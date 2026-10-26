#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config" / "jira_instances.json"
BACKUP = ROOT / "config" / "jira_instances.pre-v1.json"

def _prefix(reference: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", reference).strip("_").upper()
    return f"JIRA_{normalized}"


def _legacy_auth_matches_convention(instance_type: str, reference: str, auth: dict) -> bool:
    prefix = _prefix(reference)
    mode = auth.get("mode")
    if instance_type == "cloud":
        return (
            mode == "basic"
            and auth.get("username_env") == f"{prefix}_EMAIL"
            and auth.get("secret_env") == f"{prefix}_API_TOKEN"
        )
    if mode in {"bearer", "pat"}:
        return not auth.get("username_env") and auth.get("secret_env") == f"{prefix}_PAT"
    return (
        mode == "basic"
        and auth.get("username_env") == f"{prefix}_USERNAME"
        and auth.get("secret_env") == f"{prefix}_PASSWORD"
    )


def migrate(data: dict) -> tuple[dict, list[str]]:
    new = {}
    warnings = []
    for name, raw in data.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Instance {name!r} must be an object")
        row = dict(raw)
        instance_type = row.pop("type", row.pop("kind", None))
        if not instance_type:
            raise ValueError(f"Instance {name!r} has no type/kind")
        reference = row.get("credentials") or name
        legacy_auth = row.pop("auth", None)
        row.pop("api_version", None)
        row["type"] = instance_type
        row["credentials"] = reference
        if legacy_auth and not _legacy_auth_matches_convention(instance_type, reference, legacy_auth):
            row["auth"] = legacy_auth
            warnings.append(
                f"Instance {name!r} keeps its legacy auth mapping because its environment variable names are nonstandard."
            )

        ordered = {
            "type": row.pop("type"),
            "base_url": row.pop("base_url"),
            "credentials": row.pop("credentials"),
        }
        ordered.update(row)
        new[name] = ordered
    return new, warnings


def main() -> None:
    if not PATH.exists():
        raise SystemExit(f"No config to migrate: {PATH}")
    data = json.loads(PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("jira_instances.json must contain a JSON object")
    try:
        migrated, warnings = migrate(data)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    shutil.copy2(PATH, BACKUP)
    PATH.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
    print(f"Migrated: {PATH}")
    print(f"Backup:   {BACKUP}")
    for warning in warnings:
        print(f"Warning:  {warning}")


if __name__ == "__main__":
    main()
