from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import anyio
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from engineering_ops.api import console_routes
from engineering_ops.auth import StaticBearerTokenVerifier
from engineering_ops.backend import backend
from engineering_ops.config import settings, validate_startup_configuration
from engineering_ops.issue_creation_models import IssueDraft
from engineering_ops.plugins import CapabilityPlugin, PluginRegistry
from engineering_ops.runtime import close_clients

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("engineering_ops")

system_readiness = backend.system_readiness
list_jira_instances = backend.list_jira_instances
test_jira_connection = backend.test_jira_connection
discover_jira_environment = backend.discover_jira_environment
discover_environment = backend.discover_environment
refresh_environment = backend.refresh_environment
get_environment_summary = backend.get_environment_summary
find_project_by_name = backend.find_project_by_name
find_board_by_name = backend.find_board_by_name
find_sprint_by_name = backend.find_sprint_by_name
resolve_field_name = backend.resolve_field_name
resolve_field_value = backend.resolve_field_value
search_issues = backend.search_issues
preview_field_updates = backend.preview_field_updates
report_quarter_progress = backend.report_quarter_progress
report_sprint_progress = backend.report_sprint_progress
analyze_next_sprint_capacity = backend.analyze_next_sprint_capacity
list_local_repositories = backend.list_local_repositories
scan_repository_packages = backend.scan_repository_packages
repository_inventory = backend.repository_inventory
list_saved_views = backend.list_saved_views
get_saved_view = backend.get_saved_view
search_saved_view = backend.search_saved_view
save_operational_view = backend.save_operational_view
delete_operational_view = backend.delete_operational_view
portfolio_hygiene_review_backend = backend.portfolio_hygiene_review
portfolio_hygiene_preview_fix_backend = backend.portfolio_hygiene_preview_fix
portfolio_hygiene_apply_backend = backend.portfolio_hygiene_apply


def get_issue_creation_context(
    instance: str, project: str | None = None, issue_type: str = "Story"
) -> dict:
    """Read available creation fields and the connected Jira reporter.

    Choose an instance explicitly; use list_jira_instances and
    find_project_by_name to resolve names.
    """
    return backend.get_issue_creation_context(instance, project, issue_type)


def preview_create_issue(
    instance: str,
    draft: IssueDraft,
    project: str | None = None,
    issue_type: str = "Story",
    additional_fields: dict[str, Any] | None = None,
) -> dict:
    """Draft a new Jira issue from Chat without writing.

    Use Summary, User Story, Description, Acceptance Criteria, Dependencies,
    Out of Scope and Business Value. Ask for missing facts; do not invent
    requirements. Show the complete stored preview including instance, project
    and reporter, and obtain user approval before apply_create_issue. Reporter
    is the selected connection's authenticated Jira account. Additional fields
    use human names/values from get_issue_creation_context.
    """
    return backend.preview_create_issue(
        instance, draft.model_dump(), project, issue_type, additional_fields
    )


def apply_create_issue(preview_id: str) -> dict:
    """Create exactly the issue in a reviewed preview after explicit user approval.

    Requires MODE=safe_apply; recommend_only blocks creation. Never blindly
    retry an uncertain result: use reconcile_execution.
    """
    return backend.apply_create_issue(preview_id)


def preview_sprint_placeholders(
    source_instance: str, instance: str, sprint_id: int, project: str,
    user_mappings: dict[str, str] | None = None, issue_type: str = "Story",
    additional_fields: dict[str, Any] | None = None,
) -> dict:
    """Preview SBG Jira Ops Work placeholders per Cloud sprint assignee in GPK2.

    Match users automatically by their common email address. Optional username
    overrides handle hidden emails or account exceptions. Unresolved users are
    reported for review. Source links in existing descriptions determine
    inclusion. Missing-point stories are excluded and listed for a later rerun.
    Never writes. Review the complete preview before applying.
    """
    return backend.preview_sprint_placeholders(
        source_instance, instance, sprint_id, project, user_mappings, issue_type,
        additional_fields,
    )


def apply_sprint_placeholders(preview_id: str) -> dict:
    """Apply a reviewed Cloud-to-GPK2 placeholder preview after approval.

    Requires safe_apply. Reconcile partial or uncertain outcomes before retrying.
    """
    return backend.apply_sprint_placeholders(preview_id)


def engineering_review(
    instance: str | None = None,
    instances: list[str] | None = None,
    team: str | None = None,
    project: str | None = None,
    saved_view: str | None = None,
    time_window: str | None = "-30d",
    include_sections: list[str] | None = None,
    limit: int = 100,
) -> dict:
    """Prepare a concise engineering operations review across Jira, sprint, portfolio, backlog, security, and repository signals. Use for prompts like "Prepare this week's engineering review." Read-only."""
    return backend.engineering_review(instance, instances, team, project, saved_view, time_window, include_sections, limit)


