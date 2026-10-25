from copy import deepcopy
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import engineering_ops.api as console_api
import engineering_ops.server as server_module
from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.config import settings
from engineering_ops.services.health import engineering_health
from engineering_ops.services.orchestration import EngineeringOrchestrator
from engineering_ops.services.security import normalize_remediation_actions, version_at_least
from test_orchestration import FakeOrchestrationBackend
from test_platform_contracts import FakeFieldUpdateJira
from test_portfolio_hygiene import FakePortfolioBackend, FakePortfolioJira
from engineering_ops.services.portfolio_hygiene import PortfolioHygieneService


@pytest.mark.parametrize("path,method,payload", [
    ("/api/instances", "GET", None),
    ("/api/executions/preview", "POST", {}),
    ("/api/views", "POST", {"name": "bad"}),
    ("/api/views/anything", "DELETE", None),
    ("/diagnostics", "GET", None),
    ("/ready", "GET", None),
])
@pytest.mark.parametrize("token", [None, "wrong"])
def test_custom_routes_require_configured_token(monkeypatch, path, method, payload, token):
    monkeypatch.setattr(settings, "mcp_bearer_token", "test-token")
    app = server_module.create_mcp_server(validate_configuration=False).streamable_http_app()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        response = client.request(method, path, json=payload, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_console_token_allows_access_and_liveness_stays_public(monkeypatch):
    monkeypatch.setattr(settings, "mcp_bearer_token", "test-token")
    monkeypatch.setattr(console_api.backend, "list_jira_instances", lambda: {"instances": []})
    app = server_module.create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        assert client.get("/api/instances", headers={"Authorization": "Bearer test-token"}).status_code == 200
        assert client.get("/health/live").status_code == 200
        assert client.get("/console").status_code == 200


@pytest.mark.parametrize("tool_name", ["apply_field_updates", "assign_to_quarter", "apply_close_sprint"])
def test_low_level_mcp_apply_cannot_self_approve(monkeypatch, tool_name):
    class TrapBackend:
        def __getattr__(self, name):
            raise AssertionError(f"Unreviewed apply contacted backend: {name}")
    monkeypatch.setattr(server_module, "backend", TrapBackend())
    if tool_name == "apply_field_updates":
        result = server_module.apply_field_updates("fake", "key = A-1", {"Target Quarter": "FY27 Q1"})
    elif tool_name == "assign_to_quarter":
        result = server_module.assign_to_quarter("fake", "key = A-1", "FY27 Q1", dry_run=False)
    else:
        result = server_module.apply_close_sprint("fake", 1, 2)
    assert result["applied"] is False
    assert "preview_id" in result["reason"]


def test_rejected_execution_cannot_write(monkeypatch):
    monkeypatch.setattr(settings, "mode", "safe_apply")
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    record = backend.create_execution_preview("field_updates", {
        "instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"},
    })
    backend.reject_execution_preview(record["preview_id"])
    with pytest.raises(ValueError, match="rejected"):
        backend.apply_execution_preview(record["preview_id"])
    assert jira.updated == []


def test_successful_execution_cannot_be_replayed(monkeypatch):
    monkeypatch.setattr(settings, "mode", "safe_apply")
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    record = backend.create_execution_preview("field_updates", {
        "instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"},
    })
    assert backend.apply_execution_preview(record["preview_id"])["status"] == "succeeded"
    with pytest.raises(ValueError, match="succeeded"):
        backend.apply_execution_preview(record["preview_id"])
    assert len(jira.updated) == 1


def test_field_preview_is_bound_to_instance():
    backend = EngineeringOpsBackend(client_getter=lambda _: FakeFieldUpdateJira())
    first = backend.preview_field_updates("one", "project = ENG", {"Target Quarter": "FY27 Q1"})
    second = backend.preview_field_updates("two", "project = ENG", {"Target Quarter": "FY27 Q1"})
    assert first["preview_id"] != second["preview_id"]


def test_field_apply_refuses_changed_current_value(monkeypatch):
    class ChangingJira(FakeFieldUpdateJira):
        value = {"value": "FY26 Q4"}
        def search(self, jql, fields, limit):
            return [{"key": "ENG-1", "fields": {"summary": "Work", "customfield_10001": self.value}}]
    jira = ChangingJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    monkeypatch.setattr(settings, "mode", "safe_apply")
    preview = backend.preview_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"})
    jira.value = {"value": "FY27 Q2"}
    result = backend.apply_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"}, preview_id=preview["preview_id"])
    assert result["applied"] is False
    assert jira.updated == []


def test_rejected_hygiene_preview_cannot_write():
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira, mode="safe_apply")
    service = PortfolioHygieneService(backend)
    record = service.preview_fix(instance="onprem", categories=["labels"])
    backend.execution_store.mark_rejected(record["preview_id"])
    with pytest.raises(ValueError, match="rejected"):
        service.apply(record["preview_id"])
    assert jira.updated_operations == []


