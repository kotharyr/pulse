from __future__ import annotations

from typing import Any, Callable

from engineering_ops.config import settings
from engineering_ops.models import (
    Confidence,
    ExecutionPreviewReference,
    Finding,
    Metric,
    Recommendation,
    Risk,
    SourceCoverage,
)


DEFAULT_WINDOW = "-30d"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _quote_jql(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return '""'
    if text.replace("_", "").replace("-", "").isalnum() and text.upper() == text:
        return text
    return '"' + text.replace('"', '\\"') + '"'


def _bounded_jql(project: str | None = None, time_window: str | None = None, extra: str | None = None) -> str:
    clauses = []
    if project:
        clauses.append(f"project = {_quote_jql(project)}")
    clauses.append(f"updated >= {time_window or DEFAULT_WINDOW}")
    if extra:
        clauses.append(f"({extra})")
    return " AND ".join(clauses) + " ORDER BY updated DESC"


def _completion_from_analysis(data: dict[str, Any]) -> dict[str, Any]:
    analysis = data.get("analysis") or {}
    story_points = analysis.get("story_points") or {}
    overcommit = analysis.get("overcommit") or {}
    return {
        "completion_percent": story_points.get("completion_percent", analysis.get("completion_percent", 0)),
        "completed_story_points": story_points.get("completed", 0),
        "remaining_story_points": story_points.get("remaining", 0),
        "total_story_points": story_points.get("total", 0),
        "overcommit_percent": overcommit.get("overcommit_percentage"),
        "overcommitted": overcommit.get("overcommitted", False),
    }


class EngineeringOrchestrator:
    """Task-oriented orchestration over the shared backend capability layer."""

    def __init__(self, backend: Any):
        self.backend = backend

    @property
    def mode(self) -> str:
        backend_settings = getattr(self.backend, "settings", None)
        return getattr(backend_settings, "mode", settings.mode)

    def _response(
        self,
        workflow: str,
        *,
        inputs: dict[str, Any],
        summary: str,
        metrics: list[Metric] | None = None,
        findings: list[Finding] | None = None,
        risks: list[Risk] | None = None,
        recommendations: list[Recommendation] | None = None,
        source_coverage: list[SourceCoverage] | None = None,
        sections: dict[str, Any] | None = None,
        preview: ExecutionPreviewReference | None = None,
        caveats: list[str] | None = None,
    ) -> dict[str, Any]:
        coverage = source_coverage or []
        confidence = self._confidence(coverage, caveats or [])
        return {
            "workflow": workflow,
            "mode": self.mode,
            "inputs": {key: value for key, value in inputs.items() if value is not None},
            "summary": summary,
            "metrics": [metric.to_dict() for metric in metrics or []],
            "findings": [finding.to_dict() for finding in findings or []],
            "risks": [risk.to_dict() for risk in risks or []],
            "recommendations": [recommendation.to_dict() for recommendation in recommendations or []],
            "source_coverage": [source.to_dict() for source in coverage],
            "confidence": confidence.to_dict(),
            "execution_preview": preview.to_dict() if preview else None,
            "sections": sections or {},
        }

    def _confidence(self, coverage: list[SourceCoverage], caveats: list[str]) -> Confidence:
        if not coverage:
            return Confidence(0.5, "medium", caveats or ["No external source coverage was needed."])
        ok = sum(1 for source in coverage if source.status == "ok")
        partial = sum(1 for source in coverage if source.status == "partial")
        score = round((ok + partial * 0.5) / len(coverage), 2)
        level = "high" if score >= 0.8 else "medium" if score >= 0.45 else "low"
        generated = [source.details for source in coverage if source.status != "ok" and source.details]
        return Confidence(score, level, [*caveats, *generated])

    def _source(self, source: str, status: str = "ok", details: str | None = None, error: str | None = None) -> SourceCoverage:
        return SourceCoverage(source=source, status=status, details=details, error=error)

    def _safe(self, coverage: list[SourceCoverage], source: str, fn: Callable[[], Any], default: Any) -> Any:
        try:
            result = fn()
            coverage.append(self._source(source, "ok"))
            return result
        except Exception as exc:
            coverage.append(self._source(source, "failed", f"{source} unavailable", str(exc)))
            return default

    def _instance_names(self, instance: str | None = None, instances: list[str] | str | None = None) -> list[str]:
        requested = _as_list(instances) or _as_list(instance)
        if requested:
            return requested
        try:
            rows = self.backend.list_jira_instances().get("instances", [])
        except Exception:
            rows = []
        return [row["name"] for row in rows if row.get("name")] or ["cloud"]

    def _resolve_sprint_ids(
        self,
        instance: str,
        *,
        project: str | None = None,
        sprint_name: str | None = None,
        sprint_id: int | None = None,
        next_sprint_name: str | None = None,
        next_sprint_id: int | None = None,
        coverage: list[SourceCoverage] | None = None,
    ) -> tuple[int | None, int | None, dict[str, Any]]:
        details: dict[str, Any] = {"selection": "explicit" if sprint_id else "discovery"}
        local_coverage = coverage if coverage is not None else []
        if sprint_id and next_sprint_id:
            return int(sprint_id), int(next_sprint_id), details

        if sprint_name or next_sprint_name:
            env = self._safe(
                local_coverage,
                "environment",
                lambda: self.backend.discover_environment(instance, project, True),
                {},
            )
            sprints = env.get("sprints") or []
            if sprint_name and not sprint_id:
                match = self._match_named_sprint(sprints, sprint_name)
                sprint_id = match.get("id") if match else None
                details["sprint_name"] = sprint_name
            if next_sprint_name and not next_sprint_id:
                match = self._match_named_sprint(sprints, next_sprint_name)
                next_sprint_id = match.get("id") if match else None
                details["next_sprint_name"] = next_sprint_name

        if not sprint_id or not next_sprint_id:
            discovery = self._safe(
                local_coverage,
                "sprint_discovery",
                lambda: self.backend.discover_console_sprints(instance, project),
                {},
            )
            if not sprint_id:
                sprint_id = (discovery.get("current_sprint") or {}).get("id")
            if not next_sprint_id:
                next_sprint_id = (discovery.get("next_sprint") or {}).get("id")
            details["discovery"] = discovery.get("selection") or {}

        return int(sprint_id) if sprint_id else None, int(next_sprint_id) if next_sprint_id else None, details

    def _match_named_sprint(self, sprints: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        target = name.casefold()
        for sprint in sprints:
            if str(sprint.get("name") or "").casefold() == target:
                return sprint
        for sprint in sprints:
            if target in str(sprint.get("name") or "").casefold():
                return sprint
        return None

    def sprint_analysis(
        self,
        instance: str | None = None,
        *,
        team: str | None = None,
        project: str | None = None,
        board: str | None = None,
        sprint_name: str | None = None,
        sprint_id: int | None = None,
        next_sprint_name: str | None = None,
        next_sprint_id: int | None = None,
    ) -> dict[str, Any]:
        selected_instance = self._instance_names(instance)[0]
        coverage: list[SourceCoverage] = []
        current_id, next_id, resolution = self._resolve_sprint_ids(
            selected_instance,
            project=project,
            sprint_name=sprint_name,
            sprint_id=sprint_id,
            next_sprint_name=next_sprint_name,
            next_sprint_id=next_sprint_id,
            coverage=coverage,
        )
        risks: list[Risk] = []
        recommendations: list[Recommendation] = []
        if not current_id:
            risks.append(Risk("Sprint not resolved", "No current or matching sprint could be resolved.", "high"))
            return self._response(
                "sprint_analysis",
                inputs={
                    "instance": selected_instance,
                    "team": team,
                    "project": project,
                    "board": board,
                    "sprint_name": sprint_name,
                    "sprint_id": sprint_id,
                    "next_sprint_name": next_sprint_name,
                    "next_sprint_id": next_sprint_id,
                },
                summary="Sprint analysis could not run because no sprint was resolved.",
                risks=risks,
                source_coverage=coverage,
                sections={"resolution": resolution},
            )

        data = self._safe(
            coverage,
            "sprint_analysis",
            lambda: self.backend.analyze_current_sprint(selected_instance, current_id, next_id),
            {},
        )
        analysis = data.get("analysis") or {}
        points = analysis.get("story_points") or {}
        blocked = analysis.get("blocked_work") or []
        rollover = analysis.get("rollover_candidates") or []
        splits = analysis.get("issue_split_proposals") or []
        overcommit = analysis.get("overcommit") or {}
        completion = _completion_from_analysis(data)

        if blocked:
            risks.append(Risk("Blocked sprint work", f"{len(blocked)} issue(s) are blocked.", "high", [row.get("issue_key") for row in blocked]))
            recommendations.append(Recommendation("Clear blocked sprint issues first", "Blocked items are most likely to affect sprint completion.", "high"))
        if rollover:
            recommendations.append(Recommendation("Prepare rollover plan", f"{len(rollover)} incomplete issue(s) may need next-sprint handling.", "high"))
        if splits:
            recommendations.append(Recommendation("Review split candidates", "Large or partially complete work may be safer as follow-on issues.", "medium"))
        if overcommit.get("overcommitted"):
            risks.append(Risk("Next sprint overcommitted", "Projected next-sprint load exceeds capacity.", "high"))
            recommendations.append(Recommendation("Reduce next sprint scope", "Bring projected load back under the capacity baseline.", "high"))

        metrics = [
            Metric("completion_percent", completion["completion_percent"], "percent"),
            Metric("story_points_completed", completion["completed_story_points"], "points"),
            Metric("story_points_remaining", completion["remaining_story_points"], "points"),
            Metric("overcommit_percent", completion["overcommit_percent"], "percent"),
            Metric("blocked_issue_count", len(blocked), "issues"),
            Metric("rollover_candidate_count", len(rollover), "issues"),
        ]
        return self._response(
            "sprint_analysis",
            inputs={
                "instance": selected_instance,
                "team": team,
                "project": project,
                "board": board,
                "sprint_name": sprint_name,
                "sprint_id": sprint_id,
                "next_sprint_name": next_sprint_name,
                "next_sprint_id": next_sprint_id,
            },
            summary=f"Sprint is {completion['completion_percent']}% complete with {completion['remaining_story_points']} story points remaining.",
            metrics=metrics,
            findings=[
                Finding("Sprint completion", "Completion and workload were calculated from Jira sprint issues.", "info", "sprint", [points]),
            ],
            risks=risks,
            recommendations=recommendations,
            source_coverage=coverage,
            sections={
                "sprint": data.get("sprint"),
                "next_sprint": data.get("next_sprint"),
                "progress_by_team": analysis.get("progress_by_team") or [],
                "progress_by_engineer": analysis.get("progress_by_engineer") or [],
                "blocked_issues": blocked,
                "rollover_candidates": rollover,
                "likely_split_candidates": splits,
                "next_sprint_projected_load": analysis.get("projected_next_sprint_load") or {},
                "capacity_baseline": data.get("recent_sprint_capacity_baseline") or analysis.get("next_sprint_capacity") or {},
                "overcommit": overcommit,
                "resolution": resolution,
                "issues": data.get("issues") or [],
            },
        )

    def sprint_close_preview(
        self,
        instance: str | None = None,
        *,
        project: str | None = None,
        sprint_name: str | None = None,
        sprint_id: int | None = None,
        next_sprint_name: str | None = None,
        next_sprint_id: int | None = None,
        move_issue_keys: list[str] | None = None,
        split_plans: list[dict[str, Any]] | None = None,
        rollover_all_incomplete: bool = True,
    ) -> dict[str, Any]:
        selected_instance = self._instance_names(instance)[0]
        coverage: list[SourceCoverage] = []
        current_id, next_id, resolution = self._resolve_sprint_ids(
            selected_instance,
            project=project,
            sprint_name=sprint_name,
            sprint_id=sprint_id,
            next_sprint_name=next_sprint_name,
            next_sprint_id=next_sprint_id,
            coverage=coverage,
        )
        if not current_id or not next_id:
            return self._response(
                "sprint_close_preview",
                inputs={
                    "instance": selected_instance,
                    "project": project,
                    "sprint_name": sprint_name,
                    "sprint_id": sprint_id,
                    "next_sprint_name": next_sprint_name,
                    "next_sprint_id": next_sprint_id,
                    "rollover_all_incomplete": rollover_all_incomplete,
                },
                summary="Sprint close preview could not run because current or next sprint was not resolved.",
                risks=[Risk("Sprint close target missing", "Both current and next sprint must be resolved before preview.", "high")],
                source_coverage=coverage,
                sections={"resolution": resolution},
            )

        record = self._safe(
            coverage,
            "execution_preview",
            lambda: self.backend.create_execution_preview(
                "close_sprint",
                {
                    "instance": selected_instance,
                    "sprint_id": current_id,
                    "next_sprint_id": next_id,
                    "move_issue_keys": move_issue_keys,
                    "split_plans": split_plans or [],
                    "rollover_all_incomplete": rollover_all_incomplete,
                },
            ),
            {},
        )
        preview = record.get("preview") or {}
        analysis = self._safe(
            coverage,
            "sprint_analysis",
            lambda: self.backend.analyze_current_sprint(selected_instance, current_id, next_id),
            {},
        )
        issue_rows = analysis.get("issues") or []
        incomplete_keys = set(preview.get("current_incomplete_issue_keys") or [])
        complete = [row.get("key") for row in issue_rows if row.get("key") and row.get("key") not in incomplete_keys]
        risks = [
            Risk("Next sprint overcommit", "Preview projects the next sprint over capacity.", "high")
            for warning in preview.get("warnings") or []
            if "OVERCOMMITTED" in str(warning)
        ]
        recommendations = [
            Recommendation("Review sprint close preview", "Approve only after rollover, split, and close actions match the team plan.", "high", preview_id=record.get("preview_id")),
        ]
        can_apply = bool((record.get("preview") or {}).get("can_apply"))
        preview_ref = ExecutionPreviewReference(record.get("preview_id"), "close_sprint", record.get("status", "previewed"), can_apply) if record.get("preview_id") else None
        return self._response(
            "sprint_close_preview",
            inputs={
                "instance": selected_instance,
                "project": project,
                "sprint_name": sprint_name,
                "sprint_id": sprint_id,
                "next_sprint_name": next_sprint_name,
                "next_sprint_id": next_sprint_id,
                "rollover_all_incomplete": rollover_all_incomplete,
            },
            summary="Sprint close preview created. No changes were applied.",
            metrics=[
                Metric("complete_issue_count", len(complete), "issues"),
                Metric("incomplete_issue_count", len(incomplete_keys), "issues"),
                Metric("proposed_rollover_count", len(preview.get("move_issue_keys") or []), "issues"),
                Metric("proposed_split_count", len(preview.get("split_plans") or []), "issues"),
            ],
            risks=risks,
            recommendations=recommendations,
            source_coverage=coverage,
            preview=preview_ref,
            sections={
                "issues_complete": complete,
                "issues_incomplete": sorted(incomplete_keys),
                "proposed_rollover": preview.get("move_issue_keys") or [],
                "proposed_split_work": preview.get("split_plans") or [],
                "next_sprint_load": preview.get("next_sprint_capacity") or {},
                "capacity_baseline": (analysis.get("recent_sprint_capacity_baseline") or {}),
                "overcommit_warning": preview.get("warnings") or [],
                "exact_actions": {
                    "move_issue_keys": preview.get("move_issue_keys") or [],
                    "create_split_issues": preview.get("split_plans") or [],
                    "close_sprint": bool(preview),
                },
                "preview": preview,
                "record": record,
                "resolution": resolution,
            },
        )

    def sprint_close_apply(self, preview_id: str) -> dict[str, Any]:
        coverage: list[SourceCoverage] = []
        if not preview_id:
            return self._response(
                "sprint_close_apply",
                inputs={"preview_id": preview_id},
                summary="Sprint close apply requires a stored preview id.",
                risks=[Risk("Preview id required", "Apply operations must reference a reviewed execution preview.", "high")],
                source_coverage=coverage,
            )
        record = self._safe(coverage, "execution_apply", lambda: self.backend.apply_execution_preview(preview_id), {})
        result = record.get("result") or {}
        reason = record.get("error") or result.get("reason")
        risks = []
        if record.get("status") != "succeeded":
            risks.append(Risk("Sprint close not applied", reason or "Execution did not complete.", "high"))
        if reason and "does not match" in reason:
            risks.append(Risk("Preview is stale", "The sprint close plan no longer matches current source data.", "high"))
        return self._response(
            "sprint_close_apply",
            inputs={"preview_id": preview_id},
            summary="Sprint close applied." if record.get("status") == "succeeded" else "Sprint close was not applied.",
            metrics=[Metric("applied", bool(result.get("applied")), "boolean")],
            risks=risks,
            recommendations=[] if record.get("status") == "succeeded" else [Recommendation("Regenerate preview", "Review the latest sprint state before applying again.", "high")],
            source_coverage=coverage,
            sections={"record": record, "result": result},
        )

    def security_remediation_analysis(
        self,
        instance: str | None = None,
        *,
        project: str | None = None,
        limit: int = 2000,
    ) -> dict[str, Any]:
        selected_instance = self._instance_names(instance)[0]
        coverage: list[SourceCoverage] = []
        data = self._safe(
            coverage,
            "security_remediation",
            lambda: self.backend.analyze_security_package_updates(selected_instance, project, limit),
            {},
        )
        actions = sorted(
            data.get("remediation_actions") or [],
            key=lambda row: (_number(row.get("tickets_potentially_cleared")), _number(row.get("confidence"))),
            reverse=True,
        )
        recommendations = [
            Recommendation(
                f"Upgrade {action.get('component')}",
                f"Could clear {action.get('tickets_potentially_cleared', 0)} Operational Security Issue ticket(s).",
                "high" if index == 0 else "medium",
            )
            for index, action in enumerate(actions[:5])
        ]
        return self._response(
            "security_remediation_analysis",
            inputs={"instance": selected_instance, "project": project, "limit": limit},
            summary=f"Found {len(actions)} normalized remediation opportunity/opportunities.",
            metrics=[
                Metric("matched_ticket_count", data.get("matched_tickets", 0), "tickets"),
                Metric("remediation_action_count", len(actions), "actions"),
            ],
            findings=[Finding("Ranked remediation actions", "Actions are grouped by package/component and required version.", "info", "security", actions[:5])],
            recommendations=recommendations,
            source_coverage=coverage,
            sections={
                "ranked_remediation_opportunities": actions,
                "raw_ticket_analysis": data.get("raw_ticket_analysis") or [],
                "repository_inventory": data.get("repository_inventory") or [],
            },
        )

    def saved_view_review(
        self,
        view_name: str,
        *,
        instance: str | None = None,
        page: int = 1,
        page_size: int = 25,
        limit: int | None = None,
    ) -> dict[str, Any]:
        coverage: list[SourceCoverage] = []
        view = self._safe(coverage, "saved_view", lambda: self.backend.get_saved_view(view_name)["view"], {})
        if not view:
            return self._response(
                "saved_view_review",
                inputs={"view_name": view_name, "instance": instance, "page": page, "page_size": page_size},
                summary="Saved view was not found.",
                risks=[Risk("Saved view missing", f"No saved operational view named {view_name}.", "medium")],
                source_coverage=coverage,
            )
        selected_instance = instance or view.get("instance")
        if instance:
            results = self._safe(
                coverage,
                "saved_view_search",
                lambda: self.backend.search_issues_page(selected_instance, view["jql"], page=page, page_size=limit or page_size),
                {},
            )
        else:
            results = self._safe(
                coverage,
                "saved_view_search",
                lambda: self.backend.search_saved_view(view_name, page, limit or page_size)["results"],
                {},
            )
        issues = results.get("issues") or []
        risks = []
        if not issues:
            risks.append(Risk("No issues returned", "The saved view returned no issues or could not be queried.", "low"))
        return self._response(
            "saved_view_review",
            inputs={"view_name": view_name, "instance": instance, "page": page, "page_size": page_size, "limit": limit},
            summary=f"Saved view {view.get('name', view_name)} returned {len(issues)} issue(s) on this page.",
            metrics=[Metric("issue_count", len(issues), "issues")],
            findings=[Finding("Saved view query", "The saved view was run through the shared search service.", "info", "saved_view", [view.get("jql")])],
            risks=risks,
            recommendations=[Recommendation("Review returned risks first", "Saved views are intended to focus operational attention.", "medium")],
            source_coverage=coverage,
            sections={"view": view, "paginated_issues": results, "issues": issues},
        )

    def backlog_review(
        self,
        instance: str | None = None,
        *,
        project: str | None = None,
        team: str | None = None,
        time_window: str | None = "-90d",
        limit: int = 100,
    ) -> dict[str, Any]:
        selected_instance = self._instance_names(instance)[0]
        coverage: list[SourceCoverage] = []
        jql = _bounded_jql(project, time_window, "resolution is EMPTY")
        health = self._safe(coverage, "engineering_health", lambda: self.backend.engineering_health(selected_instance, jql, 90, limit), {})
        page = self._safe(coverage, "issue_search", lambda: self.backend.search_issues_page(selected_instance, jql, page=1, page_size=min(limit, 100)), {})
        issues = page.get("issues") or []
        stale = health.get("stale_issue_keys") or []
        blocked = health.get("blocked_issue_keys") or []
        unassigned = health.get("unassigned_issue_keys") or []
        low_quality = [
            issue.get("key")
            for issue in issues
            if len(str((issue.get("fields") or {}).get("summary") or "")) < 12
        ]
        urgent = [
            issue.get("key")
            for issue in issues
            if "urgent" in " ".join(str(label) for label in ((issue.get("fields") or {}).get("labels") or [])).casefold()
        ]
        recommendations = []
        if stale:
            recommendations.append(Recommendation("Archive or revalidate stale backlog", f"{len(stale)} stale issue(s) need disposition.", "high"))
        if low_quality:
            recommendations.append(Recommendation("Improve low-quality tickets", "Short or missing summaries make work hard to prioritize.", "medium"))
        if unassigned:
            recommendations.append(Recommendation("Assign ownership", f"{len(unassigned)} open issue(s) are unassigned.", "medium"))
        return self._response(
            "backlog_review",
            inputs={"instance": selected_instance, "project": project, "team": team, "time_window": time_window, "limit": limit},
            summary=f"Backlog review found {health.get('issue_count', len(issues))} open issue(s) in scope.",
            metrics=[
                Metric("open_issue_count", health.get("issue_count", len(issues)), "issues"),
                Metric("stale_issue_count", len(stale), "issues"),
                Metric("blocked_issue_count", len(blocked), "issues"),
                Metric("unassigned_issue_count", len(unassigned), "issues"),
            ],
            findings=[Finding("Backlog quality", "Issues are grouped into disposition buckets from search and health signals.", "info", "backlog")],
            risks=[
                Risk("Blocked backlog items", f"{len(blocked)} backlog issue(s) are blocked.", "high", blocked) for _ in [0] if blocked
            ],
            recommendations=recommendations,
            source_coverage=coverage,
            sections={
                "archive_candidates": stale,
                "keep": [issue.get("key") for issue in issues if issue.get("key") not in set(stale + low_quality)],
                "needs_review": sorted(set(stale + unassigned + low_quality)),
                "duplicates": [],
                "low_quality_tickets": low_quality,
                "urgent_new_work": urgent,
                "domain_distribution": health.get("domain_counts") or {},
                "paginated_issues": page,
            },
            caveats=["Duplicate detection is conservative until linked-issue or similarity data is available."],
        )

    def portfolio_review(
        self,
        instance: str | None = None,
        *,
        project: str | None = None,
        team: str | None = None,
        quarter: str | None = None,
        time_window: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        selected_instance = self._instance_names(instance)[0]
        coverage: list[SourceCoverage] = []
        quarters = [quarter] if quarter else []
        if not quarters:
            env = self._safe(coverage, "environment", lambda: self.backend.discover_environment(selected_instance, project), {})
            quarters = (env.get("target_quarter_values") or [])[:4]
        commitments = []
        for row_quarter in quarters:
            commitments.append(self._safe(
                coverage,
                f"quarter:{row_quarter}",
                lambda row_quarter=row_quarter: self.backend.report_quarter_progress(selected_instance, row_quarter, f"project = {_quote_jql(project)}" if project else "", limit),
                {"quarter": row_quarter, "count": 0, "status_counts": {}},
            ))
        if not commitments:
            jql = _bounded_jql(project, time_window or DEFAULT_WINDOW)
            health = self._safe(coverage, "engineering_health", lambda: self.backend.engineering_health(selected_instance, jql, 90, limit), {})
        else:
            health = {}
        total = sum(row.get("count", 0) for row in commitments)
        blocked_keys = []
        stale_keys = []
        for row in commitments:
            for issue in row.get("issues") or []:
                fields = issue.get("fields") or {}
                status = str(fields.get("status") or "")
                if "block" in status.casefold():
                    blocked_keys.append(issue.get("key"))
        recommendations = []
        if blocked_keys:
            recommendations.append(Recommendation("Unblock quarter commitments", "Blocked commitments should be reviewed before scope changes.", "high"))
        if not commitments:
            recommendations.append(Recommendation("Configure or discover quarter values", "No target-quarter values were available for portfolio grouping.", "medium"))
        return self._response(
            "portfolio_review",
            inputs={"instance": selected_instance, "project": project, "team": team, "quarter": quarter, "time_window": time_window, "limit": limit},
            summary=f"Portfolio review covered {len(commitments)} quarter bucket(s).",
            metrics=[
                Metric("quarter_bucket_count", len(commitments), "quarters"),
                Metric("commitment_count", total or health.get("issue_count", 0), "issues"),
                Metric("blocked_commitment_count", len(blocked_keys), "issues"),
            ],
            findings=[Finding("Quarter commitments", "Portfolio state is grouped by displayed quarter values where available.", "info", "portfolio")],
            risks=[Risk("Blocked commitments", f"{len(blocked_keys)} commitment(s) appear blocked.", "high", blocked_keys)] if blocked_keys else [],
            recommendations=recommendations,
            source_coverage=coverage,
            sections={
                "commitments_by_quarter": commitments,
                "status_distribution": {row.get("quarter"): row.get("status_counts") for row in commitments},
                "unassigned_work": health.get("unassigned_issue_keys") or [],
                "stale_commitments": stale_keys or health.get("stale_issue_keys") or [],
                "blocked_commitments": blocked_keys,
                "overcommit_undercommit_indicators": [],
            },
        )

    def engineering_review(
        self,
        instance: str | None = None,
        *,
        instances: list[str] | str | None = None,
        team: str | None = None,
        project: str | None = None,
        saved_view: str | None = None,
        time_window: str | None = DEFAULT_WINDOW,
        include_sections: list[str] | str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        names = self._instance_names(instance, instances)
        sections_requested = set(_as_list(include_sections) or ["sprint", "backlog", "portfolio", "security", "repositories", "saved_view"])
        coverage: list[SourceCoverage] = []
        sections: dict[str, Any] = {"instances": {}}
        findings: list[Finding] = []
        risks: list[Risk] = []
        recommendations: list[Recommendation] = []
        metrics: list[Metric] = []

        for selected_instance in names:
            instance_sections: dict[str, Any] = {}
            if "sprint" in sections_requested:
                sprint = self.sprint_analysis(selected_instance, team=team, project=project)
                instance_sections["sprint_health"] = sprint
                risks.extend(Risk(row["title"], row["description"], row.get("severity", "medium"), row.get("affected", [])) for row in sprint.get("risks", []))
                recommendations.extend(Recommendation(row["action"], row["rationale"], row.get("priority", "medium"), row.get("owner"), row.get("preview_id")) for row in sprint.get("recommendations", []))
            if "backlog" in sections_requested:
                instance_sections["backlog"] = self.backlog_review(selected_instance, project=project, team=team, time_window=time_window, limit=limit)
            if "portfolio" in sections_requested:
                instance_sections["portfolio"] = self.portfolio_review(selected_instance, project=project, team=team, time_window=time_window, limit=limit)
            if "security" in sections_requested:
                security = self.security_remediation_analysis(selected_instance, project=project, limit=limit)
                instance_sections["security"] = security
                recommendations.extend(Recommendation(row["action"], row["rationale"], row.get("priority", "medium")) for row in security.get("recommendations", []))
            if saved_view and "saved_view" in sections_requested:
                instance_sections["saved_view"] = self.saved_view_review(saved_view, instance=selected_instance, page_size=min(limit, 100))
            sections["instances"][selected_instance] = instance_sections

        if "repositories" in sections_requested:
            repo = self._safe(coverage, "repository_inventory", self.backend.repository_inventory, {})
            sections["repository_package_signals"] = repo
            metrics.append(Metric("repository_count", repo.get("count", len(repo.get("repositories", []))), "repositories"))
            metrics.append(Metric("package_count", repo.get("package_count", 0), "packages"))

        if team:
            findings.append(Finding("Team scope", "Team input is treated as an orchestration hint unless a saved view or project narrows Jira scope.", "info", "scope"))
        return self._response(
            "engineering_review",
            inputs={
                "instance": instance,
                "instances": instances,
                "team": team,
                "project": project,
                "saved_view": saved_view,
                "time_window": time_window,
                "include_sections": include_sections,
                "limit": limit,
            },
            summary=f"Engineering review prepared for {len(names)} instance(s).",
            metrics=metrics,
            findings=findings,
            risks=risks,
            recommendations=recommendations[:12],
            source_coverage=coverage,
            sections=sections,
            caveats=["Partial source failures are reported per nested workflow."],
        )