def sprint_analysis(
    instance: str | None = None,
    team: str | None = None,
    project: str | None = None,
    board: str | None = None,
    sprint_name: str | None = None,
    sprint_id: int | None = None,
    next_sprint_name: str | None = None,
    next_sprint_id: int | None = None,
) -> dict:
    """Analyze the current or named sprint using friendly names where possible. Returns completion, blocked work, rollover candidates, capacity, overcommit risk, and recommendations. Read-only."""
    return backend.sprint_analysis(instance, team, project, board, sprint_name, sprint_id, next_sprint_name, next_sprint_id)


def sprint_close_preview(
    instance: str | None = None,
    project: str | None = None,
    sprint_name: str | None = None,
    sprint_id: int | None = None,
    next_sprint_name: str | None = None,
    next_sprint_id: int | None = None,
    move_issue_keys: list[str] | None = None,
    split_plans: list[dict[str, Any]] | None = None,
    rollover_all_incomplete: bool = True,
) -> dict:
    """Create a full stored sprint close preview before any changes. Shows rollover, split work, next-sprint load, overcommit warnings, and exact planned actions. Never writes."""
    return backend.sprint_close_preview_workflow(
        instance,
        project,
        sprint_name,
        sprint_id,
        next_sprint_name,
        next_sprint_id,
        move_issue_keys,
        split_plans,
        rollover_all_incomplete,
    )


def sprint_close_apply(preview_id: str) -> dict:
    """Apply a previously reviewed sprint close preview by preview_id. Requires MODE=approved_destructive and fails if the stored preview is stale or missing."""
    return backend.sprint_close_apply_workflow(preview_id)


def reconcile_execution(preview_id: str) -> dict:
    """Read-only reconciliation of a partial execution. Review its observations before resuming."""
    return backend.reconcile_execution(preview_id)


def resume_execution(preview_id: str, recovery_id: str) -> dict:
    """Resume a reviewed partial execution. Requires the original actor, a fresh recovery_id and the correct write mode."""
    return backend.resume_execution(preview_id, recovery_id)



def portfolio_review(
    instance: str | None = None,
    project: str | None = None,
    team: str | None = None,
    quarter: str | None = None,
    time_window: str | None = None,
    limit: int = 500,
) -> dict:
    """Review quarter and portfolio state: commitments, status distribution, stale or blocked work, and rebalance recommendations. Read-only."""
    return backend.portfolio_review(instance, project, team, quarter, time_window, limit)


def backlog_review(
    instance: str | None = None,
    project: str | None = None,
    team: str | None = None,
    time_window: str | None = "-90d",
    limit: int = 100,
) -> dict:
    """Analyze backlog quality and disposition: archive candidates, needs-review work, low-quality tickets, urgent work, domain distribution, and recommendations. Read-only."""
    return backend.backlog_review(instance, project, team, time_window, limit)


def security_remediation_analysis(
    instance: str | None = None,
    project: str | None = None,
    limit: int = 2000,
) -> dict:
    """Rank Operational Security Issue remediation opportunities against local repository/package state. Returns CVEs, required versions, affected repos, already-fixed repos, and tickets potentially cleared. Read-only."""
    return backend.security_remediation_analysis(instance, project, limit)


def saved_view_review(
    view_name: str,
    instance: str | None = None,
    page: int = 1,
    page_size: int = 25,
    limit: int | None = None,
) -> dict:
    """Run and summarize a named saved operational view, including paginated issues, risks, and recommended actions. Read-only."""
    return backend.saved_view_review(view_name, instance, page, page_size, limit)


def portfolio_hygiene_review(
    instance: str = "onprem",
    quarter: str | None = None,
    project: str | None = None,
    team: str | None = None,
    pt: str | None = None,
    saved_view: str | None = None,
    limit: int = 500,
) -> dict:
    """Review on-prem portfolio hierarchy and quarter hygiene. Returns ancestry coverage, date violations, label violations, safe fixes, manual reviews, confidence, and data-quality notes. Read-only."""
    return backend.portfolio_hygiene_review(instance, quarter, project, team, pt, saved_view, limit)


