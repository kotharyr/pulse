"""Reviewed, recoverable issue creation from structured Chat drafts."""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engineering_ops.services.executions import fingerprint
from engineering_ops.services.recovery import RecoveryBlocked, run_step


if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient
    from engineering_ops.backend import EngineeringOpsBackend


class UserStory(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: str = Field(min_length=1)
    want: str = Field(min_length=1)
    benefit: str = Field(min_length=1)


class IssueDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=255)
    overview: str = Field(min_length=1, description="Content of the Description's Summary section")
    user_story: UserStory
    description: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    business_value: list[str] = Field(min_length=1)

    @field_validator("summary")
    @classmethod
    def single_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("Summary must be a single line")
        return value

    @field_validator("acceptance_criteria", "dependencies", "out_of_scope", "business_value")
    @classmethod
    def nonempty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Section items cannot be blank; use 'None' when explicitly out of scope")
        return [value.strip() for value in values]

    def sections(self) -> list[tuple[str, str | list[str]]]:
        story = self.user_story
        return [("Summary", self.overview), ("User Story", f"**As a** {story.role},\n\n**I want** {story.want},\n\n**so that** {story.benefit}."),
                ("Description", self.description), ("Acceptance Criteria", self.acceptance_criteria),
                ("Dependencies", self.dependencies), ("Out of Scope", self.out_of_scope), ("Business Value", self.business_value)]

    def markdown(self) -> str:
        return "\n\n".join(f"## {title}\n\n" + ("\n".join("- " + s for s in body) if isinstance(body, list) else body) for title, body in self.sections())


def context(jira: JiraClient, project: str | None, issue_type: str) -> tuple[dict, dict, dict]:
    project = (project or jira.cfg.default_project or "").strip().upper()
    if not project:
        raise ValueError("Choose a project in the selected Jira instance")
    # Jira project keys, not raw REST paths, are accepted at the public boundary.
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", project):
        raise ValueError("Choose a valid Jira project key")
    metadata = jira.creation_metadata(project, issue_type)
    user = jira.myself()
    reporter = jira.reporter_value(user)
    return metadata, reporter, user


def public_context(jira: JiraClient, project: str | None, issue_type: str) -> dict:
    metadata, _, user = context(jira, project, issue_type)
    return {"project": metadata["project"], "issue_type": metadata["issue_type"]["name"],
            "reporter": user.get("displayName") or user.get("name") or "Connected Jira user",
            "reporter_source": "Authenticated account of this Jira connection",
            "fields": [{"name": f["name"], "required": f.get("required", False), "has_default": f.get("hasDefaultValue", False),
                        "choices": [v.get("value") or v.get("name") or v.get("displayName") for v in f.get("allowedValues", [])]}
                       for f in metadata["fields"].values()]}


def resolve_extra(field: dict, value: Any) -> Any:
    allowed = field.get("allowedValues")
    schema = field.get("schema", {})
    if allowed:
        def match(item: Any) -> dict:
            matches = [v for v in allowed if str(v.get("value") or v.get("name") or v.get("displayName") or "").casefold() == str(item).casefold()]
            if len(matches) != 1:
                raise ValueError(f"Choose an available value for {field['name']}")
            selected = matches[0]
            if selected.get("id") is None:
                raise ValueError(f"Unsupported choice for {field['name']}")
            return {"id": str(selected["id"])}
        if schema.get("type") == "array":
            if not isinstance(value, list) or not value:
                raise ValueError(f"{field['name']} requires a nonempty list of names")
            return [match(v) for v in value]
        return match(value)
    kind = schema.get("type")
    if kind == "string" and isinstance(value, str) and value.strip():
        if schema.get("custom", "").endswith(":textarea"):
            raise ValueError(f"Rich text field {field['name']} needs dedicated support")
        return value
    if kind == "number" and type(value) in {int, float}:
        if math.isfinite(value):
            return value
    if kind == "array" and schema.get("items") == "string" and isinstance(value, list) and value and all(isinstance(v, str) and v.strip() for v in value):
        return value
    raise ValueError(f"Unsupported value for {field['name']}; use supported names or scalar values")


