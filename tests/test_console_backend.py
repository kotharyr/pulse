from types import SimpleNamespace

from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.config import settings


class FakePagedJira:
    name = "fake"
    cfg = SimpleNamespace(story_points_field_name="Story Points")

    def __init__(self):
        self.fields_called = False

    def fields(self):
        self.fields_called = True
        return [{"id": "customfield_10016", "name": "Story Points"}]

    def search(self, jql, fields, limit):
        return [
            {
                "key": f"ENG-{index}",
                "fields": {
                    "summary": f"Issue {index}",
                    "status": {"name": "To Do"},
                    "customfield_10016": index,
                },
            }
            for index in range(1, 6)
        ][:limit]


def test_issue_search_page_paginates_and_sanitizes_field_ids():
    jira = FakePagedJira()
    backend = EngineeringOpsBackend(client_getter=lambda instance: jira)

    page = backend.search_issues_page("fake", "project = ENG", page=2, page_size=2)

    assert jira.fields_called is False
    assert [issue["key"] for issue in page["issues"]] == ["ENG-3", "ENG-4"]
    assert page["pagination"] == {
        "page": 2,
        "page_size": 2,
        "count": 2,
        "has_previous": True,
        "has_next": True,
        "fetched": 5,
    }
    assert "Story Points" not in page["issues"][0]["fields"]
    assert "customfield_" not in repr(page["issues"])


class FakeWriteJira:
    name = "fake"
    cfg = SimpleNamespace(default_project="ENG", quarter_field_name="Target Quarter", story_points_field_name="Story Points")

    def __init__(self):
        self.updated = []

    def fields(self):
        return [{"id": "customfield_10001", "name": "Target Quarter", "custom": True}]

    def search(self, jql, fields, limit):
        return [{"key": "ENG-1", "fields": {"summary": "Do the thing"}}]

    def editmeta(self, issue_key):
        return {"fields": {"customfield_10001": {"allowedValues": [{"id": "10", "value": "FY27 Q1"}]}}}

    def update_issue(self, issue_key, fields):
        self.updated.append((issue_key, fields))


def test_execution_preview_apply_history_and_no_write_in_recommend_only(monkeypatch):
    jira = FakeWriteJira()
    backend = EngineeringOpsBackend(client_getter=lambda instance: jira)
    monkeypatch.setattr(settings, "mode", "recommend_only")

    record = backend.create_execution_preview(
        "field_updates",
        {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}},
    )
    assert record["status"] == "previewed"
    assert record["preview"]["can_apply"] is False
    assert jira.updated == []

    applied = backend.apply_execution_preview(record["preview_id"])
    assert applied["status"] == "failed"
    assert applied["result"]["applied"] is False
    assert applied["error"] == "MODE=recommend_only"
    assert jira.updated == []

    rejected = backend.reject_execution_preview(record["preview_id"])
    assert rejected["status"] == "rejected"
    assert backend.execution_history()["executions"][0]["preview_id"] == record["preview_id"]
