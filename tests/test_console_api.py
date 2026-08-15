from starlette.testclient import TestClient

import engineering_ops.api as console_api
from engineering_ops.config import settings
from engineering_ops.server import create_mcp_server


class FakeConsoleBackend:
    def __init__(self):
        self.calls = []

    def list_jira_instances(self):
        self.calls.append(("instances",))
        return {"instances": [{"name": "cloud", "kind": "cloud"}, {"name": "onprem", "kind": "datacenter"}]}

    def search_issues_page(self, instance, jql, fields=None, page=1, page_size=25):
        self.calls.append(("issues", instance, jql, page, page_size))
        return {
            "instance": instance,
            "jql": jql,
            "pagination": {"page": page, "page_size": page_size, "count": 1, "has_previous": False, "has_next": False},
            "issues": [{"key": "ENG-1", "fields": {"summary": "Build console"}}],
        }

    def analyze_current_sprint(self, instance, sprint_id, next_sprint_id=None):
        self.calls.append(("sprint", instance, sprint_id, next_sprint_id))
        return {
            "mode": "recommend_only",
            "instance": instance,
            "sprint": {"id": sprint_id, "name": "Sprint 12"},
            "next_sprint": {"id": next_sprint_id, "name": "Sprint 13"} if next_sprint_id else None,
            "analysis": {"completion_percent": 50, "overcommit": {"overcommitted": False}},
        }

    def create_execution_preview(self, action, parameters):
        self.calls.append(("preview", action, parameters))
        return {"preview_id": "abc123", "action": action, "parameters": parameters, "status": "previewed", "preview": {"can_apply": False}}

    def apply_execution_preview(self, preview_id):
        self.calls.append(("apply", preview_id))
        return {"preview_id": preview_id, "status": "failed", "result": {"applied": False, "reason": "MODE=recommend_only"}}

    def reject_execution_preview(self, preview_id):
        self.calls.append(("reject", preview_id))
        return {"preview_id": preview_id, "status": "rejected"}

    def execution_history(self, limit=50):
        self.calls.append(("history", limit))
        return {"executions": [{"preview_id": "abc123", "status": "rejected"}]}


def test_console_rest_endpoints(monkeypatch):
    fake = FakeConsoleBackend()
    monkeypatch.setattr(console_api, "backend", fake)
    monkeypatch.setattr(settings, "mcp_bearer_token", None)
    monkeypatch.setattr(settings, "mcp_host", "127.0.0.1")
    app = create_mcp_server(validate_configuration=False).streamable_http_app()

    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        assert client.get("/api/instances").json()["instances"][0]["name"] == "cloud"
        issues = client.get("/api/issues", params={"instance": "cloud", "jql": "project = ENG", "page": 2, "page_size": 10})
        assert issues.status_code == 200
        assert issues.json()["pagination"]["page"] == 2

        sprint = client.get("/api/sprint/analysis", params={"instance": "cloud", "sprint_id": 12, "next_sprint_id": 13})
        assert sprint.status_code == 200
        assert sprint.json()["sprint"]["name"] == "Sprint 12"

        preview = client.post(
            "/api/executions/preview",
            json={"action": "field_updates", "parameters": {"instance": "cloud", "jql": "project = ENG", "updates": {}}},
        )
        assert preview.status_code == 201
        assert preview.json()["status"] == "previewed"

        assert client.post("/api/executions/abc123/apply").json()["status"] == "failed"
        assert client.post("/api/executions/abc123/reject").json()["status"] == "rejected"
        assert client.get("/api/executions", params={"limit": 5}).json()["executions"][0]["status"] == "rejected"

    assert ("issues", "cloud", "project = ENG", 2, 10) in fake.calls
    assert ("sprint", "cloud", 12, 13) in fake.calls


def test_console_rest_reports_missing_required_search_params(monkeypatch):
    monkeypatch.setattr(console_api, "backend", FakeConsoleBackend())
    app = create_mcp_server(validate_configuration=False).streamable_http_app()

    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        response = client.get("/api/issues", params={"instance": "cloud"})

    assert response.status_code == 400
    assert response.json()["error"] == "instance and jql are required"


def test_console_static_assets_are_served(monkeypatch):
    monkeypatch.setattr(console_api, "backend", FakeConsoleBackend())
    app = create_mcp_server(validate_configuration=False).streamable_http_app()

    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        index = client.get("/console")
        script = client.get("/console/app.js")
        styles = client.get("/console/styles.css")

    assert index.status_code == 200
    assert "Ops Console" in index.text
    assert script.status_code == 200
    assert "previewCloseSprint" in script.text
    assert styles.status_code == 200
    assert ".metric-grid" in styles.text
