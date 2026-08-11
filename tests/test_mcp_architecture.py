import asyncio

from starlette.testclient import TestClient

from engineering_ops.auth import StaticBearerTokenVerifier
from engineering_ops.config import settings
import engineering_ops.server as server_module
from engineering_ops.server import build_plugin_registry, create_mcp_server


def test_builtin_capabilities_are_plugins():
    assert build_plugin_registry().names == ["system", "jira", "repositories"]


def test_plugin_composition_preserves_tool_names():
    server = create_mcp_server(validate_configuration=False)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"system_readiness", "search_issues", "scan_repository_packages"} <= names


def test_static_bearer_token_verifier():
    verifier = StaticBearerTokenVerifier("correct")
    assert asyncio.run(verifier.verify_token("wrong")) is None
    assert asyncio.run(verifier.verify_token("correct")).client_id == "engineering-ops-client"


def test_mcp_endpoint_requires_configured_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "mcp_bearer_token", "correct")
    monkeypatch.setattr(settings, "mcp_host", "127.0.0.1")
    server = create_mcp_server(validate_configuration=False)
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8080") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        response = client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json=payload,
        )
        authorized = client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer correct",
            },
            json=payload,
        )
    assert response.status_code == 401
    assert authorized.status_code == 200


def test_health_distinguishes_liveness_from_readiness(monkeypatch):
    monkeypatch.setattr(settings, "mcp_bearer_token", None)
    monkeypatch.setattr(settings, "mcp_host", "127.0.0.1")
    app = create_mcp_server(validate_configuration=False).streamable_http_app()
    monkeypatch.setattr(server_module, "system_readiness", lambda check_connections: {
        "ok": True,
        "connections_ok": False,
        "mode": "recommend_only",
        "instances": [],
        "connections": [{"instance": "cloud", "ok": False}],
        "errors": [],
        "warnings": [],
    })
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health").status_code == 503


def test_sprint_report_resolves_story_point_field_before_search(monkeypatch):
    class FakeJira:
        cfg = type("Config", (), {"story_points_field_name": "Story Points"})()

        def fields(self):
            return [{"id": "customfield_10016", "name": "Story Points"}]

        def sprint(self, sprint_id):
            return {"id": sprint_id}

        def sprint_issues(self, sprint_id, story_points_field_id=None):
            assert story_points_field_id == "customfield_10016"
            return []

    monkeypatch.setattr(server_module, "client", lambda instance: FakeJira())
    report = server_module.report_sprint_progress("cloud", 42)
    assert report["story_points"] == 0
