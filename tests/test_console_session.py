"""Automatic local Console sessions never expose or replace MCP credentials."""
import pytest
from starlette.testclient import TestClient

import engineering_ops.api as api
from engineering_ops.auth import LocalConsoleSession
from engineering_ops.config import settings
from engineering_ops.server import create_mcp_server
from engineering_ops.services.identity import current_actor, token_actor


@pytest.fixture
def console_client(monkeypatch):
    monkeypatch.setattr(settings, "mcp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "mcp_bearer_token", "private-mcp-credential")
    monkeypatch.setattr(api.backend, "list_jira_instances", lambda: {"instances": []})
    monkeypatch.setattr(api.backend, "create_execution_preview", lambda *args: {"actor": current_actor()})
    app = create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50100)) as client:
        yield client


def test_console_bootstraps_private_api_cookie_without_exposing_mcp_token(console_client):
    assert console_client.get("/api/instances").status_code == 401
    response = console_client.get("/console")
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert "private-mcp-credential" not in cookie + response.text
    assert 'id="console-token"' not in response.text
    assert response.text.index('id="instance-select"') < response.text.index('id="console-connect"') < response.text.index('id="mode-pill"')
    assert response.headers["cache-control"] == "no-store"
    assert console_client.get("/api/instances").status_code == 200


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "https://outside.example"},
    {"Origin": "null"},
    {"Origin": "http://127.0.0.1:8080", "Sec-Fetch-Site": "cross-site"},
])
def test_cookie_write_requires_a_same_origin_browser_request(console_client, headers):
    console_client.get("/console")
    response = console_client.post("/api/executions/preview", json={"action": "test"}, headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("headers", [
    {"Origin": "http://127.0.0.1:8080"}, {"Sec-Fetch-Site": "same-origin"},
])
def test_local_cookie_preserves_approval_actor(console_client, headers):
    console_client.get("/console")
    response = console_client.post("/api/executions/preview", json={"action": "test"}, headers=headers)
    assert response.status_code == 201
    assert response.json()["actor"] == token_actor("private-mcp-credential")


@pytest.mark.parametrize("headers", [
    {"Origin": "https://outside.example"}, {"Sec-Fetch-Site": "cross-site"},
])
def test_cross_site_console_navigation_cannot_issue_session(console_client, headers):
    response = console_client.get("/console", headers=headers)
    assert "set-cookie" not in response.headers
    assert console_client.get("/api/instances").status_code == 401


def test_cookie_is_not_a_bearer_credential_for_mcp_or_readiness(console_client):
    console_client.get("/console")
    assert console_client.get("/ready").status_code == 401
    assert console_client.post("/mcp", headers={"Accept": "application/json, text/event-stream"}, json={}).status_code == 401
    assert console_client.get("/api/instances", headers={"Origin": "https://outside.example"}).status_code == 401
    assert console_client.get("/api/instances", headers={"Authorization": "Bearer private-mcp-credential"}).status_code == 200


@pytest.mark.parametrize("peer,host", [
    ("192.0.2.20", "127.0.0.1"), ("127.0.0.1", "outside.example"),
])
def test_remote_clients_and_dns_aliases_never_get_console_cookie(monkeypatch, peer, host):
    monkeypatch.setattr(settings, "mcp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "mcp_bearer_token", "private-mcp-credential")
    app = create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url=f"http://{host}:8080", client=(peer, 50100)) as client:
        response = client.get("/console")
        assert "set-cookie" not in response.headers
        assert client.get("/api/instances").status_code != 200


def test_network_bound_deployments_do_not_enable_local_sessions(monkeypatch):
    monkeypatch.setattr(settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(settings, "mcp_bearer_token", "private-mcp-credential")
    app = create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50100)) as client:
        assert "set-cookie" not in client.get("/console").headers
        assert client.get("/api/instances").status_code == 401


def test_tampered_or_missing_session_is_rejected(console_client):
    response = console_client.get("/console")
    cookie_name = next(iter(response.cookies.keys()))
    console_client.cookies.clear()
    console_client.cookies.set(cookie_name, "tampered")
    assert console_client.get("/api/instances").status_code == 401
