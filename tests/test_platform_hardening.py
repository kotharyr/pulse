from pathlib import Path
from types import SimpleNamespace

from engineering_ops.backend import EngineeringOpsBackend


class FakeSettings:
    mode = "recommend_only"
    max_search_results = 5000
    local_repo_path = Path(".")

    def jira_instances(self):
        return {"cloud": SimpleNamespace(kind="cloud", default_project="ENG")}


def fake_report():
    return {
        "ok": True,
        "project_root": "/workspace",
        "loaded_env_files": [],
        "mode": "recommend_only",
        "mcp": {"host": "127.0.0.1", "port": 8080, "authentication_required": False},
        "jira_instances_file": "/workspace/config/jira_instances.json",
        "instances": [
            {
                "name": "cloud",
                "type": "cloud",
                "base_url": "https://example.atlassian.net",
                "credentials_loaded": True,
                "credential_method": "cloud_api_token",
            }
        ],
        "local_repo_root": "/workspace",
        "errors": [],
        "warnings": [],
    }


def test_platform_diagnostics_are_sanitized_and_include_future_connectors(tmp_path):
    backend = EngineeringOpsBackend(settings=FakeSettings(), configuration_reporter=fake_report)
    backend.saved_view_store.path = tmp_path / "views.json"
    backend.environment_cache.path = tmp_path / "environment.json"

    diagnostics = backend.platform_diagnostics()
    connectors = diagnostics["configuration"]["connectors"]

    assert diagnostics["product"] == "Pulse"
    assert diagnostics["status"] == "ready"
    assert any(row["connector"] == "jira" and row["status"] == "configured" for row in connectors)
    assert any(row["connector"] == "webex" and row["status"] == "not_configured" for row in connectors)
    assert "secret" not in repr(diagnostics).casefold()


def test_audit_records_preview_and_rejection(monkeypatch, tmp_path):
    class FakeJira:
        name = "fake"
        cfg = SimpleNamespace(default_project="ENG", quarter_field_name="Target Quarter", story_points_field_name="Story Points")

        def fields(self):
            return [{"id": "customfield_1", "name": "Target Quarter", "custom": True}]

        def search(self, jql, fields, limit):
            return [{"key": "ENG-1", "fields": {"summary": "Work"}}]

        def editmeta(self, issue_key):
            return {"fields": {"customfield_1": {"allowedValues": [{"id": "1", "value": "FY27 Q2"}]}}}

    backend = EngineeringOpsBackend(
        client_getter=lambda instance: FakeJira(),
        settings=FakeSettings(),
        configuration_reporter=fake_report,
    )
    backend.saved_view_store.path = tmp_path / "views.json"

    record = backend.create_execution_preview(
        "field_updates",
        {"instance": "cloud", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q2"}},
    )
    backend.reject_execution_preview(record["preview_id"])

    events = backend.audit_events()["events"]
    assert [event["action"] for event in events[:2]] == ["execution_preview_rejected", "execution_preview_created"]
