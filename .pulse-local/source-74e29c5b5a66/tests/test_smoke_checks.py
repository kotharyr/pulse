import importlib.util
from pathlib import Path

import pytest

from engineering_ops.adapters.jira import JiraClient


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("method,path", [
    ("PUT", "/rest/api/2/issue/A-1"), ("DELETE", "/rest/api/2/issue/A-1"),
    ("POST", "/rest/api/2/issue"), ("POST", "/rest/agile/1.0/sprint/1/issue"),
    ("PATCH", "/rest/api/2/issue/A-1"),
])
def test_live_smoke_guard_refuses_all_mutations(monkeypatch, method, path):
    smoke = load_script("smoke_read_only")
    calls = []
    monkeypatch.setattr(JiraClient, "request", lambda *args, **kwargs: calls.append(args))
    client = object.__new__(smoke.ReadOnlyJiraClient)
    with pytest.raises(ValueError, match="forbid Jira mutations"):
        client.request(method, path)
    assert calls == []


@pytest.mark.parametrize("method,path", [("GET", "/rest/api/2/myself"), ("POST", "/rest/api/3/search/jql"), ("POST", "/rest/api/2/search")])
def test_live_smoke_guard_permits_only_reads(monkeypatch, method, path):
    smoke = load_script("smoke_read_only")
    monkeypatch.setattr(JiraClient, "request", lambda *args, **kwargs: {"read": True})
    assert object.__new__(smoke.ReadOnlyJiraClient).request(method, path) == {"read": True}


def test_mcp_smoke_never_mistakes_tool_error_for_success():
    from types import SimpleNamespace
    smoke = load_script("smoke_jira_mcp")
    assert smoke.summarize(SimpleNamespace(structuredContent={"success": False, "error": "denied"}, isError=False))["passed"] is False
    assert smoke.summarize(SimpleNamespace(structuredContent={"success": True}, isError=True))["passed"] is False
    assert smoke.summarize(SimpleNamespace(structuredContent={"success": True}, isError=False))["passed"] is True
