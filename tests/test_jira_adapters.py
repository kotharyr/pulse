from types import SimpleNamespace

from engineering_ops.adapters.jira import (
    CloudJiraProvider,
    DataCenterJiraProvider,
    JiraClient,
    JiraClientManager,
)
from engineering_ops.config import JiraInstanceConfig, settings


class FakeJira:
    name = "test"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return next(self.responses)


def test_cloud_provider_uses_v3_token_pagination():
    jira = FakeJira([
        {"issues": [{"key": "A-1"}], "nextPageToken": "next"},
        {"issues": [{"key": "A-2"}]},
    ])
    rows = CloudJiraProvider().search(jira, "project = A", ["summary"], 10)
    assert [row["key"] for row in rows] == ["A-1", "A-2"]
    assert [call[1] for call in jira.calls] == ["/rest/api/3/search/jql"] * 2
    assert jira.calls[1][2]["json"]["nextPageToken"] == "next"


def test_datacenter_provider_uses_v2_offset_pagination():
    jira = FakeJira([
        {"issues": [{"key": "A-1"}], "total": 2},
        {"issues": [{"key": "A-2"}], "total": 2},
    ])
    rows = DataCenterJiraProvider().search(jira, "project = A", ["summary"], 10)
    assert [row["key"] for row in rows] == ["A-1", "A-2"]
    assert jira.calls[1][2]["json"]["startAt"] == 1


def test_sprint_issues_requests_resolved_story_point_id():
    jira = object.__new__(JiraClient)
    seen = {}

    def search(jql, fields, limit):
        seen.update(jql=jql, fields=fields, limit=limit)
        return []

    jira.search = search
    JiraClient.sprint_issues(jira, 42, story_points_field_id="customfield_10016")
    assert "customfield_10016" in seen["fields"]
    assert "Story Points" not in seen["fields"]


def test_sprint_movement_honors_configured_batch_size(monkeypatch):
    jira = object.__new__(JiraClient)
    calls = []
    jira.request = lambda method, path, **kwargs: calls.append(kwargs["json"]["issues"])
    monkeypatch.setattr(settings, "bulk_batch_size", 2)
    JiraClient.move_issues_to_sprint(jira, 7, ["A-1", "A-2", "A-3"])
    assert calls == [["A-1", "A-2"], ["A-3"]]


def test_client_manager_reuses_and_closes_clients(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, name, cfg):
            self.name, self.cfg, self.closed = name, cfg, False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr("engineering_ops.adapters.jira.JiraClient", FakeClient)
    cfg = JiraInstanceConfig.model_validate({"type": "cloud", "base_url": "https://x"})
    manager = JiraClientManager()
    assert manager.get("cloud", cfg) is manager.get("cloud", cfg)
    manager.close()
    assert len(created) == 1 and created[0].closed

