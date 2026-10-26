"""Offline tests for description-ledger Cloud-to-GPK2 sprint reconciliation."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from engineering_ops.adapters.jira import JiraError
from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.services.executions import ExecutionHistory
from engineering_ops.services.identity import actor_context
from engineering_ops.services.placeholder_ledger import included_keys
from engineering_ops.services.recovery import RecoveryBlocked


SOURCE_URL = "https://cloud.example.invalid/jira"
TARGET_URL = "https://gpk.example.invalid"
POINTS_ID = "customfield_10001"
PARAMS = {"source_instance": "cloud", "instance": "gpk2", "sprint_id": 42,
          "project": "GPK", "user_mappings": {"cloud-alice": "alice", "cloud-bob": "bob"}}


def source_issue(key, points, user="alice"):
    return {"key": key, "fields": {"summary": "Cloud work " + key, POINTS_ID: points,
        "assignee": {"accountId": "cloud-" + user, "displayName": user.title(), "emailAddress": user + "@common.example.invalid"} if user else None,
        "updated": "2026-10-26T00:00:00Z", "issuetype": {"name": "Story"}}}


class SourceJira:
    platform_api_version = "3"
    cfg = SimpleNamespace(base_url=SOURCE_URL, default_project="SBG", instance_type="cloud", story_points_field_name="Story Points")

    def __init__(self):
        self.issues = [source_issue("SBG-1", 3), source_issue("SBG-2", None)]
        self.name = "Sprint Amber"

    def user_email(self, user):
        return user.get("emailAddress")

    def fields(self):
        return [{"id": POINTS_ID, "name": "Story Points"}]

    def sprint(self, sprint_id):
        return {"id": sprint_id, "name": self.name, "state": "active"}

    def sprint_issues(self, sprint_id, story_points_field_id=None):
        assert sprint_id == 42 and story_points_field_id == POINTS_ID
        return deepcopy(self.issues)


class TargetJira:
    platform_api_version = "2"

    def __init__(self):
        self.cfg = SimpleNamespace(base_url=TARGET_URL, default_project="GPK", instance_type="datacenter", story_points_field_name="Story Points")
        self.issues = {}
        self.calls = []
        self.failure = None
        self.fail_user = None
        self.read_error = False
        self.hidden = False
        self.reporter = "operator"
        self.unassignable = set()
        self.meta = {key: {"name": name, "required": key in {"project", "issuetype", "summary"}, "operations": ["set"]}
            for key, name in {"project": "Project", "issuetype": "Issue Type", "summary": "Summary",
                "description": "Description", "reporter": "Reporter", "assignee": "Assignee", "labels": "Labels",
                POINTS_ID: "Story Points"}.items()}

    def fields(self):
        return [{"id": POINTS_ID, "name": "Story Points"}]

    def creation_metadata(self, project, issue_type):
        return {"project": project, "issue_type": {"id": "10", "name": issue_type}, "fields": deepcopy(self.meta)}

    def editmeta(self, key):
        return {"fields": deepcopy(self.meta)}

    def myself(self):
        return {"name": self.reporter}

    def reporter_value(self, user):
        return {"name": user["name"]}

    def assignable_user(self, project, username):
        if username in self.unassignable:
            raise ValueError("User cannot be assigned in this project")
        return {"name": username, "displayName": username.title()}

    def search(self, jql, fields, limit):
        if self.hidden:
            return []
        rows = list(self.issues.values())
        if " OR " not in jql:
            marker = jql.split('labels = "')[1].split('"')[0]
            rows = [row for row in rows if marker in row["fields"].get("labels", [])]
        return deepcopy(rows[:limit])

    def get_issue(self, key, fields=None):
        if self.read_error:
            raise JiraError("Read forbidden", status_code=403)
        return deepcopy(self.issues[key])

    def create_issue(self, fields):
        fail = self.fail_user in {None, fields["assignee"]["name"]}
        if self.failure == "reject" and fail:
            raise JiraError("Rejected", status_code=400)
        key = "GPK-" + str(len(self.issues) + 1)
        self.issues[key] = {"key": key, "fields": deepcopy(fields)}
        self.calls.append(("create", key))
        if self.failure == "timeout" and fail:
            raise TimeoutError("Response lost after creation")
        if self.failure == "read" and fail:
            self.read_error = True
        return {} if self.failure == "no-key" and fail else {"key": key}

    def update_issue(self, key, fields):
        if self.failure == "reject":
            raise JiraError("Rejected", status_code=400)
        self.issues[key]["fields"].update(deepcopy(fields))
        self.calls.append(("update", key))
        if self.failure == "timeout":
            raise TimeoutError("Response lost after update")


def setup_backend(tmp_path, mode="safe_apply"):
    source, target = SourceJira(), TargetJira()
    clients = {"cloud": source, "gpk2": target}
    backend = EngineeringOpsBackend(client_getter=clients.__getitem__, settings=SimpleNamespace(mode=mode),
        execution_store=ExecutionHistory(tmp_path / "state.sqlite3"))
    return backend, source, target


def preview(backend, **overrides):
    return backend.create_execution_preview("sprint_placeholders", {**deepcopy(PARAMS), **overrides})


def apply(backend, **overrides):
    return backend.apply_sprint_placeholders(preview(backend, **overrides)["preview_id"])


def test_create_one_placeholder_per_mapped_user_with_points_and_source_links(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues += [source_issue("SBG-3", 2.5, "bob"), source_issue("SBG-4", 0, "alice")]
    record = preview(backend)
    plan = record["preview"]
    assert not target.calls
    assert [row["key"] for row in plan["missing_points"]] == ["SBG-2"]
    assert plan["action_count"] == 2
    result = backend.apply_sprint_placeholders(record["preview_id"])
    assert result["status"] == "succeeded"
    assert len(target.issues) == 2
    totals = {row["fields"]["assignee"]["name"]: row["fields"][POINTS_ID] for row in target.issues.values()}
    assert totals == {"alice": 3, "bob": 2.5}
    first = target.issues["GPK-1"]["fields"]
    assert first["summary"] == "SBG Jira Ops Work - Sprint Amber"
    assert first["reporter"] == {"name": "operator"}
    assert included_keys(first["description"], SOURCE_URL) == {"SBG-1", "SBG-4"}
    assert "SBG-2" not in first["description"]


def test_rerun_appends_newly_pointed_stories_once_and_adjusts_total(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    source.issues[1]["fields"][POINTS_ID] = 5
    record = preview(backend)
    row = record["preview"]["users"][0]
    assert row["action"] == "update" and row["total_points"] == 8
    assert row["already_included"] == ["SBG-1"]
    assert [story["key"] for story in row["new_stories"]] == ["SBG-2"]
    backend.apply_sprint_placeholders(record["preview_id"])
    for _ in range(3):
        current = preview(backend)
        assert current["preview"]["users"][0]["action"] == "unchanged"
        backend.apply_sprint_placeholders(current["preview_id"])
    assert target.calls == [("create", "GPK-1"), ("update", "GPK-1")]
    description = target.issues["GPK-1"]["fields"]["description"]
    assert description.count("[SBG-1|") == description.count("[SBG-2|") == 1
    assert target.issues["GPK-1"]["fields"][POINTS_ID] == 8


def test_rerun_uses_description_even_with_a_fresh_local_database(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    backend.execution_store = ExecutionHistory(tmp_path / "new-state.sqlite3")
    assert preview(backend)["preview"]["action_count"] == 0
    assert len(target.issues) == 1


def test_legacy_placeholder_links_are_adopted_and_manual_description_preserved(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    fields = target.issues["GPK-1"]["fields"]
    fields["labels"] = []
    fields["description"] = f"Keep these manual notes.\n[SBG-1]({SOURCE_URL}/browse/SBG-1)"
    fields[POINTS_ID] = 7
    source.issues[1]["fields"][POINTS_ID] = 2
    apply(backend)
    assert len(target.issues) == 1
    assert target.issues["GPK-1"]["fields"]["description"].startswith("Keep these manual notes.")
    assert target.issues["GPK-1"]["fields"][POINTS_ID] == 9


@pytest.mark.parametrize("description,expected", [
    (f"[SBG-1|{SOURCE_URL}/browse/SBG-1]", {"SBG-1"}),
    (f"[SBG-1]({SOURCE_URL}/browse/SBG-1)", {"SBG-1"}),
    (f"{SOURCE_URL}/browse/SBG-1. {SOURCE_URL}/browse/SBG-1", {"SBG-1"}),
    ("https://another.example.invalid/jira/browse/SBG-1", set()),
    ("https://cloud.example.invalid/other/browse/SBG-1", set()),
    ("https://cloud.example.invalid.evil.invalid/jira/browse/SBG-1", set()),
    ("SBG-1", set()),
])
def test_description_ledger_recognizes_only_real_links_to_selected_cloud(description, expected):
    assert included_keys(description, SOURCE_URL) == expected


@pytest.mark.parametrize("points", [None, "", -1, True, float("nan"), float("inf")])
def test_missing_or_invalid_points_are_reported_without_empty_placeholders(tmp_path, points):
    backend, source, target = setup_backend(tmp_path)
    source.issues = [source_issue("SBG-1", points)]
    record = preview(backend)
    assert len(record["preview"]["missing_points"]) == 1
    assert record["preview"]["action_count"] == 0
    backend.apply_sprint_placeholders(record["preview_id"])
    assert not target.calls


def test_unassigned_and_unmapped_users_are_visible_without_blocking_other_users(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues += [source_issue("SBG-3", 2, None), source_issue("SBG-4", 5, "bob")]
    source.issues[-1]["fields"]["assignee"].pop("emailAddress")
    record = preview(backend, user_mappings={"cloud-alice": "alice"})
    assert len(record["preview"]["unassigned"]) == 1
    bob = record["preview"]["users"][1]
    assert bob["action"] == "blocked" and bob["errors"]
    backend.apply_sprint_placeholders(record["preview_id"])
    assert len(target.issues) == 1


def test_mapping_collisions_and_unassignable_accounts_never_write(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues += [source_issue("SBG-3", 5, "bob")]
    record = preview(backend, user_mappings={"cloud-alice": "alice", "cloud-bob": "alice"})
    assert all(row["action"] == "blocked" for row in record["preview"]["users"])
    target.unassignable.add("alice")
    assert preview(backend)["preview"]["users"][0]["action"] == "blocked"
    assert not target.calls


def test_duplicate_existing_placeholders_block_instead_of_creating_another(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    target.issues["GPK-2"] = deepcopy(target.issues["GPK-1"])
    target.issues["GPK-2"]["key"] = "GPK-2"
    row = preview(backend)["preview"]["users"][0]
    assert row["action"] == "blocked"
    assert "Multiple" in row["errors"][0]
    assert len(target.calls) == 1


def test_reassignment_does_not_count_same_cloud_issue_in_second_users_placeholder(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    source.issues[0]["fields"]["assignee"] = {"accountId": "cloud-bob", "displayName": "Bob"}
    rows = preview(backend)["preview"]["users"]
    assert next(row for row in rows if row["assignee"] == "Bob")["action"] == "blocked"
    assert len(target.calls) == 1


@pytest.mark.parametrize("changed", ["source", "target", "metadata", "reporter", "connector"])
def test_apply_refuses_stale_previews(tmp_path, changed):
    backend, source, target = setup_backend(tmp_path)
    if changed == "target":
        apply(backend)
        source.issues[1]["fields"][POINTS_ID] = 2
    record = preview(backend)
    calls = list(target.calls)
    if changed == "source": source.issues[0]["fields"][POINTS_ID] = 20
    elif changed == "target": target.issues["GPK-1"]["fields"]["description"] += "\nManual edit"
    elif changed == "metadata": target.meta[POINTS_ID]["required"] = True
    elif changed == "reporter": target.reporter = "someone-else"
    else: target.cfg.base_url = "https://another-target.invalid"
    with pytest.raises(ValueError, match="changed|configuration"):
        backend.apply_sprint_placeholders(record["preview_id"])
    assert target.calls == calls


def test_default_mode_and_actor_binding_block_external_writes(tmp_path):
    backend, source, target = setup_backend(tmp_path, mode="recommend_only")
    record = preview(backend)
    assert not backend.apply_sprint_placeholders(record["preview_id"])["result"]["applied"]
    backend.settings.mode = "safe_apply"
    with actor_context("alice"): record = preview(backend)
    with actor_context("bob"), pytest.raises(ValueError, match="different actor"):
        backend.apply_sprint_placeholders(record["preview_id"])
    assert not target.calls


@pytest.mark.parametrize("failure", ["timeout", "no-key", "read"])
def test_lost_create_response_reconciles_without_duplicate_after_restart(tmp_path, failure):
    backend, source, target = setup_backend(tmp_path)
    record = preview(backend)
    target.failure = failure
    with pytest.raises((TimeoutError, RecoveryBlocked)):
        backend.apply_sprint_placeholders(record["preview_id"])
    assert backend.execution_store.get_record(record["preview_id"]).status == "recovery_required"
    backend.execution_store = ExecutionHistory(tmp_path / "state.sqlite3")
    target.read_error = False
    with pytest.raises(ValueError, match="overlapping"):
        backend.apply_sprint_placeholders(preview(backend)["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert target.calls == [("create", "GPK-1")]


def test_partial_multi_user_create_resumes_only_unconfirmed_work(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues.append(source_issue("SBG-3", 4, "bob"))
    record = preview(backend)
    target.failure, target.fail_user = "timeout", "bob"
    with pytest.raises(TimeoutError): backend.apply_sprint_placeholders(record["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert target.calls == [("create", "GPK-1"), ("create", "GPK-2")]


def test_lost_update_response_does_not_add_points_again(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    apply(backend)
    source.issues[1]["fields"][POINTS_ID] = 2
    record = preview(backend)
    target.failure = "timeout"
    with pytest.raises(TimeoutError): backend.apply_sprint_placeholders(record["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert target.issues["GPK-1"]["fields"][POINTS_ID] == 5
    assert target.calls == [("create", "GPK-1"), ("update", "GPK-1")]


def test_absent_uncertain_create_is_never_blindly_retried(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    record = preview(backend)
    target.failure = "timeout"
    with pytest.raises(TimeoutError): backend.apply_sprint_placeholders(record["preview_id"])
    target.hidden = True
    review = backend.reconcile_execution(record["preview_id"])
    assert not review["can_resume"]
    with pytest.raises(RecoveryBlocked): backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert len(target.calls) == 1


def test_explicitly_rejected_create_can_resume_after_reconciliation(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    record = preview(backend)
    target.failure = "reject"
    with pytest.raises(JiraError): backend.apply_sprint_placeholders(record["preview_id"])
    target.failure = None
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert len(target.calls) == 1


def test_inflight_previews_for_same_sprint_cannot_both_claim_scope(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    first, second = preview(backend), preview(backend)
    backend.execution_store.begin_apply(first["preview_id"])
    with pytest.raises(ValueError, match="overlapping"):
        backend.execution_store.begin_apply(second["preview_id"])


def test_new_placeholder_api_is_authenticated_and_shared_with_mcp(monkeypatch, tmp_path):
    import asyncio
    from starlette.testclient import TestClient
    import engineering_ops.api as api
    import engineering_ops.server as server
    from engineering_ops.config import settings

    backend, source, target = setup_backend(tmp_path, mode="recommend_only")
    source.boards = lambda *args, **kwargs: [{"id": 7, "name": "Cloud team"}]
    source.board_sprints = lambda board, **kwargs: [source.sprint(42)]
    source.cfg = SimpleNamespace(**vars(source.cfg), default_board_id=7)
    monkeypatch.setattr(api, "backend", backend)
    monkeypatch.setattr(server, "backend", backend)
    monkeypatch.setattr(settings, "mcp_bearer_token", "test-ops-token")
    mcp = server.create_mcp_server(validate_configuration=False)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {"preview_sprint_placeholders", "apply_sprint_placeholders"} <= names
    headers = {"Authorization": "Bearer test-ops-token"}
    with TestClient(mcp.streamable_http_app(), base_url="http://127.0.0.1:8080") as client:
        assert client.get("/api/sprint-placeholders/context?source_instance=cloud").status_code == 401
        context = client.get("/api/sprint-placeholders/context?source_instance=cloud", headers=headers)
        assert context.json()["sprints"][0]["name"] == "Sprint Amber"
        response = client.post("/api/executions/preview", headers=headers, json={"action": "sprint_placeholders", "parameters": PARAMS})
        assert response.status_code == 201
        record = response.json()
        assert record["preview"]["missing_points"][0]["key"] == "SBG-2"
        assert not record["preview"]["can_apply"]
        applied = client.post(f"/api/executions/{record['preview_id']}/apply", headers=headers)
        assert not applied.json()["result"]["applied"]
        assert client.get("/console/sprint-ops.js").status_code == 200
    assert not target.calls


def test_confirmed_completed_writes_can_finish_even_after_cloud_changes(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    record = preview(backend)
    target.failure = "timeout"
    with pytest.raises(TimeoutError): backend.apply_sprint_placeholders(record["preview_id"])
    source.issues[1]["fields"][POINTS_ID] = 3
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert preview(backend)["preview"]["users"][0]["total_points"] == 6


def test_missing_target_screen_fields_are_reported_per_user(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    del target.meta[POINTS_ID]
    record = preview(backend)
    assert record["preview"]["users"][0]["action"] == "blocked"
    assert record["preview"]["missing_points"][0]["key"] == "SBG-2"
    assert not target.calls


def test_source_connection_and_full_sprint_guards_are_enforced(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    with pytest.raises(ValueError, match="Cloud source"):
        preview(backend, source_instance="gpk2")
    def incomplete(*args, **kwargs):
        raise JiraError("Sprint count exceeds limit")
    source.sprint_issues = incomplete
    with pytest.raises(JiraError, match="exceeds limit"):
        preview(backend)
    assert not target.calls


def test_common_email_automatically_resolves_user_without_manual_mapping(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    record = preview(backend, user_mappings={})
    row = record["preview"]["users"][0]
    assert row["username"] == "alice@common.example.invalid"
    assert row["match_source"] == "email" and row["action"] == "create"
    backend.apply_sprint_placeholders(record["preview_id"])
    assert target.issues["GPK-1"]["fields"]["assignee"] == {"name": "alice@common.example.invalid"}


def test_hidden_email_is_flagged_instead_of_guessing_from_display_name(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    for issue in source.issues:
        issue["fields"]["assignee"].pop("emailAddress")
    record = preview(backend, user_mappings={})
    row = record["preview"]["users"][0]
    assert row["action"] == "blocked" and "email is unavailable" in row["errors"][0]
    assert not target.calls


def test_auto_email_must_be_assignable_and_collisions_are_blocked(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    target.unassignable.add("alice@common.example.invalid")
    assert preview(backend, user_mappings={})["preview"]["users"][0]["action"] == "blocked"
    target.unassignable.clear()
    bob = source_issue("SBG-3", 3, "bob")
    bob["fields"]["assignee"]["emailAddress"] = "alice@common.example.invalid"
    source.issues.append(bob)
    assert all(row["action"] == "blocked" for row in preview(backend, user_mappings={})["preview"]["users"])


def test_source_change_blocks_recovery_when_any_writes_remain_pending(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues.append(source_issue("SBG-3", 2, "bob"))
    record = preview(backend)
    target.failure, target.fail_user = "reject", "bob"
    with pytest.raises(JiraError): backend.apply_sprint_placeholders(record["preview_id"])
    source.issues[1]["fields"][POINTS_ID] = 3
    review = backend.reconcile_execution(record["preview_id"])
    assert not review["can_resume"] and "source:changed" in review["blocking_steps"]


def test_summary_embedded_links_cannot_silently_mark_other_stories_included(tmp_path):
    backend, source, target = setup_backend(tmp_path)
    source.issues[0]["fields"]["summary"] = f"See {SOURCE_URL}/browse/SBG-2"
    apply(backend)
    description = target.issues["GPK-1"]["fields"]["description"]
    assert included_keys(description, SOURCE_URL) == {"SBG-1"}


@pytest.mark.parametrize("profile,expected", [
    ({"accountId": "id", "emailAddress": "alice@example.invalid"}, "alice@example.invalid"),
    ({"accountId": "id", "name": "alice@example.invalid"}, "alice@example.invalid"),
    ({"accountId": "id", "displayName": "Alice"}, None),
])
def test_cloud_email_resolution_uses_visible_addresses_or_profile_read(profile, expected):
    from engineering_ops.adapters.jira import JiraClient
    calls = []
    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return {"accountId": "id", "displayName": "Alice"}
    client = SimpleNamespace(platform_api_version="3", request=request)
    assert JiraClient.user_email(client, profile) == expected
    assert len(calls) == (0 if expected else 1)


@pytest.mark.parametrize("status", [403, 404])
def test_hidden_cloud_email_is_reported_without_privileged_lookup(status):
    from engineering_ops.adapters.jira import JiraClient
    def denied(*args, **kwargs):
        raise JiraError("Hidden", status_code=status)
    client = SimpleNamespace(platform_api_version="3", request=denied)
    assert JiraClient.user_email(client, {"accountId": "id", "displayName": "Alice"}) is None


def test_exact_case_insensitive_target_username_must_be_active_and_assignable():
    from engineering_ops.adapters.jira import JiraClient
    calls = []
    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return [{"name": "Alice@Example.invalid", "active": True},
                {"name": "similar@example.invalid", "active": True}]
    client = SimpleNamespace(platform_api_version="2", request=request)
    assert JiraClient.assignable_user(client, "GPK", "alice@example.invalid")["name"] == "Alice@Example.invalid"
    assert calls[0][1]["params"]["project"] == "GPK"
    client.request = lambda *a, **kw: [{"name": "alice@example.invalid", "active": False}]
    with pytest.raises(ValueError, match="assignable"):
        JiraClient.assignable_user(client, "GPK", "alice@example.invalid")
