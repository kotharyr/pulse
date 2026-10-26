"""Preview and journal per-user GPK2 placeholders for a Cloud sprint.

Descriptions, not local state, determine which Cloud issues have been included.
Local execution state supplies approval, concurrency control and crash recovery.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from engineering_ops.services.creation_fields import (
    resolve_additional_fields, validate_create_screen, validate_required_fields,
)
from engineering_ops.services.executions import fingerprint
from engineering_ops.services.fields import resolve_field
from engineering_ops.services.placeholder_ledger import (
    PlaceholderRequest, SourceStory, append_stories, included_keys, points_value,
    source_link, sum_points,
)
from engineering_ops.services.recovery import RecoveryBlocked, run_step

if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient
    from engineering_ops.backend import EngineeringOpsBackend


ACTION = "sprint_placeholders"
SCOPE_PREFIX = "pulse-ops-sprint-"


def source_snapshot(source: JiraClient, sprint_id: int) -> tuple[dict, list[SourceStory], str]:
    sprint = source.sprint(sprint_id)
    points_id = resolve_field(source, source.cfg.story_points_field_name)["id"]
    issues = source.sprint_issues(sprint_id, story_points_field_id=points_id)
    stories = []
    emails = {}
    for issue in sorted(issues, key=lambda row: row["key"]):
        fields = issue.get("fields") or {}
        assignee = fields.get("assignee") or {}
        identity = assignee.get("accountId") or assignee.get("emailAddress") or ""
        if identity not in emails:
            emails[identity] = source.user_email(assignee) if assignee else None
        email = emails[identity]
        stories.append(SourceStory(
            key=issue["key"], summary=fields.get("summary") or issue["key"],
            url=source_link(source.cfg.base_url, issue["key"]),
            account_id=assignee.get("accountId") or ("email:" + email.casefold() if email else None),
            assignee=assignee.get("displayName") or email or "Unassigned",
            email=email,
            points=points_value(fields.get(points_id)),
        ))
    version = fingerprint({"sprint": sprint, "issues": sorted(issues, key=lambda row: row["key"]), "emails": emails})
    return sprint, stories, version


def scope_label(source: JiraClient, target: JiraClient, request: PlaceholderRequest) -> str:
    return SCOPE_PREFIX + fingerprint({
        "source": source.cfg.base_url, "target": target.cfg.base_url,
        "sprint": request.sprint_id, "project": request.project.upper(),
    })[:24]


def placeholder_marker(scope: str, account_id: str) -> str:
    return "pulse-ops-item-" + fingerprint([scope, account_id])[:32]


def destination_candidates(target: JiraClient, project: str, scope: str, title: str) -> list[dict]:
    query = f'project = "{project}" AND (labels = "{scope}" OR summary ~ "SBG Jira Ops Work")'
    rows = target.search(query, ["summary", "labels", "assignee", "project"], 5001)
    if len(rows) > 5000:
        raise ValueError("Too many destination placeholders; refusing an incomplete reconciliation")
    candidates = []
    for row in rows:
        fields = row.get("fields") or {}
        labels = fields.get("labels") or []
        other_scope = any(label.startswith(SCOPE_PREFIX) and label != scope for label in labels)
        if not other_scope and (scope in labels or fields.get("summary") == title):
            # Read directly rather than trusting the lagging search index's description.
            candidates.append(target.get_issue(row["key"], None))
    return candidates


def issue_state(target: JiraClient, issue: dict) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    points_id = resolve_field(target, target.cfg.story_points_field_name)["id"]
    return {
        "project": (fields.get("project") or {}).get("key"),
        "summary": fields.get("summary"), "description": fields.get("description") or "",
        "points": points_value(fields.get(points_id)),
        "assignee": (fields.get("assignee") or {}).get("name"),
        "reporter": (fields.get("reporter") or {}).get("name"),
        "labels": sorted(fields.get("labels") or []),
    }


def find_existing(candidates: list[dict], marker: str, username: str) -> dict | None:
    matches = [row for row in candidates if marker in ((row.get("fields") or {}).get("labels") or [])]
    if not matches:
        matches = [row for row in candidates if
                   ((row.get("fields") or {}).get("assignee") or {}).get("name", "").casefold() == username.casefold()]
    if len(matches) > 1:
        raise ValueError("Multiple placeholders match this user; reconcile them before continuing")
    return matches[0] if matches else None


def writable_fields(target: JiraClient, request: PlaceholderRequest, row: dict) -> tuple[dict, str]:
    points_id = resolve_field(target, target.cfg.story_points_field_name)["id"]
    if row["action"] == "create":
        metadata = target.creation_metadata(request.project.upper(), request.issue_type)
        meta = metadata["fields"]
        validate_create_screen(meta)
        required = ["assignee", points_id]
        for key in required:
            if key not in meta or "set" not in meta[key].get("operations", ["set"]):
                raise ValueError("The create screen must allow Assignee and the configured Story Points field")
        fields = {
            "project": {"key": request.project.upper()},
            "issuetype": {"id": metadata["issue_type"]["id"]},
            "summary": row["title"], "description": row["description"],
            "assignee": {"name": row["username"]}, points_id: row["total_points"],
            "labels": row["labels"], "reporter": target.reporter_value(target.myself()),
        }
        extras = resolve_additional_fields(meta, request.additional_fields)
        if fields.keys() & extras.keys():
            raise ValueError("Additional fields cannot override placeholder accounting or ownership")
        fields.update(extras)
        validate_required_fields(meta, fields)
        return fields, fingerprint({"metadata": metadata, "reporter": fields["reporter"]})
    metadata = target.editmeta(row["issue_key"])
    fields = {"description": row["description"], points_id: row["total_points"], "labels": row["labels"]}
    for key in fields:
        field = metadata.get("fields", {}).get(key)
        if not field or "set" not in field.get("operations", ["set"]):
            raise ValueError("The placeholder edit screen must allow Description, Labels and Story Points")
    return fields, fingerprint(metadata)


def plan_user(
    target: JiraClient, source: JiraClient, request: PlaceholderRequest,
    sprint: dict, candidates: list[dict], ledger: dict[str, set[str]],
    stories: list[SourceStory], account_id: str, scope: str, title: str,
) -> dict:
    username = request.user_mappings.get(account_id) or stories[0].email
    row = {
        "cloud_account": account_id, "assignee": stories[0].assignee,
        "username": username, "match_source": "override" if account_id in request.user_mappings else "email", "action": "blocked", "issue_key": None,
        "title": title, "new_stories": [], "already_included": [],
        "added_points": 0, "total_points": 0, "errors": [],
        "marker": placeholder_marker(scope, account_id),
    }
    if not username:
        row["errors"].append("Cloud email is unavailable. Make it visible to this Jira connection or provide an optional username override")
        return row
    try:
        user = target.assignable_user(request.project.upper(), username)
        row["username"] = user["name"]
        existing = find_existing(candidates, row["marker"], row["username"])
        before = issue_state(target, existing) if existing else None
        if before and (before["assignee"] or "").casefold() != row["username"].casefold():
            raise ValueError("The existing placeholder is assigned to another user; reconcile ownership first")
        if before and before["project"] != request.project.upper():
            raise ValueError("The matching placeholder belongs to another project")
        if before and not isinstance(before["description"], str):
            raise ValueError("The existing placeholder description is not readable Jira text")
        row["issue_key"] = existing["key"] if existing else None
        existing_links = included_keys(before["description"], source.cfg.base_url) if before else set()
        additions = []
        for story in stories:
            owners = ledger.get(story.key, set())
            if owners - {row["issue_key"]}:
                raise ValueError(f"{story.key} is already linked in another user's placeholder")
            if story.key in existing_links:
                row["already_included"].append(story.key)
            elif story.points is not None:
                additions.append(story)
        if not additions:
            row["action"] = "unchanged"
            row["total_points"] = before["points"] if before else 0
            return row
        if before and before["points"] is None:
            raise ValueError("The existing placeholder has no valid points total; reconcile it before appending")
        row["new_stories"] = [story.public() for story in additions]
        row["added_points"] = sum_points([story.points for story in additions])
        row["total_points"] = sum_points([before["points"] if before else 0, row["added_points"]])
        row["action"] = "update" if before else "create"
        row["description"] = append_stories(before["description"] if before else "", additions, sprint)
        row["labels"] = sorted(set((before["labels"] if before else []) + [scope, row["marker"]]))
        row["before_version"] = fingerprint(before) if before else None
        fields, metadata_version = writable_fields(target, request, row)
        row["metadata_version"] = metadata_version
        row["payload_version"] = fingerprint(fields)
        after = dict(before or {})
        after.update({
            "project": request.project.upper(), "summary": before["summary"] if before else title,
            "description": row["description"], "points": row["total_points"],
            "assignee": before["assignee"] if before else row["username"], "labels": row["labels"],
            "reporter": before["reporter"] if before else fields["reporter"]["name"],
        })
        row["after_version"] = fingerprint(after)
    except ValueError as exc:
        row["action"] = "blocked"
        row["errors"].append(str(exc))
    return row


def prepare(backend: EngineeringOpsBackend, parameters: dict) -> dict:
    request = PlaceholderRequest.model_validate(parameters)
    source, target = backend.client(request.source_instance), backend.client(request.instance)
    if source.platform_api_version != "3" or target.platform_api_version != "2":
        raise ValueError("Choose a Cloud source and a Data Center/Server GPK2 destination")
    if source.cfg.base_url.rstrip("/") == target.cfg.base_url.rstrip("/"):
        raise ValueError("Source and destination must be different Jira instances")
    sprint, stories, source_version = source_snapshot(source, request.sprint_id)
    title = "SBG Jira Ops Work - " + sprint["name"]
    if len(title) > 255:
        raise ValueError("The sprint name makes the placeholder title longer than Jira allows")
    scope = scope_label(source, target, request)
    candidates = destination_candidates(target, request.project.upper(), scope, title)
    ledger = defaultdict(set)
    for issue in candidates:
        description = (issue.get("fields") or {}).get("description") or ""
        if not isinstance(description, str):
            raise ValueError("A destination placeholder has an unreadable description")
        for key in included_keys(description, source.cfg.base_url):
            ledger[key].add(issue["key"])
    grouped = defaultdict(list)
    for story in stories:
        if story.account_id:
            grouped[story.account_id].append(story)
    rows = [plan_user(target, source, request, sprint, candidates, ledger, items, account, scope, title)
            for account, items in sorted(grouped.items())]
    duplicates = {name for name, count in Counter(
        row["username"].casefold() for row in rows if row["username"]
    ).items() if count > 1}
    for row in rows:
        if row["username"] and row["username"].casefold() in duplicates:
            row["action"] = "blocked"
            row["errors"].append("Two Cloud users resolve to the same GPK2 account; reconcile their identities")
    actions = [row for row in rows if row["action"] in {"create", "update"}]
    return {
        "instance": request.instance, "source_instance": request.source_instance,
        "project": request.project.upper(), "sprint": sprint, "scope": scope,
        "source_version": source_version,
        "source_connector_version": backend._connector_version(request.source_instance),
        "connector_version": backend._connector_version(request.instance),
        "mode": backend.settings.mode, "can_apply": backend.settings.mode == "safe_apply" and bool(actions),
        "users": rows, "missing_points": [story.public() for story in stories if story.points is None],
        "unassigned": [story.public() for story in stories if not story.account_id],
        "action_count": len(actions),
    }


def plan_version(preview: dict) -> str:
    return fingerprint({k: v for k, v in preview.items() if k not in {"mode", "can_apply"}})


def observe_placeholder(target: JiraClient, request: dict) -> dict:
    if request["operation"] == "create":
        rows = target.search(f'labels = "{request["marker"]}"', ["summary", "project"], 2)
        if not rows:
            return {"state": "absent", "reason": "No uniquely confirmed placeholder is visible yet"}
        if len(rows) != 1:
            return {"state": "conflict", "reason": "Multiple destination placeholders have the same marker"}
        key = rows[0]["key"]
    else:
        key = request["issue_key"]
    state = issue_state(target, target.get_issue(key, None))
    version = fingerprint(state)
    if version == request["after_version"]:
        return {"state": "applied", "value": {"key": key}}
    if request["operation"] == "update" and version == request["before_version"]:
        return {"state": "pending"}
    return {"state": "conflict", "reason": "Placeholder state differs from the reviewed before/after values"}


def execute(backend: EngineeringOpsBackend, record: dict, recovery: bool = False) -> dict:
    request = PlaceholderRequest.model_validate(record["parameters"])
    if not recovery and plan_version(prepare(backend, record["parameters"])) != plan_version(record["preview"]):
        raise ValueError("Cloud sprint or GPK2 placeholders changed; review a fresh preview")
    target = backend.client(request.instance)
    results = []
    completed = {step["step_id"]: step for step in backend.execution_store.steps(record["preview_id"])
                 if step["status"] == "succeeded"}
    for row in record["preview"]["users"]:
        if row["action"] not in {"create", "update"}:
            continue
        step_id = row["marker"]
        if step_id in completed:
            results.append({"assignee": row["assignee"], "issue_key": completed[step_id]["result"]["value"]["key"], "action": row["action"]})
            continue
        fields, metadata_version = writable_fields(target, request, row)
        if metadata_version != row["metadata_version"] or fingerprint(fields) != row["payload_version"]:
            raise ValueError("Placeholder field configuration or reporter changed; review again")
        journal = {
            "operation": row["action"], "issue_key": row["issue_key"],
            "marker": row["marker"], "before_version": row["before_version"],
            "after_version": row["after_version"],
        }
        def mutate(row=row, fields=fields, journal=journal):
            if row["action"] == "create":
                result = target.create_issue(fields)
                if not result.get("key"):
                    raise RecoveryBlocked("Creation response has no key; reconcile before retrying")
                key = result["key"]
            else:
                key = row["issue_key"]
                if fingerprint(issue_state(target, target.get_issue(key, None))) != row["before_version"]:
                    from engineering_ops.services.recovery import BeforeWriteBlocked
                    raise BeforeWriteBlocked("The placeholder changed after review")
                target.update_issue(key, fields)
            # Verification failures occur after a write; never classify them as a rejected write.
            try:
                actual = fingerprint(issue_state(target, target.get_issue(key, None)))
                if actual != row["after_version"]:
                    raise ValueError("Placeholder values differ from the reviewed plan")
            except Exception as exc:
                raise RecoveryBlocked("Placeholder verification failed; reconcile before retrying") from exc
            return {"key": key}
        result = run_step(backend.execution_store, record["preview_id"], step_id, "ops_placeholder", journal, mutate)
        results.append({"assignee": row["assignee"], "issue_key": result["key"], "action": row["action"]})
    return {"applied": True, "placeholders": results,
            "missing_points": record["preview"]["missing_points"], "unassigned": record["preview"]["unassigned"]}


def recovery_checks(backend: EngineeringOpsBackend, record: dict) -> tuple[dict, list[str]]:
    request = PlaceholderRequest.model_validate(record["parameters"])
    source, target = backend.client(request.source_instance), backend.client(request.instance)
    _, _, version = source_snapshot(source, request.sprint_id)
    observations, blocked = {"source_version": version}, []
    steps = {step["step_id"]: step for step in backend.execution_store.steps(record["preview_id"])}
    pending = [row for row in record["preview"]["users"] if row["action"] in {"create", "update"}
               and steps.get(row["marker"], {}).get("status") != "succeeded"]
    # Source changes matter before a pending write. If every effect is already
    # confirmed, finishing its receipts releases the scope for a fresh sync.
    if pending and (version != record["preview"]["source_version"] or
                    backend._connector_version(request.source_instance) != record["preview"]["source_connector_version"]):
        blocked.append("source:changed")
    for row in record["preview"]["users"]:
        if row["action"] not in {"create", "update"}:
            continue
        if steps.get(row["marker"], {}).get("status") == "succeeded":
            continue
        target.assignable_user(request.project.upper(), row["username"])
        _, metadata_version = writable_fields(target, request, row)
        if metadata_version != row["metadata_version"]:
            blocked.append(row["marker"] + ":metadata")
        if row["marker"] in steps:
            continue
        request_state = {"operation": row["action"], "issue_key": row["issue_key"],
                         "marker": row["marker"], "before_version": row["before_version"], "after_version": row["after_version"]}
        observed = observe_placeholder(target, request_state)
        observations[row["marker"]] = observed
        expected = "absent" if row["action"] == "create" else "pending"
        if observed["state"] != expected:
            blocked.append(row["marker"] + ":unreviewed")
    return observations, blocked