def portfolio_hygiene_preview_fix(
    instance: str = "onprem",
    quarter: str | None = None,
    project: str | None = None,
    team: str | None = None,
    pt: str | None = None,
    saved_view: str | None = None,
    limit: int = 500,
    findings: list[dict[str, Any]] | None = None,
    proposed_changes: list[dict[str, Any]] | None = None,
    categories: list[str] | None = None,
) -> dict:
    """Create a stored Portfolio Hygiene fix preview. Includes exact issue-level date and label changes, current values, proposed values, and manual-review exclusions. Never writes."""
    return backend.portfolio_hygiene_preview_fix(instance, quarter, project, team, pt, saved_view, limit, findings, proposed_changes, categories)


def portfolio_hygiene_apply(preview_id: str, allow_parent_changes: bool = False) -> dict:
    """Apply a stored Portfolio Hygiene preview. Requires MODE=safe_apply, revalidates source state, and applies only safe date/label fixes by default."""
    return backend.portfolio_hygiene_apply(preview_id, allow_parent_changes)


def search_issues(instance: str, jql: str, fields: list[str] | None = None, limit: int = 100) -> dict:
    """Low-level/advanced diagnostic: run raw JQL search against Jira. Prefer engineering_review, backlog_review, saved_view_review, or sprint_analysis for natural-language operations."""
    return backend.search_issues(instance, jql, fields, limit)


def preview_field_updates(instance: str, jql: str, updates: dict[str, Any], limit: int = 500) -> dict:
    """Low-level/advanced diagnostic: preview direct Jira field updates by displayed field names. Prefer task workflows unless a precise bulk update is needed."""
    return backend.preview_field_updates(instance, jql, updates, limit)


def apply_field_updates(instance: str, jql: str, updates: dict[str, Any], limit: int = 500, preview_id: str | None = None) -> dict:
    """Low-level/advanced apply: apply a previously understood reversible field update. Blocked in recommend_only mode."""
    if not preview_id:
        return {"applied": False, "reason": "preview_id is required; run preview_field_updates and review it first"}
    return backend.apply_field_updates(instance, jql, updates, limit, preview_id=preview_id)


def assign_to_quarter(instance: str, jql: str, quarter: str, dry_run: bool = True, limit: int = 500, preview_id: str | None = None) -> dict:
    """Low-level/advanced apply: assign matching work to a displayed Target Quarter value without requiring field or option IDs."""
    if dry_run:
        return backend.assign_to_quarter(instance, jql, quarter, dry_run=True, limit=limit)
    if not preview_id:
        return {"applied": False, "reason": "preview_id is required; run assign_to_quarter with dry_run=True and review it first"}
    return backend.assign_to_quarter(instance, jql, quarter, dry_run=False, limit=limit, preview_id=preview_id)


def report_quarter_progress(instance: str, quarter: str, jql_extra: str = "", limit: int = 5000) -> dict:
    """Low-level/advanced diagnostic: report one explicit Target Quarter. Prefer portfolio_review for natural-language portfolio questions."""
    return backend.report_quarter_progress(instance, quarter, jql_extra, limit)


def report_sprint_progress(instance: str, sprint_id: int) -> dict:
    """Low-level/advanced diagnostic: report one explicit sprint id. Prefer sprint_analysis for current or named sprint questions."""
    return backend.report_sprint_progress(instance, sprint_id)


def analyze_next_sprint_capacity(
    instance: str,
    sprint_id: int,
    additional_issue_keys: list[str] | None = None,
    additional_story_points: float = 0,
) -> dict:
    """Low-level/advanced diagnostic: calculate next-sprint capacity for explicit inputs. Prefer sprint_analysis or sprint_close_preview."""
    return backend.analyze_next_sprint_capacity(instance, sprint_id, additional_issue_keys, additional_story_points)


def preview_close_sprint(
    instance: str,
    sprint_id: int,
    next_sprint_id: int,
    move_issue_keys: list[str] | None = None,
    split_plans: list[dict[str, Any]] | None = None,
    rollover_all_incomplete: bool = False,
) -> dict:
    """Low-level/advanced diagnostic: preview sprint closure with explicit sprint ids. Prefer sprint_close_preview for natural-language sprint close planning."""
    return backend.preview_close_sprint(instance, sprint_id, next_sprint_id, move_issue_keys, split_plans, rollover_all_incomplete)


def apply_close_sprint(
    instance: str,
    sprint_id: int,
    next_sprint_id: int,
    move_issue_keys: list[str] | None = None,
    split_plans: list[dict[str, Any]] | None = None,
    rollover_all_incomplete: bool = False,
    preview_id: str | None = None,
) -> dict:
    """Low-level/advanced apply: execute an explicitly approved sprint-close plan with explicit sprint ids. Prefer sprint_close_apply with a stored preview id."""
    if not preview_id:
        return {"applied": False, "reason": "preview_id is required; run preview_close_sprint and review it first"}
    return backend.apply_close_sprint(
        instance,
        sprint_id,
        next_sprint_id,
        move_issue_keys,
        split_plans,
        rollover_all_incomplete,
        preview_id=preview_id,
    )


