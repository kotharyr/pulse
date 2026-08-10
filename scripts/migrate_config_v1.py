#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config" / "jira_instances.json"
BACKUP = ROOT / "config" / "jira_instances.pre-v1.json"

if not PATH.exists():
    raise SystemExit(f"No config to migrate: {PATH}")

data = json.loads(PATH.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("jira_instances.json must contain a JSON object")

shutil.copy2(PATH, BACKUP)
new = {}
for name, raw in data.items():
    if not isinstance(raw, dict):
        raise SystemExit(f"Instance {name!r} must be an object")
    row = dict(raw)
    instance_type = row.pop("type", row.pop("kind", None))
    if not instance_type:
        raise SystemExit(f"Instance {name!r} has no type/kind")
    row.pop("auth", None)
    row.pop("api_version", None)
    row["type"] = instance_type
    row["credentials"] = row.get("credentials") or name

    # Stable preferred ordering for human readability.
    ordered = {
        "type": row.pop("type"),
        "base_url": row.pop("base_url"),
        "credentials": row.pop("credentials"),
    }
    ordered.update(row)
    new[name] = ordered

PATH.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
print(f"Migrated: {PATH}")
print(f"Backup:   {BACKUP}")
