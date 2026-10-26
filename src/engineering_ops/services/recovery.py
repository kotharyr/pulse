"""Write-ahead mutation receipts and read-only reconciliation. Never retry a blind create."""
from engineering_ops.adapters.jira import JiraError
from engineering_ops.services.issue_validation import reporter_matches


class RecoveryBlocked(ValueError):
    pass


class BeforeWriteBlocked(RecoveryBlocked):
    pass


def run_step(store, preview_id, step_id, kind, request, fn):
    previous = store.start_step(preview_id, step_id, kind, request)
    if previous is not None:
        return previous["value"]
    try:
        value = fn()
        receipt = {"value": value}
        store.finish_step(preview_id, step_id, "succeeded", receipt)
        return value
    except Exception as exc:
        # Only explicit rejection responses prove the mutation did not happen.
        rejected = isinstance(exc, BeforeWriteBlocked) or (isinstance(exc, JiraError) and exc.status_code in {400, 401, 403, 404, 409, 422, 429})
        store.finish_step(preview_id, step_id, "not_applied" if rejected else "uncertain", error=type(exc).__name__)
        raise


def observe_step(jira, step):
    req, kind = step["request"], step["kind"]
    if kind == "ops_placeholder":
        from engineering_ops.services.sprint_placeholders import observe_placeholder
        return observe_placeholder(jira, req)
    if kind == "create_issue":
        rows = jira.search(f'labels = "{req["marker"]}"', ["summary", "project", "labels", "reporter"], 2)
        if len(rows) == 1:
            fields = rows[0].get("fields") or {}
            if fields.get("summary") == req["summary"] and (fields.get("project") or {}).get("key") == req["project"]:
                if req.get("reporter_version"):
                    if not reporter_matches(jira, rows[0]["key"], req["reporter_version"]):
                        return {"state": "conflict", "reason": "Created issue reporter differs from reviewed account"}
                return {"state": "applied", "value": {"key": rows[0]["key"]}}
        # A missing search result can be indexing delay. Only a prior explicit
        # rejection makes an absent result retryable; ambiguity never does.
        if not rows:
            return {"state": "absent", "reason": "No created issue is currently visible for the operation marker"}
        return {"state": "conflict", "reason": "Issue creation is not uniquely confirmed by its operation marker"}
    if kind == "transition":
        issue = jira.get_issue(req["issue_key"], ["status"])
        status = (issue.get("fields") or {}).get("status") or {}
        if status.get("name", "").casefold() == req["status"].casefold() and (status.get("statusCategory") or {}).get("key") == "done":
            return {"state": "applied", "value": {"issue_key": req["issue_key"], "to_status": req["status"]}}
        return {"state": "pending", "observed": status}
    if kind == "move":
        rows = jira.sprint_issues(req["sprint_id"])
        found = sorted(set(req["issue_keys"]) & {r["key"] for r in rows})
        if len(found) == len(req["issue_keys"]):
            return {"state": "applied", "value": [{"count": len(found), "issues": found}]}
        return {"state": "pending", "observed_keys": found}
    if kind == "close_sprint":
        sprint = jira.sprint(req["sprint_id"])
        if sprint.get("state") == "closed":
            return {"state": "applied", "value": sprint}
        return {"state": "pending", "observed": sprint}
    if kind in {"date", "labels", "field_update"}:
        fields = jira.get_issue(req["issue_key"], None).get("fields") or {}
        if kind == "labels":
            labels = set(fields.get("labels") or [])
            if set(req["add"]) <= labels and not (set(req["remove"]) & labels):
                return {"state": "applied", "value": {"issue_key": req["issue_key"], "change_id": req["change_id"], "ok": True}}
            qp = sorted(str(v) for v in labels if str(v).casefold().startswith("qp-"))
            if qp == req["expected_qp"]:
                return {"state": "pending", "observed": sorted(labels)}
            return {"state": "conflict", "reason": "Source commitment labels changed"}
        names = {row["name"]: row["id"] for row in jira.fields()}
        def displayed(value):
            if isinstance(value, list):
                return [displayed(item) for item in value]
            if isinstance(value, dict):
                return value.get("value") or value.get("name") or value.get("displayName")
            return value
        actual = {name: displayed(fields.get(names[name])) for name in req["values"]}
        if actual == req["values"]:
            value = {"issue_key": req["issue_key"], "ok": True}
            if "change_id" in req:
                value["change_id"] = req["change_id"]
            return {"state": "applied", "value": value}
        if actual == req["before"]:
            return {"state": "pending", "observed": actual}
        return {"state": "conflict", "reason": "Source field values changed"}
    return {"state": "unknown", "reason": "Unsupported journal step"}


def reconcile(store, jira, preview_id):
    record = store.prepare_reconciliation(preview_id)
    observations, blocking = [], []
    for step in record["steps"]:
        try:
            observed = observe_step(jira, step)
        except Exception as exc:
            observed = {"state": "unknown", "reason": type(exc).__name__}
        if observed["state"] == "applied":
            store.finish_step(preview_id, step["step_id"], "succeeded", {"value": observed["value"]}, reconciling=True)
        elif step["status"] == "succeeded":
            blocking.append(step["step_id"])
            observed = {**observed, "state": "conflict", "reason": "Previously confirmed effect has changed"}
        elif (step["kind"] == "create_issue" or (
            step["kind"] == "ops_placeholder" and step["request"]["operation"] == "create"
        )) and step["status"] == "not_applied":
            # An explicit rejection plus no observed issue makes this create retryable.
            if observed["state"] != "absent":
                blocking.append(step["step_id"])
        elif observed["state"] == "pending":
            store.finish_step(preview_id, step["step_id"], "pending", reconciling=True)
        else:
            blocking.append(step["step_id"])
        observations.append({"step_id": step["step_id"], **observed})
    result = {"preview_id": preview_id, "observations": observations, "blocking_steps": blocking}
    return result