class SprintJira:
    name = "fake"
    cfg = SimpleNamespace(story_points_field_name="Story Points", sprint_capacity_points=20,
                          sprint_capacity_issue_count=None, sprint_capacity_buffer_percent=0, default_board_id=None)
    def __init__(self):
        self.sprints = {1: {"id": 1, "state": "active", "originBoardId": 7},
                        2: {"id": 2, "state": "future", "originBoardId": 7}}
        self.issues = [{"key": "ENG-1", "fields": {"summary": "Work", "status": {"name": "In Progress"},
                       "issuetype": {"name": "Story"}, "customfield_1": 3}}]
        self.writes = []
    def fields(self):
        return [{"id": "customfield_1", "name": "Story Points"}]
    def sprint(self, sprint_id):
        return deepcopy(self.sprints[sprint_id])
    def sprint_issues(self, sprint_id, story_points_field_id=None):
        return deepcopy(self.issues) if sprint_id == 1 else []
    def resolve_status_transition(self, *args, **kwargs):
        return {"id": "31", "to": {"statusCategory": {"key": "done"}}}
    def move_issues_to_sprint(self, *args):
        self.writes.append(("move", args))
        return []
    def update_sprint(self, *args):
        self.writes.append(("close", args))
        return {}


@pytest.mark.parametrize("scenario", ["same", "closed_source", "closed_target", "different_board", "move_and_split", "duplicate_split", "negative_points", "nan_points"])
def test_invalid_sprint_close_is_blocked(monkeypatch, scenario):
    monkeypatch.setattr(settings, "mode", "approved_destructive")
    jira = SprintJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    target, kwargs = 2, {"rollover_all_incomplete": True}
    split = {"source_issue_key": "ENG-1", "new_summary": "Follow on", "source_transition_status": "Done", "story_points": 3}
    if scenario == "same": target = 1
    if scenario == "closed_source": jira.sprints[1]["state"] = "closed"
    if scenario == "closed_target": jira.sprints[2]["state"] = "closed"
    if scenario == "different_board": jira.sprints[2]["originBoardId"] = 8
    if scenario == "move_and_split": kwargs = {"move_issue_keys": ["ENG-1"], "split_plans": [split]}
    if scenario == "duplicate_split": kwargs["split_plans"] = [split, dict(split)]
    if scenario in {"negative_points", "nan_points"}:
        split["story_points"] = -1 if scenario == "negative_points" else float("nan")
        kwargs["split_plans"] = [split]
    preview = backend.preview_close_sprint("fake", 1, target, **kwargs)
    assert preview["errors"]
    assert preview["can_apply"] is False
    result = backend.apply_close_sprint("fake", 1, target, preview_id=preview["preview_id"], **kwargs)
    assert result["applied"] is False
    assert jira.writes == []


def test_sprint_close_success_uses_reviewed_rollover(monkeypatch):
    monkeypatch.setattr(settings, "mode", "approved_destructive")
    jira = SprintJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    preview = backend.preview_close_sprint("fake", 1, 2, rollover_all_incomplete=True)
    result = backend.apply_close_sprint("fake", 1, 2, rollover_all_incomplete=True, preview_id=preview["preview_id"])
    assert result["applied"] is True
    assert jira.writes == [("move", (2, ["ENG-1"])), ("close", (1, {"state": "closed"}))]


def test_explicit_missing_sprint_name_never_falls_back_to_another():
    backend = FakeOrchestrationBackend()
    result = EngineeringOrchestrator(backend).sprint_close_preview(instance="cloud", sprint_name="Does not exist", next_sprint_id=13)
    assert result["execution_preview"] is None
    assert not any(call[0] == "preview" for call in backend.calls)


def test_engineering_review_surfaces_nested_source_failure():
    class BrokenSecurity(FakeOrchestrationBackend):
        def analyze_security_package_updates(self, *args):
            raise RuntimeError("Security source unavailable")
    result = EngineeringOrchestrator(BrokenSecurity()).engineering_review(instance="cloud", include_sections=["security"])
    assert result["source_coverage"]
    assert any(row["status"] == "failed" for row in result["source_coverage"])
    assert result["confidence"]["level"] == "low"


def test_health_accepts_naive_and_invalid_timestamps():
    issues = [{"key": "ENG-1", "fields": {"updated": "2020-01-01T00:00:00", "status": {"name": "Blocked"}}},
              {"key": "ENG-2", "fields": {"updated": "invalid", "assignee": {"displayName": "Ada"}}}]
    result = engineering_health(issues)
    assert result["stale_issue_keys"] == ["ENG-1"]
    assert result["blocked_count"] == 1
    assert result["unassigned_count"] == 1


@pytest.mark.parametrize("version", ["^3.0.15", ">=3.0.15", "3.0.15-rc.1", "3.0.15+vendor1", "sha256:123456", "3.0.x"])
def test_security_version_constraints_are_not_claimed_fixed(version):
    assert version_at_least(version, "3.0.15") is None


