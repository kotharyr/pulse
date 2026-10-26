"""Prepare reviewed Jira creations and execute them through the durable journal."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from engineering_ops.issue_creation_models import (
    CreationContext,
    CreationParameters,
    CreationPreview,
    CreationRecord,
    IssueDraft,
    JiraFields,
    PreparedCreation,
)
from engineering_ops.services.creation_fields import (
    choice_name,
    resolve_additional_fields,
    validate_create_screen,
    validate_required_fields,
)
from engineering_ops.services.executions import fingerprint
from engineering_ops.services.issue_validation import preview_matches, reporter_matches
from engineering_ops.services.recovery import RecoveryBlocked, run_step

if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient
    from engineering_ops.backend import EngineeringOpsBackend


REPORTER_SOURCE = "Authenticated account of this Jira connection"


def load_creation_context(
    jira: JiraClient, project: str | None, issue_type: str
) -> CreationContext:
    project = (project or jira.cfg.default_project or "").strip().upper()
    if not project:
        raise ValueError("Choose a project in the selected Jira instance")
    # Jira project keys, not raw REST paths, are accepted at the public boundary.
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", project):
        raise ValueError("Choose a valid Jira project key")
    metadata = jira.creation_metadata(project, issue_type)
    user = jira.myself()
    return CreationContext(
        metadata=metadata,
        reporter=jira.reporter_value(user),
        reporter_name=user.get("displayName") or user.get("name") or "Connected Jira user",
    )


def public_context(jira: JiraClient, project: str | None, issue_type: str) -> dict[str, Any]:
    context = load_creation_context(jira, project, issue_type)
    fields = [
        {
            "name": field["name"],
            "required": field.get("required", False),
            "has_default": field.get("hasDefaultValue", False),
            "choices": [choice_name(value) for value in field.get("allowedValues", [])],
        }
        for field in context.metadata["fields"].values()
    ]
    return {
        "project": context.metadata["project"],
        "issue_type": context.metadata["issue_type"]["name"],
        "reporter": context.reporter_name,
        "reporter_source": REPORTER_SOURCE,
        "fields": fields,
    }


def build_creation_fields(
    jira: JiraClient,
    context: CreationContext,
    draft: IssueDraft,
    extras: dict[str, Any],
) -> JiraFields:
    metadata = context.metadata
    validate_create_screen(metadata["fields"])
    fields: JiraFields = {
        "project": {"key": metadata["project"]},
        "issuetype": {"id": metadata["issue_type"]["id"]},
        "summary": draft.summary,
        "description": jira.formatted_description(draft.sections()),
        "reporter": context.reporter,
    }
    fields.update(resolve_additional_fields(metadata["fields"], extras))
    validate_required_fields(metadata["fields"], fields)
    return fields


def recovery_label(
    connector_version: str,
    fields: JiraFields,
    draft: IssueDraft,
    extras: dict[str, Any],
    reporter_version: str,
) -> str:
    # Stable across metadata changes; retained as a durable operation claim.
    intent = {
        "connector": connector_version,
        "project": fields["project"],
        "type": fields["issuetype"],
        "draft": draft.model_dump(),
        "extra": extras,
        "reporter": reporter_version,
    }
    return "pulse-create-" + fingerprint(intent)[:32]


def prepare(
    jira: JiraClient, params: CreationParameters, connector_version: str
) -> PreparedCreation:
    """Validate the draft, resolve fields, and build the exact reviewable payload."""
    draft = IssueDraft.model_validate(params["draft"])
    context = load_creation_context(
        jira, params.get("project"), params.get("issue_type", "Story")
    )
    extras = params.get("additional_fields") or {}
    fields = build_creation_fields(jira, context, draft, extras)
    reporter_version = fingerprint(context.reporter)
    marker = recovery_label(connector_version, fields, draft, extras, reporter_version)
    fields["labels"] = [marker]
    preview: CreationPreview = {
        "instance": params["instance"],
        "project": context.metadata["project"],
        "issue_type": context.metadata["issue_type"]["name"],
        "summary": draft.summary,
        "description": draft.markdown(),
        "additional_fields": extras,
        "reporter": context.reporter_name,
        "reporter_source": REPORTER_SOURCE,
        "reporter_version": reporter_version,
        "recovery_label": marker,
        "metadata_version": fingerprint(context.metadata),
        "connector_version": connector_version,
        "payload_version": fingerprint(fields),
    }
    return PreparedCreation(preview=preview, fields=fields)


def create_and_verify_reporter(
    jira: JiraClient, prepared: PreparedCreation
) -> dict[str, str]:
    result = jira.create_issue(prepared.fields)
    if not result.get("key"):
        raise RecoveryBlocked("Jira did not return an issue key; reconcile before retrying")
    try:
        matches = reporter_matches(jira, result["key"], prepared.preview["reporter_version"])
    except Exception as exc:
        # A read error after POST never proves that creation failed.
        raise RecoveryBlocked(
            "Issue created but reporter verification failed; reconcile before retrying"
        ) from exc
    if not matches:
        raise RecoveryBlocked(
            "Created issue reporter differs from reviewed account; reconcile before retrying"
        )
    return {"key": result["key"]}


def execute(backend: EngineeringOpsBackend, record: CreationRecord) -> dict[str, Any]:
    jira = backend.client(record["instance"])
    prepared = prepare(
        jira, record["parameters"], backend._connector_version(record["instance"])
    )
    if not preview_matches(prepared.preview, record["preview"]):
        raise ValueError(
            "Creation preview is stale; reporter, required fields, or draft changed. "
            "Review a new preview"
        )
    preview = prepared.preview
    request = {
        "marker": preview["recovery_label"],
        "summary": preview["summary"],
        "project": preview["project"],
        "reporter_version": preview["reporter_version"],
    }
    result = run_step(
        backend.execution_store,
        record["preview_id"],
        "create",
        "create_issue",
        request,
        lambda: create_and_verify_reporter(jira, prepared),
    )
    return {
        "applied": True,
        "issue_key": result["key"],
        "instance": record["instance"],
        "reporter": preview["reporter"],
    }
