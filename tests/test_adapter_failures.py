from types import SimpleNamespace

import httpx
import pytest

from engineering_ops.adapters.jira import CloudJiraProvider, DataCenterJiraProvider, JiraClient, JiraError
from test_jira_adapters import FakeJira, FakeHttp, FakeResponse


def client_with(responses):
    jira = object.__new__(JiraClient)
    jira.name = "fake"
    jira.cfg = SimpleNamespace(instance_type="cloud", base_url="https://jira.example.com")
    jira.http = FakeHttp(responses)
    return jira


@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_redirect_never_follows_or_forwards_credentials(code):
    response = FakeResponse(status_code=code)
    response.headers["location"] = "https://unexpected.example.com"
    jira = client_with([response])
    with pytest.raises(JiraError, match="not followed") as error:
        jira.request("GET", "/rest/api/3/myself")
    assert error.value.status_code == code
    assert len(jira.http.calls) == 1


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503])
def test_http_failures_are_not_retried_as_writes(code):
    jira = client_with([FakeResponse(status_code=code, text="Request failed")])
    with pytest.raises(JiraError) as error:
        jira.request("PUT", "/rest/api/3/issue/A-1", json={"fields": {}})
    assert error.value.status_code == code
    assert len(jira.http.calls) == 1


def test_non_json_response_is_a_useful_error():
    response = FakeResponse(text="Login page")
    response.headers["content-type"] = "text/html"
    with pytest.raises(JiraError, match="non-JSON"):
        client_with([response]).request("GET", "/rest/api/3/field")


def test_invalid_json_response_is_a_useful_error():
    response = FakeResponse()
    def invalid():
        raise ValueError("Invalid JSON")
    response.json = invalid
    with pytest.raises(JiraError, match="invalid JSON"):
        client_with([response]).request("GET", "/rest/api/3/field")


def test_timeout_becomes_connector_error():
    jira = client_with([])
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Timed out")
    jira.http.request = timeout
    with pytest.raises(JiraError, match="network error"):
        jira.request("GET", "/rest/api/3/field")


def test_empty_success_response_is_supported():
    response = FakeResponse(status_code=204)
    response.content = b""
    assert client_with([response]).request("PUT", "/rest/api/3/issue/A-1") == {}


def test_cloud_repeated_pagination_token_is_rejected():
    jira = FakeJira([{"issues": [{"key": "A-1"}], "nextPageToken": "repeat"},
                     {"issues": [{"key": "A-2"}], "nextPageToken": "repeat"}])
    with pytest.raises(JiraError, match="repeated nextPageToken"):
        CloudJiraProvider().search(jira, "project = A", ["summary"], 10)


def test_datacenter_auth_failure_does_not_use_search_fallback():
    jira = FakeJira([JiraError("Unauthorized", status_code=401)])
    with pytest.raises(JiraError) as error:
        DataCenterJiraProvider().search(jira, "project = A", ["summary"], 10)
    assert error.value.status_code == 401
    assert len(jira.calls) == 1


def test_cloud_projects_follow_server_pagination():
    jira = FakeJira([{"values": [{"key": "A"}], "total": 2, "isLast": False},
                     {"values": [{"key": "B"}], "total": 2, "isLast": True}])
    rows = CloudJiraProvider().projects(jira, 10)
    assert [row["key"] for row in rows] == ["A", "B"]
    assert jira.calls[1][2]["params"]["startAt"] == 1


def test_board_discovery_follows_server_pagination():
    jira = client_with([FakeResponse(payload={"values": [{"id": 1}], "isLast": False}),
                        FakeResponse(payload={"values": [{"id": 2}], "isLast": True})])
    assert [row["id"] for row in jira.boards("ENG", limit=10)] == [1, 2]
    assert jira.http.calls[1][2]["params"]["startAt"] == 1


def test_sprint_issue_search_refuses_silent_truncation():
    jira = object.__new__(JiraClient)
    jira.name = "fake"
    jira.search = lambda jql, fields, limit: [{"key": f"A-{i}"} for i in range(limit)]
    with pytest.raises(JiraError, match="limit"):
        jira.sprint_issues(1, limit=2)
