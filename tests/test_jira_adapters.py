from types import SimpleNamespace

from engineering_ops.adapters.jira import (
    CloudJiraProvider,
    DataCenterJiraProvider,
    JiraError,
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
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def get_issue(self, key, fields=None):
        params = {"fields": ",".join(fields)} if fields else None
        return self.request("GET", f"/rest/api/2/issue/{key}", params=params)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = {"content-type": "application/json"}
        self.content = b"{}" if status_code < 400 else (text or "error").encode()

    def json(self):
        return self._payload


class FakeHttp:
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


def test_datacenter_provider_retries_search_with_get_on_post_404():
    jira = FakeJira([
        JiraError("test: POST /rest/api/2/search -> 404", status_code=404),
        {"issues": [{"key": "A-1"}], "total": 1},
    ])

    rows = DataCenterJiraProvider().search(jira, "project = A", ["summary", "status"], 10)

    assert rows == [{"key": "A-1"}]
    assert jira.calls[0][:2] == ("POST", "/rest/api/2/search")
    assert jira.calls[1][:2] == ("GET", "/rest/api/2/search")
    assert jira.calls[1][2]["params"]["fields"] == "summary,status"


def test_datacenter_provider_uses_direct_issue_lookup_when_search_resource_is_unavailable():
    jira = FakeJira([
        JiraError("test: POST /rest/api/2/search -> 404", status_code=404),
        JiraError("test: GET /rest/api/2/search -> 404", status_code=404),
        {"key": "WXCNP-78909", "fields": {"summary": "Target issue"}},
    ])

    rows = DataCenterJiraProvider().search(jira, 'issue = "WXCNP-78909" ORDER BY updated DESC', ["summary"], 10)

    assert rows == [{"key": "WXCNP-78909", "fields": {"summary": "Target issue"}}]
    assert jira.calls[2][:2] == ("GET", "/rest/api/2/issue/WXCNP-78909")
    assert jira.calls[2][2]["params"] == {"fields": "summary"}


def test_jira_client_request_uses_relative_paths_to_preserve_configured_context_path():
    jira = object.__new__(JiraClient)
    jira.name = "test"
    jira.cfg = SimpleNamespace(instance_type="datacenter", base_url="https://jira.example.com/jira")
    jira.http = FakeHttp([FakeResponse(payload={"ok": True})])

    result = JiraClient.request(jira, "GET", "/rest/api/2/myself")

    assert result == {"ok": True}
    assert jira.http.calls == [("GET", "rest/api/2/myself", {})]


def test_jira_client_retries_common_jira_context_path_for_datacenter_404():
    jira = object.__new__(JiraClient)
    jira.name = "test"
    jira.cfg = SimpleNamespace(instance_type="datacenter", base_url="https://jira.example.com")
    jira.http = FakeHttp([
        FakeResponse(status_code=404, text="not found"),
        FakeResponse(payload={"key": "WXCNP-78909"}),
    ])

    result = JiraClient.request(jira, "GET", "/rest/api/2/issue/WXCNP-78909")

    assert result == {"key": "WXCNP-78909"}
    assert [call[1] for call in jira.http.calls] == [
        "rest/api/2/issue/WXCNP-78909",
        "jira/rest/api/2/issue/WXCNP-78909",
    ]


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


def test_description_value_is_provider_specific():
    assert DataCenterJiraProvider().description_value("hello") == "hello"
    cloud_value = CloudJiraProvider().description_value("hello")
    assert cloud_value["type"] == "doc"
    assert cloud_value["content"][0]["content"][0]["text"] == "hello"


def test_transition_issue_to_status_does_not_return_transition_id():
    jira = object.__new__(JiraClient)
    jira.name = "test"
    jira.provider = DataCenterJiraProvider()
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"transitions": [{"id": "31", "to": {"name": "Done"}}]}
        return {}

    jira.request = request
    result = JiraClient.transition_issue_to_status(jira, "ENG-1", "Done")

    assert result == {"issue_key": "ENG-1", "to_status": "Done"}
    assert calls[1][2]["json"] == {"transition": {"id": "31"}}
