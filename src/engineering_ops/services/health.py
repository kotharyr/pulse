from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _date(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def engineering_health(issues: list[dict[str, Any]], stale_days: int = 90) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    status_counts = Counter()
    domain_counts = Counter()
    stale = []
    blocked = []
    unassigned = []
    for issue in issues:
        f = issue.get("fields") or {}
        status = (f.get("status") or {}).get("name", "Unknown")
        status_counts[status] += 1
        labels = f.get("labels") or []
        for label in labels:
            if str(label).startswith("domain-"):
                domain_counts[str(label)] += 1
        updated = _date(f.get("updated"))
        if updated and (now - updated).days >= stale_days:
            stale.append(issue["key"])
        if "block" in status.casefold() or any("block" in str(x).casefold() for x in labels):
            blocked.append(issue["key"])
        if not f.get("assignee"):
            unassigned.append(issue["key"])
    total = len(issues)
    return {
        "issue_count": total,
        "status_counts": dict(status_counts),
        "domain_counts": dict(domain_counts),
        "stale_count": len(stale),
        "stale_percent": round(len(stale) * 100 / total, 1) if total else 0,
        "blocked_count": len(blocked),
        "unassigned_count": len(unassigned),
        "stale_issue_keys": stale[:100],
        "blocked_issue_keys": blocked[:100],
        "unassigned_issue_keys": unassigned[:100],
    }
