from copy import deepcopy
import multiprocessing
from pathlib import Path
from types import SimpleNamespace

import pytest

from engineering_ops.adapters.jira import JiraError
from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.services.audit import AuditTrail
from engineering_ops.services.executions import ExecutionHistory
from engineering_ops.services.identity import actor_context
from engineering_ops.services.recovery import RecoveryBlocked
from test_reliability_regressions import SprintJira
from test_portfolio_hygiene import FakePortfolioBackend, FakePortfolioJira


def _claim_worker(path, preview_id, queue):
    history = ExecutionHistory(path)
    try:
        history.begin_apply(preview_id)
        queue.put("claimed")
    except ValueError:
        queue.put("blocked")


def history_preview(store, actor="alice", **overrides):
    with actor_context(actor):
        return store.add_preview(overrides.get("action", "field_updates"), overrides.get("instance", "fake"),
            {"instance": "fake"}, {"preview_id": "state", "issues": [{"issue_key": "A-1"}], "source_versions": {"A-1": "version"}})


def test_history_and_audit_survive_reopen(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = ExecutionHistory(path)
    record = history_preview(first)
    with actor_context("alice"):
        first.begin_apply(record["preview_id"])
    first.mark_applied(record["preview_id"], {"applied": True})
    reopened = ExecutionHistory(path)
    assert reopened.get_record(record["preview_id"]).status == "succeeded"
    events = AuditTrail(path).list()
    assert events[0]["actor"] == "alice"
    assert {e["action"] for e in events} >= {"approval_preview_created", "approval_apply_started", "approval_apply_finished"}
    assert path.stat().st_mode & 0o777 == 0o600


def test_two_processes_cannot_claim_same_review(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = ExecutionHistory(path)
    record = history_preview(store, actor="local")
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    workers = [ctx.Process(target=_claim_worker, args=(str(path), record["preview_id"], queue)) for _ in range(2)]
    for worker in workers: worker.start()
    for worker in workers:
        worker.join(15)
        assert worker.exitcode == 0
    assert sorted(queue.get(timeout=3) for _ in workers) == ["blocked", "claimed"]
    # Both workers have exited; explicit reconciliation can now recover the claim.
    assert store.prepare_reconciliation(record["preview_id"])["status"] == "recovery_required"


@pytest.mark.parametrize("mismatch", ["actor", "action", "instance"])
def test_approval_scope_is_checked_before_consumption(tmp_path, mismatch):
    store = ExecutionHistory(tmp_path / "state.sqlite3")
    record = history_preview(store)
    with actor_context("mallory" if mismatch == "actor" else "alice"):
        with pytest.raises(ValueError):
            store.begin_apply(record["preview_id"], action="close_sprint" if mismatch == "action" else "field_updates",
                              instance="other" if mismatch == "instance" else "fake")
    assert store.get_record(record["preview_id"]).status == "previewed"


def test_equivalent_previews_cannot_duplicate_completed_operation(tmp_path):
    store = ExecutionHistory(tmp_path / "state.sqlite3")
    first = history_preview(store)
    second = history_preview(store)
    with actor_context("alice"):
        store.begin_apply(first["preview_id"])
        store.mark_applied(first["preview_id"], {"applied": True})
        with pytest.raises(ValueError, match="equivalent or overlapping"):
            ExecutionHistory(tmp_path / "state.sqlite3").begin_apply(second["preview_id"])


def test_active_worker_cannot_be_reconciled(tmp_path):
    store = ExecutionHistory(tmp_path / "state.sqlite3")
    record = history_preview(store, actor="local")
    store.begin_apply(record["preview_id"])
    with pytest.raises(ValueError, match="still running"):
        store.prepare_reconciliation(record["preview_id"])


class RecoverableJira(SprintJira):
    def __init__(self, fail_step=None, phase="after"):
        super().__init__()
        self.issues[0]["fields"]["project"] = {"key": "ENG"}
        self.issues[0]["fields"]["status"]["statusCategory"] = {"key": "indeterminate"}
        second = deepcopy(self.issues[0])
        second["key"] = "ENG-2"
        self.issues.append(second)
        self.all_issues = {row["key"]: row for row in self.issues}
        self.target_keys = []
        self.fail_step, self.phase, self.fired = fail_step, phase, False
        self.calls = []

    def mutate(self, step, effect):
        self.calls.append(step)
        if step == self.fail_step and not self.fired and self.phase == "before":
            self.fired = True
            raise JiraError("Rejected before mutation", status_code=400)
        value = effect()
        if step == self.fail_step and not self.fired:
            self.fired = True
            raise TimeoutError("Response lost after mutation")
        return value

    def get_issue(self, key, fields=None):
        return deepcopy(self.all_issues[key])

    def search(self, jql, fields, limit):
        marker = jql.split('"')[1]
        return [deepcopy(row) for row in self.all_issues.values() if marker in row["fields"].get("labels", [])][:limit]

    def description_value(self, text): return text

    def create_issue(self, fields):
        def effect():
            key = "ENG-100"
            assert key not in self.all_issues, "Duplicate split issue"
            self.all_issues[key] = {"key": key, "fields": deepcopy(fields)}
            return {"key": key}
        return self.mutate("create", effect)

    def transition_issue_to_status(self, key, status):
        def effect():
            self.all_issues[key]["fields"]["status"] = {"name": status, "statusCategory": {"key": "done"}}
            return {"issue_key": key, "to_status": status}
        return self.mutate("transition", effect)

    def sprint_issues(self, sprint_id, story_points_field_id=None):
        rows = self.target_keys if sprint_id == 2 else [key for key in ["ENG-1", "ENG-2"] if key not in self.target_keys]
        return [deepcopy(self.all_issues[key]) for key in rows]

    def move_issues_to_sprint(self, sprint_id, keys):
        def effect():
            self.target_keys = list(dict.fromkeys(self.target_keys + keys))
            return [{"count": len(keys), "issues": keys}]
        return self.mutate("move:" + keys[0], effect)

    def update_sprint(self, sprint_id, fields):
        def effect():
            self.sprints[sprint_id].update(fields)
            return deepcopy(self.sprints[sprint_id])
        return self.mutate("close", effect)


def sprint_backend(tmp_path, jira):
    store = ExecutionHistory(tmp_path / "state.sqlite3")
    return EngineeringOpsBackend(client_getter=lambda _: jira, execution_store=store, audit_trail=AuditTrail(store.db),
        settings=SimpleNamespace(mode="approved_destructive", bulk_batch_size=1))


def sprint_record(backend):
    return backend.create_execution_preview("close_sprint", {
        "instance": "fake", "sprint_id": 1, "next_sprint_id": 2, "move_issue_keys": ["ENG-2"],
        "split_plans": [{"source_issue_key": "ENG-1", "new_summary": "Follow on", "source_transition_status": "Done"}],
    })


@pytest.mark.parametrize("step", ["create", "transition", "move:ENG-2", "move:ENG-100", "close"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_sprint_recovers_every_mutation_boundary_without_duplicate_creation(tmp_path, step, phase):
    jira = RecoverableJira(step, phase)
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises((JiraError, TimeoutError)):
        backend.apply_execution_preview(record["preview_id"])
    persisted = backend.execution_store.get_record(record["preview_id"]).to_dict()
    assert persisted["status"] == "recovery_required"
    assert persisted["steps"]
    # A fresh worker uses the same database, not a process-local cache.
    backend = sprint_backend(tmp_path, jira)
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"], review
    result = backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert result["status"] == "succeeded"
    assert jira.sprints[1]["state"] == "closed"
    assert len(jira.all_issues) == 3
    assert set(jira.target_keys) == {"ENG-2", "ENG-100"}
    assert jira.calls.count("create") == (2 if step == "create" and phase == "before" else 1)
    with pytest.raises(ValueError, match="succeeded"):
        backend.apply_execution_preview(record["preview_id"])


def test_uncertain_create_is_never_blindly_retried(tmp_path):
    jira = RecoverableJira()
    def timeout(fields):
        jira.calls.append("create")
        raise TimeoutError("Unknown whether created")
    jira.create_issue = timeout
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises(TimeoutError): backend.apply_execution_preview(record["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    assert not review["can_resume"]
    with pytest.raises(RecoveryBlocked): backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert jira.calls == ["create"]


def test_recovery_review_refuses_new_source_drift(tmp_path):
    jira = RecoverableJira("create", "before")
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises(JiraError): backend.apply_execution_preview(record["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    jira.all_issues["ENG-2"]["fields"]["summary"] = "Changed by someone else"
    with pytest.raises(RecoveryBlocked): backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert jira.calls == ["create"]


def test_sprint_apply_cannot_accept_a_field_update_review(tmp_path):
    from test_platform_contracts import FakeFieldUpdateJira
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira)
    record = backend.create_execution_preview("field_updates", {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}})
    result = backend.sprint_close_apply_workflow(record["preview_id"])
    assert result["sections"]["result"].get("applied") is not True
    assert jira.updated == []
    assert backend.execution_store.get_record(record["preview_id"]).status == "previewed"


@pytest.mark.parametrize("category", ["dates", "labels"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_hygiene_recovers_after_each_individual_change(tmp_path, category, phase):
    # Inject at every change boundary, using an independent database for each case.
    for fail_index in range(4 if category == "dates" else 2):
        jira = FakePortfolioJira()
        fake = FakePortfolioBackend(jira, mode="safe_apply")
        store = ExecutionHistory(tmp_path / f"{category}-{fail_index}.sqlite3")
        backend = EngineeringOpsBackend(client_getter=lambda _: jira, settings=fake.settings,
                                       execution_store=store, audit_trail=AuditTrail(store.db))
        record = backend.portfolio_hygiene_preview_fix(instance="onprem", categories=[category])
        count = 0
        fired = False
        original = jira.update_issue if category == "dates" else jira.update_issue_operations
        def mutation(*args):
            nonlocal count, fired
            this = count
            count += 1
            if this == fail_index and not fired and phase == "before":
                fired = True
                raise JiraError("Rejected", status_code=400)
            value = original(*args)
            if this == fail_index and not fired:
                fired = True
                raise TimeoutError("Response lost")
            return value
        if category == "dates": jira.update_issue = mutation
        else: jira.update_issue_operations = mutation
        with pytest.raises((JiraError, TimeoutError)):
            backend.apply_execution_preview(record["preview_id"])
        review = backend.reconcile_execution(record["preview_id"])
        assert review["can_resume"], review
        result = backend.resume_execution(record["preview_id"], review["recovery_id"])
        assert result["status"] == "succeeded"
        writes = jira.updated_fields if category == "dates" else jira.updated_operations
        assert len(writes) == record["preview"]["change_count"]


def test_low_level_hash_is_not_an_approval(tmp_path):
    from test_platform_contracts import FakeFieldUpdateJira
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira, settings=SimpleNamespace(mode="safe_apply", max_search_results=100))
    raw, _ = backend._build_field_update_preview("fake", "project = ENG", {"Target Quarter": "FY27 Q1"}, 500)
    result = backend.apply_field_updates("fake", "project = ENG", {"Target Quarter": "FY27 Q1"}, preview_id=raw["preview_id"])
    assert not result["applied"]
    assert jira.updated == []


def test_recovery_blocks_new_current_sprint_work(tmp_path):
    jira = RecoverableJira("create", "before")
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises(JiraError): backend.apply_execution_preview(record["preview_id"])
    original = jira.sprint_issues
    def with_new_work(sprint_id, story_points_field_id=None):
        rows = original(sprint_id, story_points_field_id)
        if sprint_id == 1:
            rows.append({"key": "ENG-3", "fields": {"summary": "New work"}})
        return rows
    jira.sprint_issues = with_new_work
    review = backend.reconcile_execution(record["preview_id"])
    assert not review["can_resume"]
    assert "source:unreviewed-issues" in review["blocking_steps"]


def test_actor_binding_uses_authenticated_identity_not_headers(monkeypatch, tmp_path):
    from starlette.testclient import TestClient
    import engineering_ops.api as api
    from engineering_ops.config import settings
    from engineering_ops.server import create_mcp_server
    from test_platform_contracts import FakeFieldUpdateJira
    store = ExecutionHistory(tmp_path/"state.sqlite3")
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira, execution_store=store)
    monkeypatch.setattr(api, "backend", backend)
    monkeypatch.setattr(settings, "mcp_bearer_token", "first-token")
    with TestClient(create_mcp_server(validate_configuration=False).streamable_http_app(), base_url="http://127.0.0.1:8080") as client:
        record = client.post("/api/executions/preview", headers={"Authorization": "Bearer first-token", "X-Pulse-Actor": "forged"},
            json={"action": "field_updates", "parameters": {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}}}).json()
    assert record["actor"].startswith("token:")
    assert "first-token" not in str(record)
    monkeypatch.setattr(settings, "mcp_bearer_token", "second-token")
    with TestClient(create_mcp_server(validate_configuration=False).streamable_http_app(), base_url="http://127.0.0.1:8080") as client:
        denied = client.post(f"/api/executions/{record['preview_id']}/apply", headers={"Authorization": "Bearer second-token", "X-Pulse-Actor": record["actor"]})
    assert denied.status_code == 400
    assert "different actor" in denied.json()["error"]
    assert jira.updated == []


def _crash_after_create(path, preview_id, request, effect_path):
    import os
    from engineering_ops.services.recovery import run_step
    store = ExecutionHistory(path)
    store.begin_apply(preview_id)
    def create_then_die():
        Path(effect_path).write_text("created")
        os._exit(7)
    run_step(store, preview_id, "create:0", "create_issue", request, create_then_die)


def test_process_crash_after_create_reconciles_started_receipt(tmp_path):
    jira = RecoverableJira()
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    request = {"marker": record["preview"]["split_plans"][0]["recovery_label"], "summary": "Follow on", "project": "ENG"}
    process = multiprocessing.get_context("spawn").Process(target=_crash_after_create,
        args=(str(tmp_path/"state.sqlite3"), record["preview_id"], request, str(tmp_path/"effect")))
    process.start()
    process.join(15)
    assert process.exitcode == 7
    assert (tmp_path/"effect").exists()
    assert backend.execution_store.steps(record["preview_id"])[0]["status"] == "started"
    jira.all_issues["ENG-100"] = {"key": "ENG-100", "fields": {
        "summary": "Follow on", "project": {"key": "ENG"}, "labels": [request["marker"]]}}
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    assert backend.resume_execution(record["preview_id"], review["recovery_id"])["status"] == "succeeded"
    assert "create" not in jira.calls


def test_recovery_endpoints_require_review_and_resume_without_repeating_steps(monkeypatch, tmp_path):
    from starlette.testclient import TestClient
    import engineering_ops.api as api
    from engineering_ops.config import settings
    from engineering_ops.server import create_mcp_server
    jira = RecoverableJira("close", "after")
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises(TimeoutError): backend.apply_execution_preview(record["preview_id"])
    monkeypatch.setattr(api, "backend", backend)
    monkeypatch.setattr(settings, "mcp_bearer_token", None)
    app = create_mcp_server(validate_configuration=False).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        assert client.post(f"/api/executions/{record['preview_id']}/resume", json={}).status_code == 400
        assert client.post("/api/executions/missing/reconcile").status_code == 404
        review = client.post(f"/api/executions/{record['preview_id']}/reconcile").json()
        calls_before = list(jira.calls)
        result = client.post(f"/api/executions/{record['preview_id']}/resume", json={"recovery_id": review["recovery_id"]})
        assert result.json()["status"] == "succeeded"
        assert jira.calls == calls_before


@pytest.mark.parametrize("phase", ["before", "after"])
def test_field_update_recovery_does_not_repeat_confirmed_updates(tmp_path, phase):
    from test_platform_contracts import FakeFieldUpdateJira
    class MutableFieldJira(FakeFieldUpdateJira):
        current = "FY26 Q4"
        fired = False
        def search(self, jql, fields, limit):
            return [{"key": "ENG-1", "fields": {"summary": "Work", "customfield_10001": {"value": self.current}}}]
        def get_issue(self, key, fields=None): return self.search("", [], 1)[0]
        def update_issue(self, key, fields):
            if not self.fired and phase == "before":
                self.fired = True
                raise JiraError("Rejected", status_code=400)
            self.current = "FY27 Q1"
            self.updated.append((key, fields))
            if not self.fired:
                self.fired = True
                raise TimeoutError("Response lost")
    jira = MutableFieldJira()
    store = ExecutionHistory(tmp_path/"fields.sqlite3")
    backend = EngineeringOpsBackend(client_getter=lambda _: jira, execution_store=store,
        settings=SimpleNamespace(mode="safe_apply", max_search_results=100))
    record = backend.create_execution_preview("field_updates", {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}})
    with pytest.raises((JiraError, TimeoutError)): backend.apply_execution_preview(record["preview_id"])
    review = backend.reconcile_execution(record["preview_id"])
    assert review["can_resume"]
    result = backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert result["status"] == "succeeded"
    assert len(jira.updated) == 1


@pytest.mark.parametrize("scenario", ["ambiguous", "search_failure"])
def test_rejected_create_still_blocks_ambiguous_or_unavailable_reconciliation(tmp_path, scenario):
    jira = RecoverableJira("create", "before")
    backend = sprint_backend(tmp_path, jira)
    record = sprint_record(backend)
    with pytest.raises(JiraError): backend.apply_execution_preview(record["preview_id"])
    def unavailable(*args):
        if scenario == "search_failure": raise JiraError("Unavailable", status_code=503)
        return [{"key": "ENG-50", "fields": {}}, {"key": "ENG-51", "fields": {}}]
    jira.search = unavailable
    review = backend.reconcile_execution(record["preview_id"])
    assert not review["can_resume"]
    with pytest.raises(RecoveryBlocked): backend.resume_execution(record["preview_id"], review["recovery_id"])
    assert jira.calls == ["create"]


def test_reconciliation_cannot_alter_steps_after_a_worker_resumes(tmp_path):
    store = ExecutionHistory(tmp_path/"state.sqlite3")
    record = history_preview(store, actor="local")
    store.begin_apply(record["preview_id"])
    store.start_step(record["preview_id"], "one", "date", {})
    with pytest.raises(ValueError, match="resumed during reconciliation"):
        store.finish_step(record["preview_id"], "one", "pending", reconciling=True)
    assert store.steps(record["preview_id"])[0]["status"] == "started"


def test_approval_binds_actual_jira_target_not_only_instance_name(tmp_path):
    from test_platform_contracts import FakeFieldUpdateJira
    jira = FakeFieldUpdateJira()
    jira.cfg = SimpleNamespace(**vars(jira.cfg), base_url="https://original.example.invalid")
    backend = EngineeringOpsBackend(client_getter=lambda _: jira,
        settings=SimpleNamespace(mode="safe_apply", max_search_results=100))
    record = backend.create_execution_preview("field_updates", {"instance": "same-name", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}})
    jira.cfg.base_url = "https://another.example.invalid"
    with pytest.raises(ValueError, match="configuration changed"):
        backend.apply_execution_preview(record["preview_id"])
    assert jira.updated == []
    assert backend.execution_store.get_record(record["preview_id"]).status == "previewed"


def test_mcp_and_rest_share_the_same_authenticated_approval_actor(monkeypatch, tmp_path):
    import json
    from starlette.testclient import TestClient
    import engineering_ops.api as api
    import engineering_ops.server as server
    from engineering_ops.config import settings
    from engineering_ops.services.identity import token_actor
    from test_platform_contracts import FakeFieldUpdateJira
    jira = FakeFieldUpdateJira()
    backend = EngineeringOpsBackend(client_getter=lambda _: jira, execution_store=ExecutionHistory(tmp_path/"mcp.sqlite3"),
        settings=SimpleNamespace(mode="safe_apply", max_search_results=100))
    monkeypatch.setattr(server, "backend", backend)
    monkeypatch.setattr(api, "backend", backend)
    monkeypatch.setattr(settings, "mcp_bearer_token", "shared-test-credential")
    app = server.create_mcp_server(validate_configuration=False).streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer shared-test-credential"}
    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        initialized = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "actor-test", "version": "1"}}})
        headers["mcp-session-id"] = initialized.headers["mcp-session-id"]
        client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "preview_field_updates", "arguments": {"instance": "fake", "jql": "project = ENG", "updates": {"Target Quarter": "FY27 Q1"}}}})
        message = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))
        assert not message["result"]["isError"], message
        preview = json.loads(message["result"]["content"][0]["text"])
        record = backend.execution_store.get_record(preview["preview_id"]).to_dict()
        assert record["actor"] == token_actor("shared-test-credential")
        applied = client.post(f"/api/executions/{preview['preview_id']}/apply", headers={"Authorization": "Bearer shared-test-credential"})
        assert applied.status_code == 200
        assert applied.json()["status"] == "succeeded"
        assert len(jira.updated) == 1