def test_repository_with_vulnerable_occurrence_is_not_already_fixed():
    finding = {"issue_key": "SEC-1", "packages": ["openssl"], "fixed_versions": [{"package": "openssl", "required_version": "3.0.15"}]}
    inventory = [{"name": "api", "packages": [{"package": "openssl", "version": "3.0.12"}, {"package": "openssl", "version": "3.0.15"}]}]
    action = normalize_remediation_actions([finding], inventory)[0]
    assert action["repositories_requiring_upgrade"] == ["api"]
    assert action["already_fixed_repositories"] == []


def test_console_invalid_sprint_id_returns_validation_error():
    app = server_module.create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080", raise_server_exceptions=False) as client:
        result = client.get("/api/sprint/analysis?instance=cloud&sprint_id=invalid")
    assert result.status_code == 400
    assert "error" in result.json()


@pytest.mark.parametrize("path", ["/api/security/remediation?instance=cloud&limit=invalid", "/api/executions?limit=invalid"])
def test_console_invalid_limits_return_validation_error(path):
    app = server_module.create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080", raise_server_exceptions=False) as client:
        response = client.get(path)
    assert response.status_code == 400


def test_identical_preview_can_be_reviewed_again_without_reviving_rejected_id(monkeypatch):
    monkeypatch.setattr(settings, "mode", "safe_apply")
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    params = {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}}
    old = backend.create_execution_preview("field_updates", params)
    backend.reject_execution_preview(old["preview_id"])
    new = backend.create_execution_preview("field_updates", params)
    assert old["preview_id"] != new["preview_id"]
    assert backend.execution_store.get_record(old["preview_id"]).status == "rejected"
    assert backend.apply_execution_preview(new["preview_id"])["status"] == "succeeded"


def test_execution_failure_is_recorded_and_not_replayed(monkeypatch):
    monkeypatch.setattr(settings, "mode", "approved_destructive")
    jira = SprintJira()
    def fail_move(*args):
        raise RuntimeError("Move failed")
    jira.move_issues_to_sprint = fail_move
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    record = backend.create_execution_preview("close_sprint", {"instance": "fake", "sprint_id": 1, "next_sprint_id": 2, "rollover_all_incomplete": True})
    with pytest.raises(RuntimeError, match="Move failed"):
        backend.apply_execution_preview(record["preview_id"])
    assert backend.execution_store.get_record(record["preview_id"]).status == "failed"
    assert jira.writes == []
    with pytest.raises(ValueError, match="failed"):
        backend.apply_execution_preview(record["preview_id"])


def test_execution_apply_is_consumed_atomically():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from engineering_ops.services.executions import ExecutionHistory
    store = ExecutionHistory()
    record = store.add_preview("field_updates", "fake", {}, {"preview_id": "fingerprint"})
    barrier = Barrier(2)
    def attempt():
        barrier.wait()
        try:
            return store.begin_apply(record["preview_id"])["status"]
        except ValueError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == ["applying", "blocked"]


@pytest.mark.parametrize("category", ["dates", "labels"])
def test_hygiene_refuses_stale_source_values(category):
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira, mode="safe_apply")
    service = PortfolioHygieneService(backend)
    record = service.preview_fix(instance="onprem", categories=[category])
    for change in record["preview"]["changes"]:
        if category == "labels":
            jira.issues[change["issue_key"]]["fields"]["labels"] = ["QP-FY28Q1-committed"]
        else:
            from engineering_ops.services.fields import resolve_field
            field_id = resolve_field(jira, change["field"])["id"]
            jira.issues[change["issue_key"]]["fields"][field_id] = "2029-01-01"
    result = service.apply(record["preview_id"])
    assert result["applied"] is False
    assert all(not row["ok"] for row in result["results"])
    assert jira.updated_fields == []
    assert jira.updated_operations == []


def test_mcp_protocol_can_call_a_read_only_tool(monkeypatch):
    def system_readiness():
        return {"ok": True, "mode": "recommend_only"}
    monkeypatch.setattr(server_module, "system_readiness", system_readiness)
    app = server_module.create_mcp_server(validate_configuration=False).streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        init = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "audit", "version": "1"},
            },
        })
        assert init.status_code == 200
        headers["mcp-session-id"] = init.headers["mcp-session-id"]
        assert client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
        result = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "system_readiness", "arguments": {}},
        })
        assert result.status_code == 200
        import json
        message = json.loads(next(line[6:] for line in result.text.splitlines() if line.startswith("data: ")))
        assert message["result"]["isError"] is False
        content = json.loads(message["result"]["content"][0]["text"])
        assert content == {"ok": True, "mode": "recommend_only"}


def test_sprint_split_requires_transition_to_done_category(monkeypatch):
    monkeypatch.setattr(settings, "mode", "approved_destructive")
    jira = SprintJira()
    def unresolved(*args, **kwargs):
        raise ValueError("Split source must transition to a Done status category")
    jira.resolve_status_transition = unresolved
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    preview = backend.preview_close_sprint("fake", 1, 2, split_plans=[{
        "source_issue_key": "ENG-1", "new_summary": "Follow on", "source_transition_status": "In Progress",
    }])
    assert not preview["can_apply"]
    assert any("Done" in row["error"] for row in preview["errors"])
