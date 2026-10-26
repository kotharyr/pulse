from __future__ import annotations

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


def completion_percent(completed: float, total: float) -> float:
    return round(completed * 100 / total, 1) if total else 0.0


def _issue_summary(issue: dict[str, Any]) -> str | None:
    return (issue.get("fields") or {}).get("summary")


def _assignee_name(issue: dict[str, Any]) -> str:
    assignee = (issue.get("fields") or {}).get("assignee") or {}
    return assignee.get("displayName") or assignee.get("name") or assignee.get("emailAddress") or "Unassigned"


def _display_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        rows: list[str] = []
        for item in value:
            rows.extend(_display_values(item))
        return rows
    if isinstance(value, dict):
        for key in ("value", "name", "displayName", "key"):
            if value.get(key):
                return [str(value[key])]
        return []
    text = str(value).strip()
    return [text] if text else []


def team_names(
    issue: dict[str, Any],
    team_field_name: str = "Team",
    team_field_id: str | None = None,
) -> list[str]:
    fields = issue.get("fields") or {}
    teams: list[str] = []
    if team_field_id:
        teams.extend(_display_values(fields.get(team_field_id)))
    teams.extend(_display_values(fields.get(team_field_name)))
    teams.extend(_display_values(fields.get("components")))
    for label in fields.get("labels") or []:
        text = str(label)
        lowered = text.casefold()
        if lowered.startswith("team:"):
            teams.append(text.split(":", 1)[1].strip())
        elif lowered.startswith("team-"):
            teams.append(text.split("-", 1)[1].strip())
    normalized = [team for team in dict.fromkeys(teams) if team]
    return normalized or ["Unassigned Team"]


def _completion_row(
    name: str,
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None,
) -> dict[str, Any]:
    summary = summarize_capacity(issues, story_points_field_name, story_points_field_id)
    return {
        "name": name,
        **summary,
        "remaining_issue_count": summary["issue_count"] - summary["done_issue_count"],
        "remaining_story_points": round(summary["story_points"] - summary["done_story_points"], 2),
        "completion_percent": completion_percent(summary["done_issue_count"], summary["issue_count"]),
        "story_point_completion_percent": completion_percent(summary["done_story_points"], summary["story_points"]),
    }


def progress_by_engineer(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        grouped.setdefault(_assignee_name(issue), []).append(issue)
    return sorted(
        [_completion_row(name, rows, story_points_field_name, story_points_field_id) for name, rows in grouped.items()],
        key=lambda row: (-row["story_points"], row["name"]),
    )


def progress_by_team(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
    team_field_name: str = "Team",
    team_field_id: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        for team in team_names(issue, team_field_name, team_field_id):
            grouped.setdefault(team, []).append(issue)
    return sorted(
        [_completion_row(name, rows, story_points_field_name, story_points_field_id) for name, rows in grouped.items()],
        key=lambda row: (-row["story_points"], row["name"]),
    )


def is_blocked(issue: dict[str, Any]) -> bool:
    fields = issue.get("fields") or {}
    labels = {str(label).casefold() for label in fields.get("labels") or []}
    status = _status_name(issue).casefold()
    flagged = fields.get("Flagged") or fields.get("flagged")
    return status == "blocked" or "blocked" in labels or "impediment" in labels or bool(flagged)


def issue_projection_row(
    issue: dict[str, Any],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> dict[str, Any]:
    return {
        "issue_key": issue.get("key"),
        "summary": _issue_summary(issue),
        "status": _status_name(issue),
        "assignee": _assignee_name(issue),
        "story_points": story_points(issue, story_points_field_name, story_points_field_id),
        "blocked": is_blocked(issue),
    }


def blocked_work(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> list[dict[str, Any]]:
    return [issue_projection_row(issue, story_points_field_name, story_points_field_id) for issue in issues if is_blocked(issue)]


def rollover_candidates(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> list[dict[str, Any]]:
    candidates = []
    for issue in issues:
        if is_done(issue):
            continue
        row = issue_projection_row(issue, story_points_field_name, story_points_field_id)
        row["reason"] = "Incomplete at sprint boundary"
        candidates.append(row)
    return sorted(candidates, key=lambda row: (-row["story_points"], row["issue_key"] or ""))


def issue_split_proposals(
    issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None = None,
) -> list[dict[str, Any]]:
    proposals = []
    for issue in issues:
        if is_done(issue):
            continue
        points = story_points(issue, story_points_field_name, story_points_field_id)
        if points <= 0:
            continue
        summary = _issue_summary(issue) or issue.get("key")
        proposals.append({
            "source_issue_key": issue.get("key"),
            "new_summary": f"Finish {summary}",
            "story_points": points,
            "move_new_issue_to_next_sprint": True,
            "source_transition_status": None,
            "reason": "Create explicit follow-on work for unfinished scope",
        })
    return sorted(proposals, key=lambda row: (-row["story_points"], row["source_issue_key"] or ""))


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


def sprint_intelligence(
    current_issues: list[dict[str, Any]],
    next_issues: list[dict[str, Any]],
    story_points_field_name: str,
    story_points_field_id: str | None,
    capacity: dict[str, Any],
    buffer_percent: float = 0.0,
    team_field_name: str = "Team",
    team_field_id: str | None = None,
) -> dict[str, Any]:
    current = summarize_capacity(current_issues, story_points_field_name, story_points_field_id)
    next_existing = summarize_capacity(next_issues, story_points_field_name, story_points_field_id)
    remaining_points = round(current["story_points"] - current["done_story_points"], 2)
    remaining_count = current["issue_count"] - current["done_issue_count"]
    projected = overcommit_analysis(
        next_existing["story_points"],
        remaining_points,
        capacity.get("story_points"),
        buffer_percent,
        next_existing["issue_count"],
        remaining_count,
        capacity.get("issue_count"),
    )
    utilization = projected.get("utilization_percent")
    projected["overcommit_percentage"] = round(max(0.0, utilization - 100), 1) if utilization is not None else None
    return {
        "issue_count": current["issue_count"],
        "completion_percent": completion_percent(current["done_issue_count"], current["issue_count"]),
        "story_points": {
            "completed": current["done_story_points"],
            "remaining": remaining_points,
            "total": current["story_points"],
            "completion_percent": completion_percent(current["done_story_points"], current["story_points"]),
        },
        "progress_by_engineer": progress_by_engineer(current_issues, story_points_field_name, story_points_field_id),
        "progress_by_team": progress_by_team(
            current_issues,
            story_points_field_name,
            story_points_field_id,
            team_field_name,
            team_field_id,
        ),
        "blocked_work": blocked_work(current_issues, story_points_field_name, story_points_field_id),
        "rollover_candidates": rollover_candidates(current_issues, story_points_field_name, story_points_field_id),
        "issue_split_proposals": issue_split_proposals(current_issues, story_points_field_name, story_points_field_id),
        "projected_next_sprint_load": {
            "existing_story_points": next_existing["story_points"],
            "rollover_story_points": remaining_points,
            "projected_story_points": projected["projected_story_points"],
            "existing_issue_count": next_existing["issue_count"],
            "rollover_issue_count": remaining_count,
            "projected_issue_count": projected["projected_issue_count"],
        },
        "next_sprint_capacity": {
            "story_points": capacity.get("story_points"),
            "issue_count": capacity.get("issue_count"),
            "source": capacity.get("source", "unknown"),
            "buffer_percent": buffer_percent,
            "safe_story_points": projected.get("safe_capacity_story_points"),
        },
        "overcommit": projected,
    }
