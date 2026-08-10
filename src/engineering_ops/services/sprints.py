from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _status_name(issue: dict[str, Any]) -> str:
    return ((issue.get("fields") or {}).get("status") or {}).get("name", "Unknown")


def _status_category(issue: dict[str, Any]) -> str:
    return (((issue.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key", "")


def is_done(issue: dict[str, Any]) -> bool:
    category = _status_category(issue).casefold()
    if category == "done":
        return True
    return _status_name(issue).casefold() in {"done", "closed", "resolved"}


def story_points(issue: dict[str, Any], field_name: str, field_id: str | None = None) -> float:
    fields = issue.get("fields") or {}
    value = fields.get(field_id) if field_id else None
    if value is None:
        value = fields.get(field_name)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_capacity(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> dict[str, Any]:
    total_points = sum(story_points(i, story_points_field_name, story_points_field_id) for i in issues)
    done_issues = [i for i in issues if is_done(i)]
    done_points = sum(story_points(i, story_points_field_name, story_points_field_id) for i in done_issues)
    return {
        "issue_count": len(issues),
        "story_points": round(total_points, 2),
        "done_issue_count": len(done_issues),
        "done_story_points": round(done_points, 2),
    }


def overcommit_analysis(
    existing_points: float,
    added_points: float,
    capacity_points: float | None,
    buffer_percent: float = 0.0,
    existing_count: int = 0,
    added_count: int = 0,
    capacity_issue_count: int | None = None,
) -> dict[str, Any]:
    projected_points = existing_points + added_points
    projected_count = existing_count + added_count
    result: dict[str, Any] = {
        "existing_story_points": round(existing_points, 2),
        "added_story_points": round(added_points, 2),
        "projected_story_points": round(projected_points, 2),
        "existing_issue_count": existing_count,
        "added_issue_count": added_count,
        "projected_issue_count": projected_count,
        "capacity_story_points": capacity_points,
        "capacity_issue_count": capacity_issue_count,
        "buffer_percent": buffer_percent,
        "overcommitted": False,
        "basis": "unknown",
    }
    if capacity_points and capacity_points > 0:
        safe_capacity = capacity_points * max(0.0, (100.0 - buffer_percent) / 100.0)
        delta = projected_points - safe_capacity
        result.update({
            "basis": "story_points",
            "safe_capacity_story_points": round(safe_capacity, 2),
            "overcommitted": delta > 0,
            "over_by_story_points": round(max(0.0, delta), 2),
            "utilization_percent": round(projected_points * 100 / safe_capacity, 1) if safe_capacity else None,
        })
    elif capacity_issue_count and capacity_issue_count > 0:
        delta_count = projected_count - capacity_issue_count
        result.update({
            "basis": "issue_count",
            "overcommitted": delta_count > 0,
            "over_by_issue_count": max(0, delta_count),
            "utilization_percent": round(projected_count * 100 / capacity_issue_count, 1),
        })
    return result
