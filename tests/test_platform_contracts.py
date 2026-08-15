from types import SimpleNamespace

from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.config import settings


class FakeFieldUpdateJira:
    name = "fake"
    cfg = SimpleNamespace(default_project="ENG", quarter_field_name="Target Quarter", story_points_field_name="Story Points")

    def __init__(self):
        self.updated = []

    def fields(self):
        return [{"id": "customfield_10001", "name": "Target Quarter", "custom": True}]

    def search(self, jql, fields, limit):
        return [{"key": "ENG-1", "fields": {"summary": "Do the thing"}}]

    def editmeta(self, issue_key):
        return {
            "fields": {
                "customfield_10001": {
                    "allowedValues": [{"id": "10", "value": "FY27 Q1"}],
                }
            }
        }

    def update_issue(self, issue_key, fields):
        self.updated.append((issue_key, fields))


def test_field_update_preview_does_not_expose_jira_field_ids():
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda instance: jira)

    preview = backend.preview_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"})

    assert "preview_id" in preview
    assert "customfield_" not in repr(preview)
    assert preview["issues"][0]["updates"] == [{"field": "Target Quarter", "value": "FY27 Q1"}]


def test_apply_field_updates_requires_matching_preview_id(monkeypatch):
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda instance: jira)
    monkeypatch.setattr(settings, "mode", "safe_apply")

    missing = backend.apply_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"})
    assert missing["applied"] is False
    assert "preview_id is required" in missing["reason"]
    assert jira.updated == []

    preview = backend.preview_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"})
    applied = backend.apply_field_updates(
        "fake",
        "project = ENG",
        {"Target Quarter": "FY27 Q1"},
        preview_id=preview["preview_id"],
    )
    assert applied["applied"] is True
    assert jira.updated == [("ENG-1", {"customfield_10001": {"id": "10"}})]


def test_discover_jira_environment_hides_field_ids():
    class FakeJira:
        cfg = SimpleNamespace(default_project="ENG")

        def fields(self):
            return [{"id": "customfield_10001", "name": "Target Quarter", "custom": True}]

        def boards(self, project, limit):
            return []

        def projects(self):
            return [{"id": "10000", "key": "ENG", "name": "Engineering"}]

    backend = EngineeringOpsBackend(client_getter=lambda instance: FakeJira())
    discovered = backend.discover_jira_environment("fake")

    assert discovered["fields"] == [{"name": "Target Quarter", "custom": True}]
    assert "customfield_" not in repr(discovered["fields"])


def test_apply_close_sprint_requires_matching_preview_id(monkeypatch):
    class FakeSprintJira:
        name = "fake"
        cfg = SimpleNamespace(
            story_points_field_name="Story Points",
            sprint_capacity_points=10,
            sprint_capacity_issue_count=None,
            sprint_capacity_buffer_percent=0,
            default_board_id=None,
        )

        def __init__(self):
            self.closed = []

        def fields(self):
            return [{"id": "customfield_10016", "name": "Story Points"}]

        def sprint(self, sprint_id):
            return {"id": sprint_id}

        def sprint_issues(self, sprint_id, story_points_field_id=None):
            return []

        def update_sprint(self, sprint_id, fields):
            self.closed.append((sprint_id, fields))
            return {"id": sprint_id, **fields}

    jira = FakeSprintJira()
    backend = EngineeringOpsBackend(client_getter=lambda instance: jira)
    monkeypatch.setattr(settings, "mode", "approved_destructive")

    missing = backend.apply_close_sprint("fake", 42, 43)
    assert missing["applied"] is False
    assert "preview_id is required" in missing["reason"]
    assert jira.closed == []

    preview = backend.preview_close_sprint("fake", 42, 43)
    applied = backend.apply_close_sprint("fake", 42, 43, preview_id=preview["preview_id"])
    assert applied["applied"] is True
    assert jira.closed == [(42, {"state": "closed"})]
