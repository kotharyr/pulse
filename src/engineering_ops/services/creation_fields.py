"""Resolve human field names and values against a Jira create screen."""
from __future__ import annotations

import math
from typing import Any

from engineering_ops.issue_creation_models import CreationField, FieldChoice, JiraFields


RESERVED_FIELDS = frozenset({
    "project", "issuetype", "summary", "description", "reporter", "labels",
})
REQUIRED_SCREEN_FIELDS = ("summary", "description", "reporter", "labels")


def choice_name(choice: FieldChoice) -> str | None:
    return choice.get("value") or choice.get("name") or choice.get("displayName")


def is_writable(field: CreationField) -> bool:
    return "set" in field.get("operations", ["set"])


def validate_create_screen(metadata: dict[str, CreationField]) -> None:
    for key in REQUIRED_SCREEN_FIELDS:
        if key not in metadata or not is_writable(metadata[key]):
            raise ValueError(
                f"The selected create screen must allow {key}; "
                "ask its Jira administrator to enable it"
            )


def resolve_choice(field: CreationField, value: Any) -> dict[str, str]:
    matches = [
        choice for choice in field["allowedValues"]
        if str(choice_name(choice) or "").casefold() == str(value).casefold()
    ]
    if len(matches) != 1:
        raise ValueError(f"Choose an available value for {field['name']}")
    selected = matches[0]
    if selected.get("id") is None:
        raise ValueError(f"Unsupported choice for {field['name']}")
    return {"id": str(selected["id"])}


def resolve_extra(field: CreationField, value: Any) -> Any:
    """Accept only supported values; never pass arbitrary objects through to Jira."""
    schema = field.get("schema", {})
    kind = schema.get("type")
    if field.get("allowedValues"):
        if kind == "array":
            if not isinstance(value, list) or not value:
                raise ValueError(f"{field['name']} requires a nonempty list of names")
            return [resolve_choice(field, item) for item in value]
        return resolve_choice(field, value)
    if kind == "string" and isinstance(value, str) and value.strip():
        if schema.get("custom", "").endswith(":textarea"):
            raise ValueError(f"Rich text field {field['name']} needs dedicated support")
        return value
    if kind == "number" and type(value) in {int, float} and math.isfinite(value):
        return value
    if (
        kind == "array"
        and schema.get("items") == "string"
        and isinstance(value, list)
        and value
        and all(isinstance(item, str) and item.strip() for item in value)
    ):
        return value
    raise ValueError(
        f"Unsupported value for {field['name']}; use supported names or scalar values"
    )


def resolve_additional_fields(
    metadata: dict[str, CreationField], values: dict[str, Any]
) -> JiraFields:
    resolved = {}
    for name, value in values.items():
        matches = [
            (key, field) for key, field in metadata.items()
            if field["name"].casefold() == name.casefold()
        ]
        if (
            len(matches) != 1
            or matches[0][0] in RESERVED_FIELDS
            or name.casefold() in RESERVED_FIELDS
        ):
            raise ValueError(f"Unknown, ambiguous, or reserved creation field: {name}")
        key, field = matches[0]
        if not is_writable(field):
            raise ValueError(f"Creation field is not writable: {name}")
        resolved[key] = resolve_extra(field, value)
    return resolved


def validate_required_fields(
    metadata: dict[str, CreationField], fields: JiraFields
) -> None:
    # Labels are supplied by the recovery marker after this validation stage.
    missing = [
        field["name"] for key, field in metadata.items()
        if field.get("required") and not field.get("hasDefaultValue")
        and key not in fields and key != "labels"
    ]
    if missing:
        raise ValueError("Required creation fields need values: " + ", ".join(missing))