def prepare(jira: JiraClient, params: dict, connector_version: str) -> tuple[dict, dict]:
    draft = IssueDraft.model_validate(params["draft"])
    metadata, reporter, user = context(jira, params.get("project"), params.get("issue_type", "Story"))
    meta = metadata["fields"]
    # Requiring both fields makes reporter attribution and uncertain-create recovery explicit.
    for key in ("summary", "description", "reporter", "labels"):
        if key not in meta or "set" not in meta[key].get("operations", ["set"]):
            raise ValueError(f"The selected create screen must allow {key}; ask its Jira administrator to enable it")
    fields = {"project": {"key": metadata["project"]}, "issuetype": {"id": metadata["issue_type"]["id"]},
              "summary": draft.summary, "description": jira.formatted_description(draft.sections()), "reporter": reporter}
    extras = params.get("additional_fields") or {}
    protected = {"project", "issuetype", "summary", "description", "reporter", "labels"}
    for name, value in extras.items():
        matches = [(key, field) for key, field in meta.items() if field["name"].casefold() == name.casefold()]
        if len(matches) != 1 or matches[0][0] in protected or name.casefold() in protected:
            raise ValueError(f"Unknown, ambiguous, or reserved creation field: {name}")
        key, field = matches[0]
        if "set" not in field.get("operations", ["set"]):
            raise ValueError(f"Creation field is not writable: {name}")
        fields[key] = resolve_extra(field, value)
    missing = [f["name"] for key, f in meta.items() if f.get("required") and not f.get("hasDefaultValue") and key not in fields and key != "labels"]
    if missing:
        raise ValueError("Required creation fields need values: " + ", ".join(missing))
    identity_version = fingerprint(reporter)
    # Stable across metadata changes; retained as a durable operation claim.
    marker = "pulse-create-" + fingerprint({"connector": connector_version, "project": fields["project"], "type": fields["issuetype"],
                                            "draft": draft.model_dump(), "extra": extras, "reporter": identity_version})[:32]
    fields["labels"] = [marker]
    preview = {"instance": params["instance"], "project": metadata["project"], "issue_type": metadata["issue_type"]["name"],
               "summary": draft.summary, "description": draft.markdown(), "additional_fields": extras,
               "reporter": user.get("displayName") or user.get("name") or "Connected Jira user",
               "reporter_source": "Authenticated account of this Jira connection", "reporter_version": identity_version,
               "recovery_label": marker, "metadata_version": fingerprint(metadata), "connector_version": connector_version,
               "payload_version": fingerprint(fields)}
    return preview, fields


def execute(backend: EngineeringOpsBackend, record: dict, recovery: bool = False) -> dict:
    jira = backend.client(record["instance"])
    current, fields = prepare(jira, record["parameters"], backend._connector_version(record["instance"]))
    if fingerprint(current) != fingerprint(record["preview"]):
        raise ValueError("Creation preview is stale; reporter, required fields, or draft changed. Review a new preview")
    request = {"marker": current["recovery_label"], "summary": current["summary"], "project": current["project"],
               "reporter_version": current["reporter_version"]}

    def create() -> dict:
        result = jira.create_issue(fields)
        if not result.get("key"):
            raise RecoveryBlocked("Jira did not return an issue key; reconcile before retrying")
        try:
            created = jira.get_issue(result["key"], ["reporter"])
            actual = jira.reporter_value((created.get("fields") or {}).get("reporter") or {})
        except Exception as exc:
            # A read error after POST never proves that creation failed.
            raise RecoveryBlocked("Issue created but reporter verification failed; reconcile before retrying") from exc
        if fingerprint(actual) != current["reporter_version"]:
            raise RecoveryBlocked("Created issue reporter differs from reviewed account; reconcile before retrying")
        return {"key": result["key"]}

    result = run_step(backend.execution_store, record["preview_id"], "create", "create_issue", request, create)
    return {"applied": True, "issue_key": result["key"], "instance": record["instance"], "reporter": current["reporter"]}
