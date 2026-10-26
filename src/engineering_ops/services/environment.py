from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from engineering_ops.config import PROJECT_ROOT
from engineering_ops.models import Board, Project, Sprint


DEFAULT_ENVIRONMENT_CACHE = PROJECT_ROOT / "config" / "environment_cache.json"
SELECT_FIELD_HINTS = ("select", "multiselect", "option", "array")
PORTFOLIO_FIELD_HINTS = ("portfolio", "initiative", "theme", "epic", "parent")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _age_seconds(value: str | None) -> int | None:
    if not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        refreshed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return max(0, int((datetime.now(UTC) - refreshed.astimezone(UTC)).total_seconds()))


def _display_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        rows: list[str] = []
        for item in value:
            rows.extend(_display_values(item))
        return rows
    if isinstance(value, dict):
        for key in ("name", "value", "displayName", "key"):
            if value.get(key):
                return [str(value[key])]
        return []
    text = str(value).strip()
    return [text] if text else []


def _dedupe(rows: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result = []
    for row in rows:
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _field_schema_type(field: dict[str, Any]) -> str | None:
    schema = field.get("schema") or {}
    return schema.get("custom") or schema.get("type")


def _is_select_field(field: dict[str, Any]) -> bool:
    text = " ".join(str(part or "") for part in [field.get("name"), _field_schema_type(field)]).casefold()
    return any(hint in text for hint in SELECT_FIELD_HINTS)


def _public_field(field: dict[str, Any], include_internal: bool = False) -> dict[str, Any]:
    row = {
        "name": field.get("name"),
        "custom": field.get("custom", False),
        "type": _field_schema_type(field),
    }
    if include_internal:
        row["id"] = field.get("id")
    return {key: value for key, value in row.items() if value is not None}


def public_environment(model: dict[str, Any], include_internal: bool = False) -> dict[str, Any]:
    public = dict(model)
    public["projects"] = [
        Project(row.get("key"), row.get("name"), row.get("id")).to_dict(include_internal)
        for row in model.get("projects", [])
    ]
    public["boards"] = [
        Board(row.get("name"), row.get("project_key"), row.get("type"), row.get("id")).to_dict(include_internal)
        for row in model.get("boards", [])
    ]
    public["sprints"] = [
        Sprint(
            row.get("name"),
            row.get("state"),
            row.get("board_name"),
            row.get("start_date"),
            row.get("end_date"),
            row.get("id"),
            row.get("board_id"),
        ).to_dict(include_internal)
        for row in model.get("sprints", [])
    ]
    public["fields"] = [_public_field(row, include_internal) for row in model.get("fields", [])]
    public["custom_fields"] = [_public_field(row, include_internal) for row in model.get("custom_fields", [])]
    if not include_internal:
        public.pop("internal", None)
    return public


@dataclass
class EnvironmentCache:
    path: Path = DEFAULT_ENVIRONMENT_CACHE

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"instances": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"instances": {}}
        if not isinstance(data, dict):
            return {"instances": {}}
        data.setdefault("instances", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, instance: str) -> dict[str, Any] | None:
        return self._read().get("instances", {}).get(instance)

    def put(self, instance: str, model: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data.setdefault("instances", {})[instance] = model
        self._write(data)
        return model

    def all(self) -> dict[str, Any]:
        return self._read().get("instances", {})


def discover_environment_model(jira: Any, instance: str, project_key: str | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def safe(name: str, fn: Callable[[], Any], default: Any) -> Any:
        try:
            return fn()
        except Exception as exc:
            errors.append({"area": name, "error": str(exc)})
            return default

    project = project_key or jira.cfg.default_project
    projects_raw = safe("projects", lambda: jira.projects(), [])
    projects = [
        {"key": row.get("key"), "name": row.get("name"), "id": row.get("id")}
        for row in projects_raw or []
    ]
    project_keys = [project] if project else [row.get("key") for row in projects[:5] if row.get("key")]

    fields_raw = safe("fields", lambda: jira.fields(), [])
    fields = [_public_field(row, include_internal=True) for row in fields_raw or []]
    custom_fields = [row for row in fields if row.get("custom")]
    field_names = {str(row.get("name") or "").casefold(): row for row in fields_raw or []}

    boards_raw = safe("boards", lambda: jira.boards(project, limit=100), []) if project else []
    boards = [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "type": row.get("type"),
            "project_key": project,
        }
        for row in boards_raw or []
    ]

    sprints = []
    for board in boards[:20]:
        for state in ("active", "future", "closed"):
            rows = safe(
                f"sprints:{board.get('name') or board.get('id')}:{state}",
                lambda board_id=board.get("id"), state=state: jira.board_sprints(int(board_id), state=state, limit=50),
                [],
            )
            for sprint in rows or []:
                sprints.append({
                    "id": sprint.get("id"),
                    "name": sprint.get("name"),
                    "state": sprint.get("state"),
                    "start_date": sprint.get("startDate"),
                    "end_date": sprint.get("endDate"),
                    "board_id": board.get("id"),
                    "board_name": board.get("name"),
                })

    issue_types = safe("issue_types", lambda: jira.issue_types(), [])
    priorities = safe("priorities", lambda: jira.priorities(), [])
    components = []
    versions = []
    for key in project_keys:
        if not key:
            continue
        components.extend([
            {"project_key": key, "name": row.get("name")}
            for row in safe(f"components:{key}", lambda key=key: jira.project_components(key), [])
        ])
        versions.extend([
            {"project_key": key, "name": row.get("name"), "released": row.get("released"), "archived": row.get("archived")}
            for row in safe(f"versions:{key}", lambda key=key: jira.project_versions(key), [])
        ])

    configured_names = {
        str(getattr(jira.cfg, "quarter_field_name", "")).casefold(),
        "target quarter",
        "architectural domain",
    }
    relevant_fields = [
        row for row in fields_raw or []
        if str(row.get("name") or "").casefold() in configured_names
        or any(hint in str(row.get("name") or "").casefold() for hint in PORTFOLIO_FIELD_HINTS)
    ]
    select_fields = [row for row in fields_raw or [] if _is_select_field(row) or row in relevant_fields]

    field_values: dict[str, list[str]] = {}
    for field in select_fields:
        values: list[str] = []
        for value in field.get("allowedValues") or []:
            values.extend(_display_values(value))
        field_values[field.get("name") or field.get("id")] = sorted(set(values))

    sample_field_ids = [row.get("id") for row in relevant_fields if row.get("id")]
    if project and sample_field_ids:
        sample_fields = ["summary", *sample_field_ids]
        sample_jql = f"project = {project} ORDER BY updated DESC"
        samples = safe("sample_field_values", lambda: jira.search(sample_jql, sample_fields, 100), [])
        id_to_name = {row.get("id"): row.get("name") for row in relevant_fields}
        for issue in samples or []:
            for field_id, value in (issue.get("fields") or {}).items():
                name = id_to_name.get(field_id)
                if name:
                    field_values.setdefault(name, [])
                    field_values[name].extend(_display_values(value))
        field_values = {key: sorted(set(values)) for key, values in field_values.items()}

    quarter_field_name = getattr(jira.cfg, "quarter_field_name", "Target Quarter")
    quarter_values = field_values.get(quarter_field_name) or (
        [row["name"] for row in versions if row.get("name")] if quarter_field_name.casefold() in {"fix version/s", "fix versions"} else []
    )
    domain_values = []
    for name, values in field_values.items():
        if "architectural domain" in name.casefold():
            domain_values.extend(values)

    return {
        "instance": instance,
        "kind": jira.cfg.kind,
        "project": project,
        "refreshed_at": now_iso(),
        "cache_age_seconds": 0,
        "projects": _dedupe(projects),
        "boards": _dedupe(boards),
        "sprints": _dedupe(sprints),
        "issue_types": sorted({row.get("name") for row in issue_types or [] if row.get("name")}),
        "fields": _dedupe(fields),
        "custom_fields": _dedupe(custom_fields),
        "components": _dedupe([row for row in components if row.get("name")]),
        "priorities": sorted({row.get("name") for row in priorities or [] if row.get("name")}),
        "versions": _dedupe([row for row in versions if row.get("name")]),
        "select_field_values": field_values,
        "target_quarter_values": sorted(set(quarter_values)),
        "architectural_domain_values": sorted(set(domain_values)),
        "portfolio_fields": [
            _public_field(row, include_internal=True)
            for row in fields_raw or []
            if any(hint in str(row.get("name") or "").casefold() for hint in PORTFOLIO_FIELD_HINTS)
        ],
        "errors": errors,
    }


def with_cache_age(model: dict[str, Any]) -> dict[str, Any]:
    return {**model, "cache_age_seconds": _age_seconds(model.get("refreshed_at"))}


def find_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    target = name.casefold()
    for row in rows:
        candidates = [row.get("name"), row.get("key")]
        if any(str(candidate or "").casefold() == target for candidate in candidates):
            return row
    for row in rows:
        candidates = [row.get("name"), row.get("key")]
        if any(target in str(candidate or "").casefold() for candidate in candidates):
            return row
    return None
