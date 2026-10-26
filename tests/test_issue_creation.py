"""No-network contract tests for Chat issue creation and its approval boundary."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from engineering_ops.adapters.jira import JiraClient, JiraError
from engineering_ops.adapters.issue_creation import creation_metadata, formatted_description, reporter_value
from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.services.executions import ExecutionHistory
from engineering_ops.services.identity import actor_context
from engineering_ops.services.issue_creation import IssueDraft
from engineering_ops.services.recovery import RecoveryBlocked


DRAFT = {"summary": "Increase CAPI Node Roll Timeout to 15 Minutes for Edge DC Amber Clusters",
         "overview": "Allow **15 minutes (900 seconds)** for SFCN readiness.",
         "user_story": {"role": "Kubernetes Platform Engineer", "want": "a 15 minute rolling timeout", "benefit": "SFCN pods can become Ready"},
         "description": "Identify the precise CAPI mechanism before changing its timeout.\n- Preserve existing health checks.\n- Validate SFCN readiness.",
         "acceptance_criteria": ["Amber node rolls succeed with SFCN workloads.", "Blue and Red configurations are unchanged."],
         "dependencies": ["An Amber validation cluster."], "out_of_scope": ["SFCN application changes."],
         "business_value": ["**Improves reliability** of cluster upgrades."]}
HEADINGS = ["Summary", "User Story", "Description", "Acceptance Criteria", "Dependencies", "Out of Scope", "Business Value"]


class CreationJira:
    reporter_value = reporter_value
    formatted_description = formatted_description

    def __init__(self, version="3"):
        self.platform_api_version = version
        self.cfg = SimpleNamespace(default_project="EDGE", base_url="https://example.invalid", instance_type="cloud" if version == "3" else "datacenter")
        self.user = {"displayName": "Connected engineer", "accountId": "account-one", "name": "engineer", "active": True}
        self.meta = {"project": "EDGE", "issue_type": {"id": "100", "name": "Story"},
                     "fields": {key: {"name": name, "required": key in {"summary", "project", "issuetype"}, "operations": ["set"]}
                                for key, name in {"summary": "Summary", "project": "Project", "issuetype": "Issue Type", "reporter": "Reporter", "description": "Description", "labels": "Labels"}.items()}}
        self.created, self.rows = [], []
        self.failure = None
        self.reporter_override = None
        self.read_error = None

    def creation_metadata(self, project, issue_type):
        return deepcopy({**self.meta, "project": project})

    def myself(self):
        return deepcopy(self.user)

    def create_issue(self, fields):
        if self.failure == "rejected":
            raise JiraError("Not permitted", status_code=403)
        self.created.append(deepcopy(fields))
        self.rows.append({"key": "EDGE-1", "fields": {**deepcopy(fields), "reporter": deepcopy(self.reporter_override or self.user)}})
        if self.failure == "timeout":
            raise TimeoutError("Response lost after create")
        if self.failure == "missing_key":
            return {}
        return {"key": "EDGE-1"}

    def get_issue(self, key, fields=None):
        if self.read_error:
            raise self.read_error
        return deepcopy(self.rows[0])

    def search(self, jql, fields, limit):
        assert 'labels = "pulse-create-' in jql
        return deepcopy(self.rows[:limit])


def make_backend(tmp_path, jira=None, mode="safe_apply"):
    jira = jira or CreationJira()
    clients = {"edge": jira, "other": CreationJira("2")}
    backend = EngineeringOpsBackend(client_getter=clients.__getitem__, settings=SimpleNamespace(mode=mode),
                                    execution_store=ExecutionHistory(tmp_path / "state.sqlite3"))
    return backend, jira


def preview(backend, **kwargs):
    return backend.preview_create_issue("edge", deepcopy(DRAFT), **kwargs)


@pytest.mark.parametrize("version", ["3", "2"])
def test_create_with_formatted_sections_current_reporter_and_explicit_target(tmp_path, version):
    backend, jira = make_backend(tmp_path, CreationJira(version))
    record = preview(backend, project="AMBER")
    plan = record["preview"]
    assert plan["project"] == "AMBER" and plan["reporter"] == "Connected engineer"
    assert [s.split("\n", 1)[0] for s in plan["description"].split("## ")[1:]] == HEADINGS
    assert not jira.created
    result = backend.apply_create_issue(record["preview_id"])
    assert result["result"]["issue_key"] == "EDGE-1"
    fields = jira.created[0]
    assert fields["project"] == {"key": "AMBER"}
    assert fields["reporter"] == ({"accountId": "account-one"} if version == "3" else {"name": "engineer"})
    if version == "3":
        nodes = fields["description"]["content"]
        assert [node["content"][0]["text"] for node in nodes if node["type"] == "heading"] == HEADINGS
        assert any(node["type"] == "bulletList" for node in nodes)
        assert any(text.get("marks") == [{"type": "strong"}] for node in nodes if node["type"] == "paragraph" for text in node["content"])
    else:
        assert fields["description"].startswith("h2. Summary")
        assert "*15 minutes (900 seconds)*" in fields["description"]
    assert backend.execution_store.steps(record["preview_id"])[0]["status"] == "succeeded"


@pytest.mark.parametrize("mode", ["recommend_only", "approved_destructive"])
def test_creation_requires_safe_apply_without_mutation(tmp_path, mode):
    backend, jira = make_backend(tmp_path, mode=mode)
    record = preview(backend)
    result = backend.apply_create_issue(record["preview_id"])
    assert not result["result"]["applied"] and not jira.created


def test_requires_chosen_instance_project_and_correct_actor(tmp_path):
    backend, jira = make_backend(tmp_path)
    with pytest.raises(KeyError):
        backend.preview_create_issue("missing", DRAFT)
    jira.cfg.default_project = None
    with pytest.raises(ValueError, match="Choose a project"):
        preview(backend)
    with actor_context("alice"):
        record = preview(backend, project="EDGE")
    with actor_context("bob"), pytest.raises(ValueError, match="different actor"):
        backend.apply_create_issue(record["preview_id"])
    assert not jira.created


@pytest.mark.parametrize("change", ["identity", "metadata", "connector"])
def test_stale_creation_review_never_writes(tmp_path, change):
    backend, jira = make_backend(tmp_path)
    record = preview(backend)
    if change == "identity":
        jira.user["accountId"] = "different-account"
    elif change == "metadata":
        jira.meta["fields"]["summary"]["required"] = False
    else:
        jira.cfg.base_url = "https://different.invalid"
    with pytest.raises(ValueError, match="stale|configuration changed"):
        backend.apply_create_issue(record["preview_id"])
    assert not jira.created


@pytest.mark.parametrize("key", ["reporter", "labels", "description"])
def test_unsupported_create_screen_blocks_preview(tmp_path, key):
    backend, jira = make_backend(tmp_path)
    del jira.meta["fields"][key]
    with pytest.raises(ValueError, match="create screen"):
        preview(backend)
    assert not jira.created


def test_required_extra_fields_use_human_names_and_values(tmp_path):
    backend, jira = make_backend(tmp_path)
    jira.meta["fields"]["customfield_123"] = {"name": "Environment", "required": True, "schema": {"type": "option"}, "allowedValues": [{"id": "9", "value": "Amber"}]}
    with pytest.raises(ValueError, match="Environment"):
        preview(backend)
    for additional_fields in [{"customfield_123": "Amber"}, {"Reporter": "other"}, {"Environment": "Unknown"}]:
        with pytest.raises(ValueError):
            preview(backend, additional_fields=additional_fields)
    record = preview(backend, additional_fields={"Environment": "Amber"})
    assert "customfield_123" not in str(record["preview"])
    backend.apply_create_issue(record["preview_id"])
    assert jira.created[0]["customfield_123"] == {"id": "9"}


@pytest.mark.parametrize("failure", ["timeout", "missing_key", "reporter", "read_403"])
def test_uncertain_creation_reconciles_without_duplicate_after_restart(tmp_path, failure):
    backend, jira = make_backend(tmp_path)
    record = preview(backend)
    if failure == "reporter":
        jira.reporter_override = {**jira.user, "accountId": "someone-else"}
    elif failure == "read_403":
        jira.read_error = JiraError("Read denied", status_code=403)
    else:
        jira.failure = failure
    with pytest.raises((TimeoutError, RecoveryBlocked)):
        backend.apply_create_issue(record["preview_id"])
    assert backend.execution_store.get_record(record["preview_id"]).status == "recovery_required"
    assert backend.execution_store.steps(record["preview_id"])[0]["status"] == "uncertain"
    backend.execution_store = ExecutionHistory(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError):
        backend.apply_create_issue(preview(backend)["preview_id"])
    result = backend.reconcile_execution(record["preview_id"])
    assert result["can_resume"] is (failure not in {"reporter", "read_403"})
    if result["can_resume"]:
        backend.resume_execution(record["preview_id"], result["recovery_id"])
    else:
        with pytest.raises(RecoveryBlocked):
            backend.resume_execution(record["preview_id"], result["recovery_id"])
    assert len(jira.created) == 1


def test_absent_or_ambiguous_search_never_retries_uncertain_create(tmp_path):
    backend, jira = make_backend(tmp_path)
    record = preview(backend)
    jira.failure = "timeout"
    with pytest.raises(TimeoutError):
        backend.apply_create_issue(record["preview_id"])
    original = deepcopy(jira.rows)
    for rows in [[], original * 2]:
        jira.rows = rows
        assert not backend.reconcile_execution(record["preview_id"])["can_resume"]
    assert len(jira.created) == 1


def test_success_cannot_be_repeated_even_after_metadata_changes(tmp_path):
    backend, jira = make_backend(tmp_path)
    first = preview(backend)
    backend.apply_create_issue(first["preview_id"])
    jira.meta["fields"]["summary"]["required"] = False
    with pytest.raises(ValueError, match="equivalent or overlapping"):
        backend.apply_create_issue(preview(backend)["preview_id"])
    assert len(jira.created) == 1


@pytest.mark.parametrize("change", [lambda d: d.update(summary="bad\nsummary"), lambda d: d.update(acceptance_criteria=[" "]), lambda d: d.update(reporter="other"), lambda d: d["user_story"].update(role=" ")])
def test_invalid_draft_rejected(change):
    draft = deepcopy(DRAFT)
    change(draft)
    with pytest.raises(ValueError):
        IssueDraft.model_validate(draft)


class MetadataJira:
    creation_metadata = JiraClient.creation_metadata

    def __init__(self, responses, version="3"):
        self.platform_api_version = version
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.parametrize("version", ["2", "3"])
def test_create_metadata_pagination(version):
    jira = MetadataJira([{"total": 2, "values": [{"id": "1", "name": "Bug"}]},
                         {"total": 2, "issueTypes": [{"id": "2", "name": "Story"}]},
                         {"total": 2, "fields": [{"fieldId": "summary", "name": "Summary"}]},
                         {"total": 2, "values": [{"fieldId": "reporter", "name": "Reporter"}]}], version)
    metadata = creation_metadata(jira, "EDGE", "Story")
    assert set(metadata["fields"]) == {"summary", "reporter"}
    assert jira.calls[1][2]["params"]["startAt"] == 1
    assert f"/rest/api/{version}/" in jira.calls[0][1]


def test_legacy_server_metadata_fallback():
    jira = MetadataJira([JiraError("Missing", status_code=404), {"projects": [{"key": "EDGE", "issuetypes": [{"id": "2", "name": "Story", "fields": {"summary": {"name": "Summary"}}}]}]}], "2")
    assert creation_metadata(jira, "EDGE", "Story")["fields"]["summary"]["name"] == "Summary"
    assert jira.calls[-1][2]["params"]["expand"] == "projects.issuetypes.fields"


@pytest.mark.parametrize("version,status", [("3", 404), ("2", 401), ("2", 403)])
def test_metadata_auth_errors_and_cloud_missing_route_do_not_fallback(version, status):
    jira = MetadataJira([JiraError("Denied", status_code=status)], version)
    with pytest.raises(JiraError):
        creation_metadata(jira, "EDGE", "Story")
    assert len(jira.calls) == 1


def test_metadata_truncation_is_not_silently_accepted():
    jira = MetadataJira([{"total": 2, "values": []}])
    with pytest.raises(JiraError, match="pagination stopped"):
        creation_metadata(jira, "EDGE", "Story")


def test_readonly_context_and_selected_instance_use_connection_reporter(tmp_path):
    backend, jira = make_backend(tmp_path)
    result = backend.get_issue_creation_context("other", "OPS")
    assert result["instance"] == "other" and result["project"] == "OPS"
    assert result["reporter_source"] == "Authenticated account of this Jira connection"
    record = backend.preview_create_issue("other", DRAFT, "OPS")
    backend.apply_create_issue(record["preview_id"])
    assert not jira.created
    assert backend.client("other").created[0]["reporter"] == {"name": "engineer"}


def test_explicit_rejection_can_be_reconciled_then_resumed(tmp_path):
    backend, jira = make_backend(tmp_path)
    record = preview(backend)
    jira.failure = "rejected"
    with pytest.raises(JiraError):
        backend.apply_create_issue(record["preview_id"])
    assert not jira.created
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    jira.failure = None
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert len(jira.created) == 1


def test_authenticated_mcp_creation_and_console_share_approvals(monkeypatch, tmp_path):
    import asyncio
    import json
    from starlette.testclient import TestClient
    import engineering_ops.api as api
    import engineering_ops.server as server
    from engineering_ops.config import settings
    from engineering_ops.services.identity import token_actor

    backend, jira = make_backend(tmp_path)
    monkeypatch.setattr(server, "backend", backend)
    monkeypatch.setattr(api, "backend", backend)
    monkeypatch.setattr(settings, "mcp_bearer_token", "creation-test-credential")
    mcp = server.create_mcp_server(validate_configuration=False)
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert {"get_issue_creation_context", "preview_create_issue", "apply_create_issue"} <= tools.keys()
    assert {"instance", "draft"} == set(tools["preview_create_issue"].inputSchema["required"])
    headers = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer creation-test-credential"}
    with TestClient(mcp.streamable_http_app(), base_url="http://127.0.0.1:8080") as client:
        initialized = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "creation-test", "version": "1"}}})
        headers["mcp-session-id"] = initialized.headers["mcp-session-id"]
        client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})

        def call(name, args, number):
            response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {"name": name, "arguments": args}})
            message = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))
            assert not message["result"]["isError"], message
            return json.loads(message["result"]["content"][0]["text"])

        record = call("preview_create_issue", {"instance": "edge", "draft": DRAFT}, 2)
        assert not jira.created
        assert record["actor"] == token_actor("creation-test-credential")
        assert client.post(f"/api/executions/{record['preview_id']}/apply").status_code == 401
        assert call("apply_create_issue", {"preview_id": record["preview_id"]}, 3)["status"] == "succeeded"
        # REST has the same draft validation, history and approval mechanism.
        revised = {**deepcopy(DRAFT), "summary": "A distinct reviewed story"}
        response = client.post("/api/executions/preview", headers={"Authorization": headers["Authorization"]},
                               json={"action": "create_issue", "parameters": {"instance": "edge", "draft": revised}})
        assert response.status_code == 201
        assert response.json()["action"] == "create_issue"
    assert len(jira.created) == 1


@pytest.mark.parametrize("version,expected_fingerprint", [
    ("3", "be877c0612eecfc50cecca64cf7b702b6b446c34d574414288d17ef0b6ed46ab"),
    ("2", "1ee0cc166f283d0add35f046fc93aaaa379f6a3eb15bc878480fd7fab69fa671"),
])
def test_refactor_preserves_stored_approval_fingerprints(tmp_path, version, expected_fingerprint):
    # Captured from commit d50da3a before refactoring. Changing these hashes would
    # invalidate an already-reviewed draft even though its intended write is unchanged.
    from engineering_ops.services.executions import fingerprint

    backend, jira = make_backend(tmp_path, CreationJira(version))
    record = preview(backend)
    assert fingerprint(record["preview"]) == expected_fingerprint
    backend.apply_create_issue(record["preview_id"])
    assert len(jira.created) == 1


@pytest.mark.parametrize("schema,allowed,value,expected", [
    ({"type": "string"}, [], "amber", "amber"),
    ({"type": "number"}, [], 900, 900),
    ({"type": "number"}, [], 1.5, 1.5),
    ({"type": "array", "items": "string"}, [], ["edge", "amber"], ["edge", "amber"]),
    (
        {"type": "array"},
        [{"id": "1", "name": "Amber"}, {"id": "2", "name": "Blue"}],
        ["amber", "Blue"],
        [{"id": "1"}, {"id": "2"}],
    ),
])
def test_additional_field_payloads_keep_supported_values(tmp_path, schema, allowed, value, expected):
    backend, jira = make_backend(tmp_path)
    jira.meta["fields"]["customfield_123"] = {
        "name": "Environment", "required": True, "schema": schema,
        "allowedValues": allowed,
    }
    record = preview(backend, additional_fields={"Environment": value})
    backend.apply_create_issue(record["preview_id"])
    assert jira.created[0]["customfield_123"] == expected


@pytest.mark.parametrize("schema,allowed,value", [
    ({"type": "number"}, [], True),
    ({"type": "number"}, [], float("nan")),
    ({"type": "number"}, [], float("inf")),
    ({"type": "string", "custom": "jira:textarea"}, [], "Rich text"),
    ({"type": "array", "items": "string"}, [], []),
    ({"type": "array", "items": "string"}, [], [" "]),
    ({"type": "array"}, [{"id": "1", "name": "Amber"}], "Amber"),
    ({"type": "option"}, [{"name": "Amber"}], "Amber"),
    (
        {"type": "option"},
        [{"id": "1", "name": "Amber"}, {"id": "2", "name": "Amber"}],
        "Amber",
    ),
])
def test_unsupported_additional_values_never_reach_jira(tmp_path, schema, allowed, value):
    backend, jira = make_backend(tmp_path)
    jira.meta["fields"]["customfield_123"] = {
        "name": "Environment", "schema": schema, "allowedValues": allowed,
    }
    with pytest.raises(ValueError):
        preview(backend, additional_fields={"Environment": value})
    assert not jira.created


@pytest.mark.parametrize("reason", ["ambiguous", "read_only"])
def test_ambiguous_or_readonly_creation_fields_block_preview(tmp_path, reason):
    backend, jira = make_backend(tmp_path)
    field = {"name": "Environment", "schema": {"type": "string"}}
    jira.meta["fields"]["customfield_123"] = field
    if reason == "ambiguous":
        jira.meta["fields"]["customfield_124"] = deepcopy(field)
    else:
        field["operations"] = []
    with pytest.raises(ValueError):
        preview(backend, additional_fields={"Environment": "Amber"})
    assert not jira.created


def test_creation_field_with_default_does_not_require_override(tmp_path):
    backend, jira = make_backend(tmp_path)
    jira.meta["fields"]["customfield_123"] = {
        "name": "Environment", "required": True, "hasDefaultValue": True,
        "schema": {"type": "string"},
    }
    backend.apply_create_issue(preview(backend)["preview_id"])
    assert "customfield_123" not in jira.created[0]


def test_recovery_blocks_changed_create_metadata(tmp_path):
    backend, jira = make_backend(tmp_path)
    record = preview(backend)
    jira.failure = "timeout"
    with pytest.raises(TimeoutError):
        backend.apply_create_issue(record["preview_id"])
    jira.meta["fields"]["summary"]["required"] = False
    review = backend.reconcile_execution(record["preview_id"])
    assert "creation:stale" in review["blocking_steps"]
    with pytest.raises(RecoveryBlocked):
        backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert len(jira.created) == 1


@pytest.mark.parametrize("version", ["3", "2"])
def test_unreadable_reporter_identity_stays_uncertain_during_recovery(tmp_path, version):
    backend, jira = make_backend(tmp_path, CreationJira(version))
    record = preview(backend)
    # A successful POST with an unusable reporter response must remain uncertain.
    jira.reporter_override = {"displayName": "No stable identity"}
    with pytest.raises(RecoveryBlocked):
        backend.apply_create_issue(record["preview_id"])
    steps = backend.execution_store.steps(record["preview_id"])
    assert steps[0]["status"] == "uncertain"
    assert not backend.reconcile_execution(record["preview_id"])["can_resume"]
    assert len(jira.created) == 1