def analyze_security_package_updates(instance: str, project_key: str | None = None, limit: int = 2000) -> dict:
    """Low-level/advanced diagnostic: normalize Operational Security Issue tickets. Prefer security_remediation_analysis for ranked remediation review."""
    return backend.analyze_security_package_updates(instance, project_key, limit)


def engineering_health(instance: str, jql: str, stale_days: int = 90, limit: int = 5000) -> dict:
    """Low-level/advanced diagnostic: summarize a raw JQL scope. Prefer engineering_review or backlog_review for natural-language operations."""
    return backend.engineering_health(instance, jql, stale_days, limit)


async def health(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.platform_health)
    return JSONResponse(result)


async def ready(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.platform_readiness)
    return JSONResponse(result, status_code=200 if result["ready"] else 503)


async def diagnostics(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.platform_diagnostics)
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)


async def liveness(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "mode": settings.mode})


def _log_startup_report(report: dict[str, Any]) -> None:
    safe = {
        "project_root": report["project_root"],
        "loaded_env_files": report["loaded_env_files"],
        "mode": report["mode"],
        "mcp": report["mcp"],
        "jira_instances_file": report["jira_instances_file"],
        "instances": [
            {"name": row["name"], "type": row["type"], "credentials_loaded": row["credentials_loaded"]}
            for row in report["instances"]
        ],
        "local_repo_root": report["local_repo_root"],
        "warnings": report["warnings"],
    }
    logger.info("Startup configuration:\n%s", json.dumps(safe, indent=2))


def build_plugin_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.add(CapabilityPlugin(
        name="system",
        tools=(system_readiness,),
        routes=(
            ("/health", ("GET",), health),
            ("/ready", ("GET",), ready),
            ("/diagnostics", ("GET",), diagnostics),
            ("/health/live", ("GET",), liveness),
        ),
    ))
    registry.add(CapabilityPlugin(
        name="jira",
        tools=(
            get_issue_creation_context,
            preview_create_issue,
            apply_create_issue,
            preview_sprint_placeholders,
            apply_sprint_placeholders,
            engineering_review,
            sprint_analysis,
            sprint_close_preview,
            sprint_close_apply,
            reconcile_execution,
            resume_execution,
            portfolio_review,
            portfolio_hygiene_review,
            portfolio_hygiene_preview_fix,
            portfolio_hygiene_apply,
            backlog_review,
            security_remediation_analysis,
            saved_view_review,
            list_jira_instances,
            test_jira_connection,
            discover_jira_environment,
            discover_environment,
            refresh_environment,
            get_environment_summary,
            find_project_by_name,
            find_board_by_name,
            find_sprint_by_name,
            resolve_field_name,
            resolve_field_value,
            search_issues,
            preview_field_updates,
            apply_field_updates,
            assign_to_quarter,
            report_quarter_progress,
            report_sprint_progress,
            analyze_next_sprint_capacity,
            preview_close_sprint,
            apply_close_sprint,
            analyze_security_package_updates,
            engineering_health,
        ),
    ))
    registry.add(CapabilityPlugin(
        name="repositories",
        tools=(
            list_local_repositories,
            scan_repository_packages,
            repository_inventory,
            list_saved_views,
            get_saved_view,
            search_saved_view,
            save_operational_view,
            delete_operational_view,
        ),
    ))
    registry.add(CapabilityPlugin(
        name="console",
        routes=console_routes(),
    ))
    return registry


def create_mcp_server(*, validate_configuration: bool = True) -> FastMCP:
    """Compose the MCP application from registered capability plugins."""
    if validate_configuration:
        _log_startup_report(validate_startup_configuration())

    auth_settings = None
    token_verifier = None
    if settings.mcp_bearer_token:
        public_url = (settings.mcp_public_url or f"http://127.0.0.1:{settings.mcp_port}").rstrip("/")
        auth_settings = AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
            required_scopes=["mcp:tools"],
        )
        token_verifier = StaticBearerTokenVerifier(settings.mcp_bearer_token)

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        try:
            yield {}
        finally:
            close_clients()

    server = FastMCP(
        "engineering-operations-assistant",
        host=settings.mcp_host,
        port=settings.mcp_port,
        auth=auth_settings,
        token_verifier=token_verifier,
        lifespan=lifespan,
    )
    build_plugin_registry().install(server)
    return server


mcp = create_mcp_server()


def run() -> None:
    try:
        mcp.run(transport="streamable-http")
    finally:
        close_clients()


if __name__ == "__main__":
    run()
