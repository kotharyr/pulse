from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from statistics import mean
from typing import Any, Callable

from engineering_ops.adapters.jira import JiraClient
from engineering_ops.config import Settings, configuration_report, settings
from engineering_ops.runtime import client as default_client
from engineering_ops.services.fields import resolve_field, resolve_value_for_issue
from engineering_ops.services.health import engineering_health as health_summary
from engineering_ops.services.executions import ExecutionHistory
from engineering_ops.services.repos import discover_repositories, extract_security_signals, scan_manifests
from engineering_ops.services.sprints import is_done, overcommit_analysis, sprint_intelligence, story_points, summarize_capacity

logger = logging.getLogger("engineering_ops")
ClientGetter = Callable[[str], JiraClient]
CUSTOM_FIELD_RE = re.compile(r"^customfield_\d+$", re.I)


def _text_from_adf(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(_text_from_adf(item) for item in node)
    if isinstance(node, dict):
        parts = []
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        if node.get("content"):
            parts.append(_text_from_adf(node["content"]))
        return " ".join(part for part in parts if part)
    return ""


def _preview_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key not in {"mode", "can_apply", "preview_id"}}


def _preview_id(plan: dict[str, Any]) -> str:
    payload = json.dumps(_preview_payload(plan), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _with_preview_id(plan: dict[str, Any]) -> dict[str, Any]:
    return {**plan, "preview_id": _preview_id(plan)}


def _sanitize_issue(issue: dict[str, Any], field_aliases: dict[str, str] | None = None) -> dict[str, Any]:
    aliases = field_aliases or {}
    sanitized = {key: value for key, value in issue.items() if key != "fields"}
    fields = issue.get("fields") or {}
    sanitized_fields: dict[str, Any] = {}
    for key, value in fields.items():
        alias = aliases.get(key)
        if alias:
            sanitized_fields[alias] = value
        elif not CUSTOM_FIELD_RE.match(str(key)):
            sanitized_fields[key] = value
    sanitized["fields"] = sanitized_fields
    return sanitized


@dataclass
class EngineeringOpsBackend:
    """Transport-neutral backend used by MCP today and future UI clients."""

    client_getter: ClientGetter = default_client
    settings: Settings = field(default_factory=lambda: settings)
    configuration_reporter: Callable[[], dict[str, Any]] = configuration_report
    execution_store: ExecutionHistory = field(default_factory=ExecutionHistory)

    def client(self, instance: str) -> JiraClient:
        return self.client_getter(instance)

    def _story_points_field(self, jira: JiraClient) -> tuple[str, str | None]:
        name = jira.cfg.story_points_field_name
        return name, resolve_field(jira, name)["id"]

    def _recent_capacity_samples(
        self,
        jira: JiraClient,
        board_id: int | None,
        points_field_name: str,
        points_field_id: str | None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if not board_id:
            return []
        closed = jira.board_sprints(board_id, state="closed", limit=5)
        samples = []
        for sprint in closed[-limit:]:
            issues = jira.sprint_issues(int(sprint["id"]), story_points_field_id=points_field_id)
            completed = sum(story_points(issue, points_field_name, points_field_id) for issue in issues if is_done(issue))
            if completed > 0:
                samples.append({
                    "sprint_id": sprint.get("id"),
                    "name": sprint.get("name"),
                    "completed_story_points": round(completed, 2),
                })
        return samples

    def _derive_capacity(
        self,
        jira: JiraClient,
        board_id: int | None,
        points_field_name: str,
        points_field_id: str | None,
    ) -> dict[str, Any]:
        cfg = jira.cfg
        if cfg.sprint_capacity_points:
            return {"story_points": cfg.sprint_capacity_points, "issue_count": cfg.sprint_capacity_issue_count, "source": "configured"}
        if board_id:
            try:
                samples = self._recent_capacity_samples(jira, board_id, points_field_name, points_field_id)
                if samples:
                    completed_points = [sample["completed_story_points"] for sample in samples]
                    return {
                        "story_points": round(mean(completed_points), 2),
                        "issue_count": None,
                        "source": f"average completed points from {len(samples)} recent closed sprints",
                    }
            except Exception as exc:
                logger.warning("Could not derive sprint capacity for %s: %s", jira.name, exc)
        return {
            "story_points": None,
            "issue_count": cfg.sprint_capacity_issue_count,
            "source": "configured_issue_count" if cfg.sprint_capacity_issue_count else "unknown",
        }

    def system_readiness(self, check_connections: bool = False) -> dict[str, Any]:
        """Check local configuration and, optionally, authenticate to every configured Jira instance."""
        report = self.configuration_reporter()
        connection_results = []
        if check_connections and report["ok"]:
            for row in report["instances"]:
                try:
                    me = self.client(row["name"]).myself()
                    connection_results.append({
                        "instance": row["name"],
                        "ok": True,
                        "display_name": me.get("displayName") or me.get("name"),
                    })
                except Exception as exc:
                    connection_results.append({"instance": row["name"], "ok": False, "error": str(exc)})
            report["connections_ok"] = all(result["ok"] for result in connection_results)
        report["connections"] = connection_results
        return report

    def list_jira_instances(self) -> dict:
        """List the named Jira environments available to the assistant."""
        return {
            "instances": [
                {"name": name, "kind": cfg.kind, "base_url": cfg.base_url, "default_project": cfg.default_project}
                for name, cfg in self.settings.jira_instances().items()
            ]
        }

    def test_jira_connection(self, instance: str) -> dict:
        """Authenticate to a named Jira instance and return the current Jira user."""
        me = self.client(instance).myself()
        return {
            "ok": True,
            "instance": instance,
            "display_name": me.get("displayName") or me.get("name"),
            "account": me.get("emailAddress") or me.get("key"),
        }

    def discover_jira_environment(self, instance: str, project_key: str | None = None) -> dict:
        """Discover projects, fields, boards, and active/future sprints so natural-language requests do not require IDs."""
        jira = self.client(instance)
        project = project_key or jira.cfg.default_project
        fields = jira.fields()
        boards = jira.boards(project, limit=100)
        sprint_rows = []
        for board in boards[:20]:
            for state in ("active", "future"):
                try:
                    for sprint in jira.board_sprints(int(board["id"]), state=state, limit=50):
                        sprint_rows.append({**sprint, "boardId": board["id"], "boardName": board.get("name")})
                except Exception as exc:
                    sprint_rows.append({"boardId": board.get("id"), "boardName": board.get("name"), "state": state, "error": str(exc)})
        return {
            "instance": instance,
            "project": project,
            "projects": [{"key": p.get("key"), "name": p.get("name"), "id": p.get("id")} for p in jira.projects()],
            "fields": [{"name": field.get("name"), "custom": field.get("custom", False)} for field in fields],
            "boards": boards,
            "sprints": sprint_rows,
        }

    def search_issues(self, instance: str, jql: str, fields: list[str] | None = None, limit: int = 100) -> dict:
        """Search Jira using JQL. This tool is read-only and safe for exploratory natural-language questions."""
        rows = self.client(instance).search(
            jql,
            fields or ["summary", "status", "priority", "assignee", "created", "updated", "labels"],
            min(limit, self.settings.max_search_results),
        )
        return {"count": len(rows), "issues": [_sanitize_issue(row) for row in rows]}

    def search_issues_page(
        self,
        instance: str,
        jql: str,
        fields: list[str] | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        """Return a sanitized issue page for the Ops Console."""
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100))
        start = (page - 1) * page_size
        fetch_limit = min(start + page_size + 1, self.settings.max_search_results)
        jira = self.client(instance)
        default_fields = ["summary", "status", "priority", "assignee", "created", "updated", "labels", "issuetype"]
        rows = jira.search(jql, fields or default_fields, fetch_limit)
        page_rows = rows[start:start + page_size]
        has_next = len(rows) > start + page_size
        return {
            "instance": instance,
            "jql": jql,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "count": len(page_rows),
                "has_previous": page > 1,
                "has_next": has_next,
                "fetched": len(rows),
            },
            "issues": [_sanitize_issue(row) for row in page_rows],
        }

    def _build_field_update_preview(
        self,
        instance: str,
        jql: str,
        updates: dict[str, Any],
        limit: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        jira = self.client(instance)
        issues = jira.search(jql, ["summary"], limit)
        requested_updates = [{"field": field, "value": value} for field, value in updates.items()]
        resolved_fields: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, Any]] = []
        for name in updates:
            try:
                resolved_fields[name] = resolve_field(jira, name)
            except Exception as exc:
                errors.append({"field": name, "error": str(exc)})

        public_issues = []
        internal_issues = []
        for issue in issues:
            public_updates = []
            internal_fields = {}
            for name, value in updates.items():
                resolved = resolved_fields.get(name)
                if not resolved:
                    continue
                try:
                    internal_fields[resolved["id"]] = resolve_value_for_issue(jira, issue["key"], resolved["id"], value)
                    public_updates.append({"field": name, "value": value})
                except Exception as exc:
                    errors.append({"issue_key": issue["key"], "field": name, "error": str(exc)})
            public_issues.append({
                "issue_key": issue["key"],
                "summary": issue.get("fields", {}).get("summary"),
                "updates": public_updates,
            })
            internal_issues.append({"issue_key": issue["key"], "fields": internal_fields})

        preview = {
            "mode": self.settings.mode,
            "matched": len(issues),
            "updates": requested_updates,
            "issues": public_issues,
            "errors": errors,
            "can_apply": bool(issues) and not errors and self.settings.mode != "recommend_only",
        }
        return _with_preview_id(preview), internal_issues

    def preview_field_updates(self, instance: str, jql: str, updates: dict[str, Any], limit: int = 500) -> dict:
        """Preview bulk updates using human-readable Jira field names and displayed option values. Never writes."""
        preview, _ = self._build_field_update_preview(instance, jql, updates, limit)
        return preview

    def apply_field_updates(
        self,
        instance: str,
        jql: str,
        updates: dict[str, Any],
        limit: int = 500,
        preview_id: str | None = None,
    ) -> dict:
        """Apply a previously previewed reversible field update. Blocked in recommend_only mode."""
        preview, internal_issues = self._build_field_update_preview(instance, jql, updates, limit)
        if self.settings.mode == "recommend_only":
            return {**preview, "applied": False, "reason": "MODE=recommend_only"}
        if not preview_id:
            return {**preview, "applied": False, "reason": "preview_id is required; run preview_field_updates first"}
        if preview_id != preview["preview_id"]:
            return {**preview, "applied": False, "reason": "preview_id does not match the current plan"}
        if preview["errors"]:
            return {**preview, "applied": False, "reason": "Resolution errors must be fixed"}

        jira = self.client(instance)
        results = []
        for item in internal_issues:
            try:
                jira.update_issue(item["issue_key"], item["fields"])
                results.append({"issue_key": item["issue_key"], "ok": True})
            except Exception as exc:
                results.append({"issue_key": item["issue_key"], "ok": False, "error": str(exc)})
        return {"applied": all(result["ok"] for result in results), "preview_id": preview["preview_id"], "results": results}

    def assign_to_quarter(
        self,
        instance: str,
        jql: str,
        quarter: str,
        dry_run: bool = True,
        limit: int = 500,
        preview_id: str | None = None,
    ) -> dict:
        """Assign matching work to a displayed Target Quarter value without requiring field or option IDs."""
        field = self.settings.jira_instances()[instance].quarter_field_name
        if dry_run:
            return self.preview_field_updates(instance, jql, {field: quarter}, limit)
        return self.apply_field_updates(instance, jql, {field: quarter}, limit, preview_id=preview_id)

    def report_quarter_progress(self, instance: str, quarter: str, jql_extra: str = "", limit: int = 5000) -> dict:
        """Summarize delivery progress for a target quarter."""
        cfg = self.settings.jira_instances()[instance]
        jira = self.client(instance)
        field = resolve_field(jira, cfg.quarter_field_name)
        points_name, points_id = self._story_points_field(jira)
        jql = f'"{cfg.quarter_field_name}" = "{quarter}"' + (f" AND ({jql_extra})" if jql_extra else "")
        search_fields = ["summary", "status", "assignee", "updated", field["id"]]
        if points_id:
            search_fields.append(points_id)
        issues = jira.search(jql, search_fields, limit)
        counts = Counter((issue.get("fields", {}).get("status") or {}).get("name", "Unknown") for issue in issues)
        done_issues = [issue for issue in issues if is_done(issue)]
        total_points = sum(story_points(issue, points_name, points_id) for issue in issues)
        done_points = sum(story_points(issue, points_name, points_id) for issue in done_issues)
        aliases = {field["id"]: cfg.quarter_field_name}
        if points_id:
            aliases[points_id] = points_name
        return {
            "quarter": quarter,
            "count": len(issues),
            "status_counts": dict(counts),
            "completed_count": len(done_issues),
            "completion_percent": round(len(done_issues) * 100 / len(issues), 1) if issues else 0,
            "story_points": round(total_points, 2),
            "completed_story_points": round(done_points, 2),
            "story_point_completion_percent": round(done_points * 100 / total_points, 1) if total_points else None,
            "issues": [_sanitize_issue(issue, aliases) for issue in issues],
        }

    def report_sprint_progress(self, instance: str, sprint_id: int) -> dict:
        """Report sprint status, incomplete work, and story-point progress."""
        jira = self.client(instance)
        sprint = jira.sprint(sprint_id)
        points_name, points_id = self._story_points_field(jira)
        issues = jira.sprint_issues(sprint_id, story_points_field_id=points_id)
        counts = Counter((issue.get("fields", {}).get("status") or {}).get("name", "Unknown") for issue in issues)
        capacity = summarize_capacity(issues, points_name, points_id)
        aliases = {points_id: points_name} if points_id else {}
        return {
            "sprint": sprint,
            "count": len(issues),
            "status_counts": dict(counts),
            **capacity,
            "incomplete_issue_keys": [issue["key"] for issue in issues if not is_done(issue)],
            "issues": [_sanitize_issue(issue, aliases) for issue in issues],
        }

    def analyze_current_sprint(
        self,
        instance: str,
        sprint_id: int,
        next_sprint_id: int | None = None,
    ) -> dict[str, Any]:
        """Return current sprint intelligence for the Ops Console."""
        jira = self.client(instance)
        sprint = jira.sprint(sprint_id)
        next_sprint = jira.sprint(next_sprint_id) if next_sprint_id else None
        points_name, points_id = self._story_points_field(jira)
        current_issues = jira.sprint_issues(sprint_id, story_points_field_id=points_id)
        next_issues = jira.sprint_issues(next_sprint_id, story_points_field_id=points_id) if next_sprint_id else []
        board_id = (
            (next_sprint or {}).get("originBoardId")
            or sprint.get("originBoardId")
            or jira.cfg.default_board_id
        )
        normalized_board_id = int(board_id) if board_id else None
        capacity = self._derive_capacity(jira, normalized_board_id, points_name, points_id)
        baseline_samples: list[dict[str, Any]] = []
        try:
            baseline_samples = self._recent_capacity_samples(jira, normalized_board_id, points_name, points_id)
        except Exception as exc:
            logger.warning("Could not load recent sprint baseline for %s: %s", jira.name, exc)
        aliases = {points_id: points_name} if points_id else {}
        return {
            "mode": self.settings.mode,
            "instance": instance,
            "sprint": sprint,
            "next_sprint": next_sprint,
            "recent_sprint_capacity_baseline": {
                "samples": baseline_samples,
                "average_completed_story_points": round(
                    mean([sample["completed_story_points"] for sample in baseline_samples]),
                    2,
                ) if baseline_samples else None,
            },
            "analysis": sprint_intelligence(
                current_issues,
                next_issues,
                points_name,
                points_id,
                capacity,
                jira.cfg.sprint_capacity_buffer_percent,
            ),
            "issues": [_sanitize_issue(issue, aliases) for issue in current_issues],
        }

    def analyze_next_sprint_capacity(
        self,
        instance: str,
        sprint_id: int,
        additional_issue_keys: list[str] | None = None,
        additional_story_points: float = 0,
    ) -> dict:
        """Check whether a sprint is or will become overcommitted, using configured or recent historical capacity."""
        jira = self.client(instance)
        sprint = jira.sprint(sprint_id)
        points_name, points_id = self._story_points_field(jira)
        issues = jira.sprint_issues(sprint_id, story_points_field_id=points_id)
        existing = summarize_capacity(issues, points_name, points_id)
        extra_issues = []
        if additional_issue_keys:
            for key in additional_issue_keys:
                extra_issues.append(jira.get_issue(key, ["summary", "status", points_id or points_name]))
        added_points = additional_story_points + sum(story_points(issue, points_name, points_id) for issue in extra_issues)
        board_id = sprint.get("originBoardId") or jira.cfg.default_board_id
        capacity = self._derive_capacity(jira, int(board_id) if board_id else None, points_name, points_id)
        analysis = overcommit_analysis(
            existing["story_points"],
            added_points,
            capacity["story_points"],
            jira.cfg.sprint_capacity_buffer_percent,
            existing["issue_count"],
            len(extra_issues),
            capacity["issue_count"],
        )
        return {"sprint": sprint, "capacity_source": capacity["source"], **analysis}

    def preview_close_sprint(
        self,
        instance: str,
        sprint_id: int,
        next_sprint_id: int,
        move_issue_keys: list[str] | None = None,
        split_plans: list[dict[str, Any]] | None = None,
        rollover_all_incomplete: bool = False,
    ) -> dict:
        """Preview sprint closure, rollover, issue splitting, and next-sprint overcommit. Never writes."""
        jira = self.client(instance)
        current_sprint = jira.sprint(sprint_id)
        next_sprint = jira.sprint(next_sprint_id)
        points_name, points_id = self._story_points_field(jira)
        current_issues = jira.sprint_issues(sprint_id, story_points_field_id=points_id)
        current_map = {issue["key"]: issue for issue in current_issues}
        incomplete = [issue for issue in current_issues if not is_done(issue)]
        move_keys = list(dict.fromkeys(move_issue_keys or ([] if not rollover_all_incomplete else [issue["key"] for issue in incomplete])))
        plans = split_plans or []
        split_sources = {plan.get("source_issue_key") for plan in plans if plan.get("source_issue_key")}
        if rollover_all_incomplete:
            move_keys = [key for key in move_keys if key not in split_sources]
        unknown = sorted((set(move_keys) | split_sources) - set(current_map))
        moved_points = sum(story_points(current_map[key], points_name, points_id) for key in move_keys if key in current_map)
        split_points = 0.0
        plan_previews = []
        errors = []
        for plan in plans:
            key = plan.get("source_issue_key")
            source = current_map.get(key)
            if not source:
                continue
            pts = plan.get("story_points")
            if pts is None:
                pts = story_points(source, points_name, points_id)
            try:
                pts = float(pts or 0)
            except (TypeError, ValueError):
                errors.append({"source_issue_key": key, "error": "story_points must be numeric"})
                pts = 0
            split_points += pts
            source_type = ((source.get("fields") or {}).get("issuetype") or {}).get("name")
            plan_previews.append({
                "source_issue_key": key,
                "source_summary": (source.get("fields") or {}).get("summary"),
                "source_issue_type": source_type,
                "new_summary": plan.get("new_summary"),
                "new_issue_type": plan.get("new_issue_type") or source_type,
                "story_points": pts,
                "parent_key": plan.get("parent_key"),
                "source_transition_status": plan.get("source_transition_status"),
                "will_move_new_issue_to_next_sprint": plan.get("move_new_issue_to_next_sprint", True),
            })
            if not plan.get("new_summary"):
                errors.append({"source_issue_key": key, "error": "new_summary is required"})
            if not plan.get("source_transition_status"):
                errors.append({
                    "source_issue_key": key,
                    "error": "source_transition_status is required so the original work is explicitly resolved before sprint closure",
                })
        next_issues = jira.sprint_issues(next_sprint_id, story_points_field_id=points_id)
        next_existing = summarize_capacity(next_issues, points_name, points_id)
        board_id = next_sprint.get("originBoardId") or current_sprint.get("originBoardId") or jira.cfg.default_board_id
        capacity = self._derive_capacity(jira, int(board_id) if board_id else None, points_name, points_id)
        overcommit = overcommit_analysis(
            next_existing["story_points"],
            moved_points + split_points,
            capacity["story_points"],
            jira.cfg.sprint_capacity_buffer_percent,
            next_existing["issue_count"],
            len(move_keys) + len(plans),
            capacity["issue_count"],
        )
        unhandled = sorted(set(issue["key"] for issue in incomplete) - set(move_keys) - split_sources)
        if unhandled:
            errors.append({"error": "Incomplete issues would remain unhandled when the sprint closes", "issue_keys": unhandled})
        preview = {
            "mode": self.settings.mode,
            "current_sprint": current_sprint,
            "next_sprint": next_sprint,
            "current_incomplete_issue_keys": [issue["key"] for issue in incomplete],
            "move_issue_keys": move_keys,
            "split_plans": plan_previews,
            "unknown_issue_keys": unknown,
            "unhandled_incomplete_issue_keys": unhandled,
            "next_sprint_capacity": {"capacity_source": capacity["source"], **overcommit},
            "warnings": (["NEXT SPRINT IS PROJECTED TO BE OVERCOMMITTED"] if overcommit["overcommitted"] else []),
            "errors": errors,
            "can_apply": self.settings.mode == "approved_destructive" and not unknown and not errors,
        }
        return _with_preview_id(preview)

    def apply_close_sprint(
        self,
        instance: str,
        sprint_id: int,
        next_sprint_id: int,
        move_issue_keys: list[str] | None = None,
        split_plans: list[dict[str, Any]] | None = None,
        rollover_all_incomplete: bool = False,
        preview_id: str | None = None,
    ) -> dict:
        """Execute an explicitly approved sprint-close plan."""
        preview = self.preview_close_sprint(instance, sprint_id, next_sprint_id, move_issue_keys, split_plans, rollover_all_incomplete)
        if self.settings.mode != "approved_destructive":
            return {**preview, "applied": False, "reason": "MODE must be approved_destructive"}
        if not preview_id:
            return {**preview, "applied": False, "reason": "preview_id is required; run preview_close_sprint first"}
        if preview_id != preview["preview_id"]:
            return {**preview, "applied": False, "reason": "preview_id does not match the current plan"}
        if not preview["can_apply"]:
            return {**preview, "applied": False, "reason": "Preview contains blocking errors"}

        jira = self.client(instance)
        points_name, points_id = self._story_points_field(jira)
        created, transitions = [], []
        new_issue_keys = []
        for plan in split_plans or []:
            source = jira.get_issue(plan["source_issue_key"], ["summary", "description", "issuetype", "project", "parent", points_id or points_name])
            source_fields = source.get("fields") or {}
            project_key = (source_fields.get("project") or {}).get("key")
            issue_type = plan.get("new_issue_type") or (source_fields.get("issuetype") or {}).get("name")
            fields: dict[str, Any] = {
                "project": {"key": project_key},
                "summary": plan["new_summary"],
                "issuetype": {"name": issue_type},
                "description": jira.description_value(
                    plan.get("new_description")
                    or f"Follow-on work split from {plan['source_issue_key']} during sprint closure."
                ),
            }
            if plan.get("parent_key"):
                fields["parent"] = {"key": plan["parent_key"]}
            if points_id and plan.get("story_points") is not None:
                fields[points_id] = float(plan["story_points"])
            result = jira.create_issue(fields)
            new_key = result.get("key")
            created.append({"source_issue_key": plan["source_issue_key"], "new_issue_key": new_key})
            if new_key and plan.get("move_new_issue_to_next_sprint", True):
                new_issue_keys.append(new_key)
            transitions.append(jira.transition_issue_to_status(plan["source_issue_key"], plan["source_transition_status"]))
        all_move = list(dict.fromkeys((preview["move_issue_keys"] or []) + new_issue_keys))
        moved_batches = jira.move_issues_to_sprint(next_sprint_id, all_move) if all_move else []
        closed = jira.update_sprint(sprint_id, {"state": "closed"})
        return {
            "applied": True,
            "preview_id": preview["preview_id"],
            "created_issues": created,
            "source_transitions": transitions,
            "moved_to_next_sprint": all_move,
            "move_batches": moved_batches,
            "closed_sprint": closed,
            "next_sprint_capacity": preview["next_sprint_capacity"],
            "warnings": preview["warnings"],
        }

    def create_execution_preview(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Create and store an execution preview for console approve/reject workflows."""
        params = dict(parameters)
        instance = params.get("instance")
        if not instance:
            raise ValueError("instance is required")
        if action == "field_updates":
            preview = self.preview_field_updates(
                instance,
                params["jql"],
                params["updates"],
                int(params.get("limit", 500)),
            )
        elif action == "assign_to_quarter":
            preview = self.assign_to_quarter(
                instance,
                params["jql"],
                params["quarter"],
                dry_run=True,
                limit=int(params.get("limit", 500)),
            )
        elif action == "close_sprint":
            preview = self.preview_close_sprint(
                instance,
                int(params["sprint_id"]),
                int(params["next_sprint_id"]),
                params.get("move_issue_keys"),
                params.get("split_plans"),
                bool(params.get("rollover_all_incomplete", False)),
            )
        else:
            raise ValueError(f"Unsupported execution action: {action}")
        return self.execution_store.add_preview(action, instance, params, preview)

    def apply_execution_preview(self, preview_id: str) -> dict[str, Any]:
        """Apply a stored preview through the same backend write gates used by MCP."""
        record = self.execution_store.get_record(preview_id).to_dict()
        action = record["action"]
        params = record["parameters"]
        instance = record["instance"]
        if action == "field_updates":
            result = self.apply_field_updates(
                instance,
                params["jql"],
                params["updates"],
                int(params.get("limit", 500)),
                preview_id=preview_id,
            )
        elif action == "assign_to_quarter":
            result = self.assign_to_quarter(
                instance,
                params["jql"],
                params["quarter"],
                dry_run=False,
                limit=int(params.get("limit", 500)),
                preview_id=preview_id,
            )
        elif action == "close_sprint":
            result = self.apply_close_sprint(
                instance,
                int(params["sprint_id"]),
                int(params["next_sprint_id"]),
                params.get("move_issue_keys"),
                params.get("split_plans"),
                bool(params.get("rollover_all_incomplete", False)),
                preview_id=preview_id,
            )
        else:
            raise ValueError(f"Unsupported execution action: {action}")
        return self.execution_store.mark_applied(preview_id, result)

    def reject_execution_preview(self, preview_id: str) -> dict[str, Any]:
        """Reject a stored preview without writing to external systems."""
        return self.execution_store.mark_rejected(preview_id)

    def execution_history(self, limit: int = 50) -> dict[str, Any]:
        """Return recent console execution previews and outcomes."""
        return {"executions": self.execution_store.list(limit)}

    def list_local_repositories(self) -> dict:
        """List locally checked-out repositories under LOCAL_REPO_ROOT. Read-only."""
        root = self.settings.local_repo_path
        if not root:
            return {"configured": False, "repositories": [], "error": "LOCAL_REPO_ROOT is not configured"}
        return {"configured": True, "root": str(root), "repositories": discover_repositories(root)}

    def scan_repository_packages(self) -> dict:
        """Scan local dependency and container manifests across all checked-out repositories. Read-only."""
        root = self.settings.local_repo_path
        if not root:
            return {"configured": False, "packages": [], "error": "LOCAL_REPO_ROOT is not configured"}
        rows = scan_manifests(root)
        return {"configured": True, "root": str(root), "count": len(rows), "packages": rows}

    def analyze_security_package_updates(self, instance: str, project_key: str | None = None, limit: int = 2000) -> dict:
        """Normalize Operational Security Issue tickets into package remediation candidates and compare them with local repositories."""
        jira = self.client(instance)
        project = project_key or jira.cfg.default_project
        marker = self.settings.security_issue_summary_marker.replace('"', '\\"')
        jql = (
            f'project = {project} AND summary ~ "\\"{marker}\\"" ORDER BY updated DESC'
            if project
            else f'summary ~ "\\"{marker}\\"" ORDER BY updated DESC'
        )
        issues = jira.search(
            jql,
            ["summary", "description", "status", "updated", "labels", "components"],
            min(limit, self.settings.max_search_results),
        )
        ticket_rows = []
        aggregate: dict[tuple[str, str], dict[str, Any]] = {}
        for issue in issues:
            fields = issue.get("fields") or {}
            text = (fields.get("summary") or "") + "\n" + _text_from_adf(fields.get("description"))
            signals = extract_security_signals(text)
            ticket_rows.append({"issue_key": issue["key"], "summary": fields.get("summary"), **signals})
            for fix in signals["fixed_versions"]:
                package = fix.get("package")
                version = fix.get("required_version")
                if package and version:
                    key = (package, version)
                    row = aggregate.setdefault(key, {"package": package, "required_version": version, "issue_keys": [], "cves": set()})
                    row["issue_keys"].append(issue["key"])
                    row["cves"].update(signals["cves"])
        repo_rows = scan_manifests(self.settings.local_repo_path) if self.settings.local_repo_path else []
        repo_by_package = defaultdict(list)
        for row in repo_rows:
            if row.get("package"):
                repo_by_package[str(row["package"]).casefold()].append(row)
        normalized = []
        for row in aggregate.values():
            normalized.append({
                "package": row["package"],
                "required_version": row["required_version"],
                "ticket_count": len(set(row["issue_keys"])),
                "issue_keys": sorted(set(row["issue_keys"])),
                "cves": sorted(row["cves"]),
                "repo_occurrences": repo_by_package.get(row["package"].casefold(), []),
            })
        normalized.sort(key=lambda row: (-row["ticket_count"], row["package"]))
        return {
            "matched_tickets": len(issues),
            "normalized_upgrade_actions": normalized,
            "raw_ticket_analysis": ticket_rows,
            "repo_scan_available": bool(self.settings.local_repo_path),
        }

    def engineering_health(self, instance: str, jql: str, stale_days: int = 90, limit: int = 5000) -> dict:
        """Summarize engineering operational health: stale, blocked, unassigned, status mix, and domain labels."""
        issues = self.client(instance).search(
            jql,
            ["summary", "status", "assignee", "updated", "created", "labels", "priority"],
            min(limit, self.settings.max_search_results),
        )
        return {"instance": instance, "jql": jql, **health_summary(issues, stale_days)}


backend = EngineeringOpsBackend()
