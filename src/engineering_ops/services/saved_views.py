from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engineering_ops.config import PROJECT_ROOT
from engineering_ops.models import SavedView


DEFAULT_SAVED_VIEWS_PATH = PROJECT_ROOT / "config" / "saved_views.json"


def view_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if not slug:
        raise ValueError("Saved view name cannot be empty")
    return slug


DEFAULT_VIEW_DEFINITIONS = [
    {
        "name": "Security Exceptions",
        "instance": "cloud",
        "jql": 'summary ~ "Security Exception" ORDER BY updated DESC',
        "metadata": {"domain": "security"},
        "dashboard_type": "issue_list",
    },
    {
        "name": "Governance Exceptions",
        "instance": "cloud",
        "jql": 'summary ~ "Governance Exception" ORDER BY updated DESC',
        "metadata": {"domain": "governance"},
        "dashboard_type": "issue_list",
    },
    {
        "name": "Platform Backlog",
        "instance": "cloud",
        "jql": "project = MUON ORDER BY updated DESC",
        "metadata": {"team": "platform"},
        "dashboard_type": "backlog",
    },
    {
        "name": "Current Sprint",
        "instance": "cloud",
        "jql": "sprint in openSprints() ORDER BY priority DESC, updated DESC",
        "dashboard_type": "sprint",
    },
    {
        "name": "Unassigned Work",
        "instance": "cloud",
        "jql": "assignee is EMPTY AND resolution is EMPTY ORDER BY updated DESC",
        "dashboard_type": "issue_list",
    },
    {
        "name": "Stale Backlog",
        "instance": "cloud",
        "jql": "updated <= -90d AND resolution is EMPTY ORDER BY updated ASC",
        "dashboard_type": "risk",
    },
    {
        "name": "Low Quality Tickets",
        "instance": "cloud",
        "jql": "description is EMPTY AND resolution is EMPTY ORDER BY updated DESC",
        "dashboard_type": "quality",
    },
    {
        "name": "Operational Security Issues",
        "instance": "cloud",
        "jql": 'summary ~ "Operational Security Issue" ORDER BY updated DESC',
        "metadata": {"domain": "security"},
        "dashboard_type": "security",
    },
]


def default_views(default_instance: str = "cloud", default_project: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for raw in DEFAULT_VIEW_DEFINITIONS:
        row = dict(raw)
        row["instance"] = default_instance
        if row["name"] == "Platform Backlog" and default_project:
            row["jql"] = f"project = {default_project} ORDER BY updated DESC"
        rows.append(SavedView(**row).to_dict())
    return rows


@dataclass
class SavedViewStore:
    path: Path = DEFAULT_SAVED_VIEWS_PATH

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"views": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"views": []}
        if not isinstance(data, dict):
            return {"views": []}
        data.setdefault("views", [])
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._read().get("views", []), key=lambda row: row.get("name", "").casefold())

    def bootstrap_defaults(self, default_instance: str = "cloud", default_project: str | None = None) -> list[dict[str, Any]]:
        data = self._read()
        if not data.get("views"):
            data["views"] = default_views(default_instance, default_project)
            self._write(data)
        return self.list()

    def get(self, name_or_id: str) -> dict[str, Any]:
        target = view_id(name_or_id)
        for row in self.list():
            if row.get("id") == target or view_id(row.get("name", "")) == target:
                return row
        raise KeyError(f"Saved view not found: {name_or_id}")

    def upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        view = SavedView(
            name=payload["name"],
            instance=payload["instance"],
            jql=payload["jql"],
            metadata=payload.get("metadata") or {},
            default_columns=payload.get("default_columns") or [],
            default_sort=payload.get("default_sort"),
            dashboard_type=payload.get("dashboard_type"),
        ).to_dict()
        data = self._read()
        target = view["id"]
        rows = [row for row in data.get("views", []) if row.get("id") != target and view_id(row.get("name", "")) != target]
        rows.append(view)
        data["views"] = rows
        self._write(data)
        return view

    def delete(self, name_or_id: str) -> dict[str, Any]:
        target = view_id(name_or_id)
        data = self._read()
        kept = [row for row in data.get("views", []) if row.get("id") != target and view_id(row.get("name", "")) != target]
        if len(kept) == len(data.get("views", [])):
            raise KeyError(f"Saved view not found: {name_or_id}")
        data["views"] = kept
        self._write(data)
        return {"deleted": True, "id": target}
