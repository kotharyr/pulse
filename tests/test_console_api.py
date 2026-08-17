from starlette.testclient import TestClient

import engineering_ops.api as console_api
from engineering_ops.config import settings
from engineering_ops.server import create_mcp_server


class FakeConsoleBackend:
    def __init__(self):
        self.calls = []

    def list_jira_instances(self):
        self.calls.append(("instances",))
        return {
            "instances": [
                {"name": "cloud", "kind": "cloud", "default_project": "ENG"},
                {"name": "onprem", "kind": "datacenter", "default_project": "OPS"},
            ]
        }

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

    def discover_console_sprints(self, instance, project_key=None):
        self.calls.append(("sprint_discovery", instance, project_key))
        return {
            "instance": instance,
            "project": project_key or "ENG",
            "current_sprint": {"id": 12, "name": "Sprint 12", "state": "active"},
            "next_sprint": {"id": 13, "name": "Sprint 13", "state": "future"},
            "selection": {"next_strategy": "number"},
        }

    def discover_environment(self, instance):
        self.calls.append(("environment", instance))
        return {"instance": instance, "projects": [{"key": "ENG", "name": "Engineering"}], "cache_age_seconds": 12}

    def refresh_environment(self, instance, project_key=None):
        self.calls.append(("environment_refresh", instance, project_key))
        return {"instance": instance, "project": project_key or "ENG", "refreshed_at": "2026-01-01T00:00:00Z"}

    def get_environment_summary(self, instance=None):
        self.calls.append(("environment_summary", instance))
        return {"instances": [{"instance": instance or "cloud", "cached": True}]}

    def list_saved_views(self):
        self.calls.append(("views",))
        return {"views": [{"id": "security", "name": "Security", "instance": "cloud", "jql": "project = ENG"}]}

    def get_saved_view(self, name):
        self.calls.append(("view", name))
        return {"view": {"id": name, "name": name, "instance": "cloud", "jql": "project = ENG"}}

    def search_saved_view(self, name, page=1, page_size=25):
        self.calls.append(("view_issues", name, page, page_size))
        return {"view": {"name": name}, "results": {"issues": [{"key": "ENG-2"}], "pagination": {"page": page}}}

    def save_operational_view(self, view):
        self.calls.append(("view_save", view))
        return {"view": {"id": "new-view", **view}}

    def delete_operational_view(self, name):
        self.calls.append(("view_delete", name))
        return {"deleted": True, "id": name}

    def repository_inventory(self):
        self.calls.append(("repositories",))
        return {"configured": True, "repositories": [{"name": "service-a"}]}

    def analyze_security_package_updates(self, instance, project_key=None, limit=2000):
        self.calls.append(("security", instance, project_key, limit))
        return {"matched_tickets": 2, "remediation_actions": [{"component": "openssl"}]}

    def engineering_review(self, **payload):
        self.calls.append(("engineering_review", payload))
        return {"workflow": "engineering_review", "summary": "review", "metrics": [], "sections": {}}

    def sprint_analysis(self, **payload):
        self.calls.append(("orchestration_sprint_analysis", payload))
        return {"workflow": "sprint_analysis", "summary": "sprint", "metrics": [], "sections": {}}

    def sprint_close_preview_workflow(self, **payload):
        self.calls.append(("sprint_close_preview_workflow", payload))
        return {"workflow": "sprint_close_preview", "execution_preview": {"preview_id": "abc123"}}

    def sprint_close_apply_workflow(self, preview_id):
        self.calls.append(("sprint_close_apply_workflow", preview_id))
        return {"workflow": "sprint_close_apply", "sections": {"result": {"applied": False}}}

    def portfolio_review(self, **payload):
        self.calls.append(("portfolio_review", payload))
        return {"workflow": "portfolio_review", "summary": "portfolio"}

    def backlog_review(self, **payload):
        self.calls.append(("backlog_review", payload))
        return {"workflow": "backlog_review", "summary": "backlog"}

    def security_remediation_analysis(self, **payload):
        self.calls.append(("security_remediation_analysis", payload))
        return {"workflow": "security_remediation_analysis", "summary": "security"}

    def saved_view_review(self, view_name, **payload):
        self.calls.append(("saved_view_review", view_name, payload))
        return {"workflow": "saved_view_review", "summary": view_name}

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
        discovery = client.get("/api/sprint/discovery", params={"instance": "cloud"})
        assert discovery.status_code == 200
        assert discovery.json()["selection"]["next_strategy"] == "number"
        assert client.get("/api/environment", params={"instance": "cloud"}).json()["projects"][0]["key"] == "ENG"
        assert client.post("/api/environment/refresh", json={"instance": "cloud", "project": "ENG"}).json()["project"] == "ENG"
        assert client.get("/api/environment/summary", params={"instance": "cloud"}).json()["instances"][0]["cached"] is True

        assert client.get("/api/views").json()["views"][0]["name"] == "Security"
        assert client.get("/api/views/Security").json()["view"]["name"] == "Security"
        assert client.get("/api/views/Security/issues", params={"page": 2}).json()["results"]["pagination"]["page"] == 2
        assert client.post("/api/views", json={"name": "New View", "instance": "cloud", "jql": "project = ENG"}).json()["view"]["id"] == "new-view"
        assert client.delete("/api/views/New%20View").json()["deleted"] is True
        assert client.get("/api/repositories").json()["repositories"][0]["name"] == "service-a"
        assert client.get("/api/security/remediation", params={"instance": "cloud", "project": "ENG", "limit": 20}).json()["matched_tickets"] == 2

        assert client.post("/api/orchestration/engineering-review", json={"instance": "cloud", "project": "ENG"}).json()["workflow"] == "engineering_review"
        assert client.post("/api/orchestration/sprint-analysis", json={"instance": "cloud"}).json()["workflow"] == "sprint_analysis"
        assert client.post("/api/orchestration/sprint-close-preview", json={"instance": "cloud", "sprint_id": 12, "next_sprint_id": 13}).status_code == 201
        assert client.post("/api/orchestration/sprint-close-apply", json={"preview_id": "abc123"}).json()["workflow"] == "sprint_close_apply"
        assert client.post("/api/orchestration/portfolio-review", json={"instance": "cloud"}).json()["workflow"] == "portfolio_review"
        assert client.post("/api/orchestration/backlog-review", json={"instance": "cloud"}).json()["workflow"] == "backlog_review"
        assert client.post("/api/orchestration/security-remediation-analysis", json={"instance": "cloud"}).json()["workflow"] == "security_remediation_analysis"
        assert client.post("/api/orchestration/saved-view-review", json={"view_name": "Security"}).json()["workflow"] == "saved_view_review"
        assert client.post("/api/orchestration/sprint-close-apply", json={}).status_code == 400

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
    assert ("sprint_discovery", "cloud", None) in fake.calls
    assert ("environment_refresh", "cloud", "ENG") in fake.calls
    assert ("view_issues", "Security", 2, 25) in fake.calls
    assert ("security", "cloud", "ENG", 20) in fake.calls
    assert ("engineering_review", {"instance": "cloud", "project": "ENG"}) in fake.calls
    assert ("sprint_close_apply_workflow", "abc123") in fake.calls


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
    assert "sidebar-toggle" in index.text
    assert "theme-toggle" in index.text
    assert "Environment" in index.text
    assert "Saved Operational Views" in index.text
    assert "Repository Inventory" in index.text
    assert "Operational Security Issues" in index.text
    assert "Engineering Workflows" in index.text
    assert "Sprint Close Preview" in index.text
    assert 'value="ORDER BY updated DESC"' not in index.text
    assert script.status_code == 200
    assert "setSidebarCollapsed" in script.text
    assert "previewCloseSprint" in script.text
    assert "loadSprintDiscovery" in script.text
    assert "defaultJqlForInstance" in script.text
    assert "loadEnvironment" in script.text
    assert "loadRepositories" in script.text
    assert "loadSecurity" in script.text
    assert "runWorkflow" in script.text
    assert "/api/orchestration/" in script.text
    assert "/api/views" in script.text
    assert styles.status_code == 200
    assert ".sidebar-collapsed" in styles.text
    assert ".sprint-ring" in styles.text
    assert ".saved-view-layout" in styles.text
    assert ".workflow-grid" in styles.text
