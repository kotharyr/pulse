from __future__ import annotations

import json
import logging
<<<<<<< HEAD
from contextlib import asynccontextmanager
from typing import Any

import anyio
from mcp.server.auth.settings import AuthSettings
=======
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

<<<<<<< HEAD
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
=======
from engineering_ops.adapters.jira import JiraClient
from engineering_ops.config import configuration_report, settings, validate_startup_configuration
from engineering_ops.services.fields import resolve_field, resolve_value_for_issue
from engineering_ops.services.health import engineering_health as health_summary
from engineering_ops.services.repos import discover_repositories, extract_security_signals, scan_manifests
from engineering_ops.services.sprints import is_done, overcommit_analysis, story_points, summarize_capacity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("engineering_ops")
mcp = FastMCP("engineering-operations-assistant")


def client(instance: str) -> JiraClient:
    configs = settings.jira_instances()
    if instance not in configs:
        raise ValueError(f"Unknown instance {instance!r}; available={list(configs)}")
    return JiraClient(instance, configs[instance])


def _story_points_field(jira: JiraClient) -> tuple[str, str | None]:
    name = jira.cfg.story_points_field_name
    try:
        return name, resolve_field(jira, name)["id"]
    except Exception:
        return name, None


def _text_from_adf(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(_text_from_adf(x) for x in node)
    if isinstance(node, dict):
        parts = []
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        if node.get("content"):
            parts.append(_text_from_adf(node["content"]))
        return " ".join(p for p in parts if p)
    return ""


def _description_value(jira: JiraClient, text: str) -> Any:
    if jira.cfg.kind != "cloud":
        return text
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]} if line else {"type": "paragraph", "content": []}
            for line in text.splitlines()
        ],
    }


def _derive_capacity(jira: JiraClient, board_id: int | None, points_field_name: str, points_field_id: str | None) -> dict[str, Any]:
    cfg = jira.cfg
    if cfg.sprint_capacity_points:
        return {"story_points": cfg.sprint_capacity_points, "issue_count": cfg.sprint_capacity_issue_count, "source": "configured"}
    if board_id:
        try:
            closed = jira.board_sprints(board_id, state="closed", limit=5)
            samples = []
            for sprint in closed[-3:]:
                issues = jira.sprint_issues(int(sprint["id"]))
                completed = sum(story_points(i, points_field_name, points_field_id) for i in issues if is_done(i))
                if completed > 0:
                    samples.append(completed)
            if samples:
                return {"story_points": round(mean(samples), 2), "issue_count": None, "source": f"average completed points from {len(samples)} recent closed sprints"}
        except Exception as exc:
            logger.warning("Could not derive sprint capacity for %s: %s", jira.name, exc)
    return {"story_points": None, "issue_count": cfg.sprint_capacity_issue_count, "source": "configured_issue_count" if cfg.sprint_capacity_issue_count else "unknown"}


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    report = configuration_report()
    return JSONResponse({
        "status": "ok" if report["ok"] else "configuration_error",
        "mode": report["mode"],
        "instances": [{"name": r["name"], "type": r["type"], "credentials_loaded": r["credentials_loaded"]} for r in report["instances"]],
        "local_repo_root": report["local_repo_root"],
        "errors": report["errors"],
        "warnings": report["warnings"],
    }, status_code=200 if report["ok"] else 503)


@mcp.tool()
def system_readiness(check_connections: bool = False) -> dict[str, Any]:
    """Check local configuration and, optionally, authenticate to every configured Jira instance."""
    report = configuration_report()
    connection_results = []
    if check_connections and report["ok"]:
        for row in report["instances"]:
            try:
                me = client(row["name"]).myself()
                connection_results.append({"instance": row["name"], "ok": True, "display_name": me.get("displayName") or me.get("name")})
            except Exception as exc:
                connection_results.append({"instance": row["name"], "ok": False, "error": str(exc)})
        report["connections_ok"] = all(r["ok"] for r in connection_results)
    report["connections"] = connection_results
    return report


@mcp.tool()
def list_jira_instances() -> dict:
    """List the named Jira environments available to the assistant."""
    return {"instances": [{"name": n, "kind": c.kind, "base_url": c.base_url, "default_project": c.default_project} for n, c in settings.jira_instances().items()]}


@mcp.tool()
def test_jira_connection(instance: str) -> dict:
    """Authenticate to a named Jira instance and return the current Jira user."""
    me = client(instance).myself()
    return {"ok": True, "instance": instance, "display_name": me.get("displayName") or me.get("name"), "account": me.get("emailAddress") or me.get("key")}


@mcp.tool()
def discover_jira_environment(instance: str, project_key: str | None = None) -> dict:
    """Discover projects, fields, boards, and active/future sprints so natural-language requests do not require IDs."""
    jira = client(instance)
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
        "fields": [{"id": f.get("id"), "name": f.get("name"), "custom": f.get("custom", False)} for f in fields],
        "boards": boards,
        "sprints": sprint_rows,
    }


@mcp.tool()
def search_issues(instance: str, jql: str, fields: list[str] | None = None, limit: int = 100) -> dict:
    """Search Jira using JQL. This tool is read-only and safe for exploratory natural-language questions."""
    rows = client(instance).search(jql, fields or ["summary", "status", "priority", "assignee", "created", "updated", "labels"], min(limit, settings.max_search_results))
    return {"count": len(rows), "issues": rows}


@mcp.tool()
def preview_field_updates(instance: str, jql: str, updates: dict[str, Any], limit: int = 500) -> dict:
    """Preview bulk updates using human-readable Jira field names and displayed option values. Never writes."""
    jira = client(instance)
    issues = jira.search(jql, ["summary"], limit)
    resolved_fields = {name: resolve_field(jira, name) for name in updates}
    previews, errors = [], []
    for issue in issues:
        fields = {}
        for name, value in updates.items():
            try:
                fields[resolved_fields[name]["id"]] = resolve_value_for_issue(jira, issue["key"], resolved_fields[name]["id"], value)
            except Exception as exc:
                errors.append({"issue_key": issue["key"], "field": name, "error": str(exc)})
        previews.append({"issue_key": issue["key"], "summary": issue.get("fields", {}).get("summary"), "fields": fields})
    return {"mode": settings.mode, "matched": len(issues), "field_resolution": {k: v["id"] for k, v in resolved_fields.items()}, "issues": previews, "errors": errors, "can_apply": bool(issues) and not errors and settings.mode != "recommend_only"}


@mcp.tool()
def apply_field_updates(instance: str, jql: str, updates: dict[str, Any], limit: int = 500) -> dict:
    """Apply a previously understood reversible field update. Blocked in recommend_only mode."""
    preview = preview_field_updates(instance, jql, updates, limit)
    if settings.mode == "recommend_only":
        return {**preview, "applied": False, "reason": "MODE=recommend_only"}
    if preview["errors"]:
        return {**preview, "applied": False, "reason": "Resolution errors must be fixed"}
    jira = client(instance)
    results = []
    for item in preview["issues"]:
        try:
            jira.update_issue(item["issue_key"], item["fields"])
            results.append({"issue_key": item["issue_key"], "ok": True})
        except Exception as exc:
            results.append({"issue_key": item["issue_key"], "ok": False, "error": str(exc)})
    return {"applied": all(r["ok"] for r in results), "results": results}


@mcp.tool()
def assign_to_quarter(instance: str, jql: str, quarter: str, dry_run: bool = True, limit: int = 500) -> dict:
    """Assign matching work to a displayed Target Quarter value without requiring field or option IDs."""
    field = settings.jira_instances()[instance].quarter_field_name
    return preview_field_updates(instance, jql, {field: quarter}, limit) if dry_run else apply_field_updates(instance, jql, {field: quarter}, limit)


@mcp.tool()
def report_quarter_progress(instance: str, quarter: str, jql_extra: str = "", limit: int = 5000) -> dict:
    """Summarize delivery progress for a target quarter."""
    cfg = settings.jira_instances()[instance]
    jira = client(instance)
    field = resolve_field(jira, cfg.quarter_field_name)
    points_name, points_id = _story_points_field(jira)
    jql = f'"{cfg.quarter_field_name}" = "{quarter}"' + (f" AND ({jql_extra})" if jql_extra else "")
    search_fields = ["summary", "status", "assignee", "updated", field["id"]]
    if points_id:
        search_fields.append(points_id)
    issues = jira.search(jql, search_fields, limit)
    counts = Counter((i.get("fields", {}).get("status") or {}).get("name", "Unknown") for i in issues)
    done_issues = [i for i in issues if is_done(i)]
    total_points = sum(story_points(i, points_name, points_id) for i in issues)
    done_points = sum(story_points(i, points_name, points_id) for i in done_issues)
    return {
        "quarter": quarter, "count": len(issues), "status_counts": dict(counts),
        "completed_count": len(done_issues), "completion_percent": round(len(done_issues)*100/len(issues), 1) if issues else 0,
        "story_points": round(total_points, 2), "completed_story_points": round(done_points, 2),
        "story_point_completion_percent": round(done_points*100/total_points, 1) if total_points else None,
        "issues": issues,
    }


@mcp.tool()
def report_sprint_progress(instance: str, sprint_id: int) -> dict:
    """Report sprint status, incomplete work, and story-point progress."""
    jira = client(instance)
    sprint = jira.sprint(sprint_id)
    issues = jira.sprint_issues(sprint_id)
    points_name, points_id = _story_points_field(jira)
    counts = Counter((i.get("fields", {}).get("status") or {}).get("name", "Unknown") for i in issues)
    capacity = summarize_capacity(issues, points_name, points_id)
    return {"sprint": sprint, "count": len(issues), "status_counts": dict(counts), **capacity, "incomplete_issue_keys": [i["key"] for i in issues if not is_done(i)], "issues": issues}


@mcp.tool()
def analyze_next_sprint_capacity(instance: str, sprint_id: int, additional_issue_keys: list[str] | None = None, additional_story_points: float = 0) -> dict:
    """Check whether a sprint is or will become overcommitted, using configured or recent historical capacity."""
    jira = client(instance)
    sprint = jira.sprint(sprint_id)
    issues = jira.sprint_issues(sprint_id)
    points_name, points_id = _story_points_field(jira)
    existing = summarize_capacity(issues, points_name, points_id)
    extra_issues = []
    if additional_issue_keys:
        for key in additional_issue_keys:
            extra_issues.append(jira.get_issue(key, ["summary", "status", points_id or points_name]))
    added_points = additional_story_points + sum(story_points(i, points_name, points_id) for i in extra_issues)
    board_id = sprint.get("originBoardId") or jira.cfg.default_board_id
    capacity = _derive_capacity(jira, int(board_id) if board_id else None, points_name, points_id)
    analysis = overcommit_analysis(existing["story_points"], added_points, capacity["story_points"], jira.cfg.sprint_capacity_buffer_percent, existing["issue_count"], len(extra_issues), capacity["issue_count"])
    return {"sprint": sprint, "capacity_source": capacity["source"], **analysis}


@mcp.tool()
def preview_close_sprint(instance: str, sprint_id: int, next_sprint_id: int, move_issue_keys: list[str] | None = None, split_plans: list[dict[str, Any]] | None = None, rollover_all_incomplete: bool = False) -> dict:
    """Preview sprint closure, rollover, issue splitting, and next-sprint overcommit. Never writes. split_plans may include source_issue_key, new_summary, new_description, story_points, new_issue_type, parent_key, and source_transition_status."""
    jira = client(instance)
    current_sprint = jira.sprint(sprint_id)
    next_sprint = jira.sprint(next_sprint_id)
    current_issues = jira.sprint_issues(sprint_id)
    current_map = {i["key"]: i for i in current_issues}
    incomplete = [i for i in current_issues if not is_done(i)]
    move_keys = list(dict.fromkeys(move_issue_keys or ([] if not rollover_all_incomplete else [i["key"] for i in incomplete])))
    plans = split_plans or []
    split_sources = {p.get("source_issue_key") for p in plans if p.get("source_issue_key")}
    if rollover_all_incomplete:
        move_keys = [k for k in move_keys if k not in split_sources]
    unknown = sorted((set(move_keys) | split_sources) - set(current_map))
    points_name, points_id = _story_points_field(jira)
    moved_points = sum(story_points(current_map[k], points_name, points_id) for k in move_keys if k in current_map)
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
            errors.append({"source_issue_key": key, "error": "source_transition_status is required so the original work is explicitly resolved before sprint closure"})
    next_issues = jira.sprint_issues(next_sprint_id)
    next_existing = summarize_capacity(next_issues, points_name, points_id)
    board_id = next_sprint.get("originBoardId") or current_sprint.get("originBoardId") or jira.cfg.default_board_id
    capacity = _derive_capacity(jira, int(board_id) if board_id else None, points_name, points_id)
    overcommit = overcommit_analysis(next_existing["story_points"], moved_points + split_points, capacity["story_points"], jira.cfg.sprint_capacity_buffer_percent, next_existing["issue_count"], len(move_keys) + len(plans), capacity["issue_count"])
    unhandled = sorted(set(i["key"] for i in incomplete) - set(move_keys) - split_sources)
    if unhandled:
        errors.append({"error": "Incomplete issues would remain unhandled when the sprint closes", "issue_keys": unhandled})
    return {
        "mode": settings.mode,
        "current_sprint": current_sprint,
        "next_sprint": next_sprint,
        "current_incomplete_issue_keys": [i["key"] for i in incomplete],
        "move_issue_keys": move_keys,
        "split_plans": plan_previews,
        "unknown_issue_keys": unknown,
        "unhandled_incomplete_issue_keys": unhandled,
        "next_sprint_capacity": {"capacity_source": capacity["source"], **overcommit},
        "warnings": (["NEXT SPRINT IS PROJECTED TO BE OVERCOMMITTED"] if overcommit["overcommitted"] else []),
        "errors": errors,
        "can_apply": settings.mode == "approved_destructive" and not unknown and not errors,
    }


def _transition_to_status(jira: JiraClient, issue_key: str, status_name: str) -> dict[str, Any]:
    data = jira.request("GET", f"/rest/api/{jira.platform_api_version}/issue/{issue_key}/transitions")
    matches = [t for t in data.get("transitions", []) if ((t.get("to") or {}).get("name") or "").casefold() == status_name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Could not resolve transition to {status_name!r} for {issue_key}; matches={[((t.get('to') or {}).get('name'), t.get('id')) for t in matches]}")
    jira.request("POST", f"/rest/api/{jira.platform_api_version}/issue/{issue_key}/transitions", json={"transition": {"id": matches[0]["id"]}})
    return {"issue_key": issue_key, "to_status": status_name, "transition_id": matches[0]["id"]}


@mcp.tool()
def apply_close_sprint(instance: str, sprint_id: int, next_sprint_id: int, move_issue_keys: list[str] | None = None, split_plans: list[dict[str, Any]] | None = None, rollover_all_incomplete: bool = False) -> dict:
    """Execute an explicitly approved sprint-close plan. Requires MODE=approved_destructive. Creates follow-on issues, transitions split sources, moves rollover work, then closes the sprint."""
    preview = preview_close_sprint(instance, sprint_id, next_sprint_id, move_issue_keys, split_plans, rollover_all_incomplete)
    if settings.mode != "approved_destructive":
        return {**preview, "applied": False, "reason": "MODE must be approved_destructive"}
    if not preview["can_apply"]:
        return {**preview, "applied": False, "reason": "Preview contains blocking errors"}
    jira = client(instance)
    points_name, points_id = _story_points_field(jira)
    created, transitions = [], []
    new_issue_keys = []
    for plan in split_plans or []:
        source = jira.get_issue(plan["source_issue_key"], ["summary", "description", "issuetype", "project", "parent", points_id or points_name])
        sf = source.get("fields") or {}
        project_key = (sf.get("project") or {}).get("key")
        issue_type = plan.get("new_issue_type") or (sf.get("issuetype") or {}).get("name")
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": plan["new_summary"],
            "issuetype": {"name": issue_type},
            "description": _description_value(jira, plan.get("new_description") or f"Follow-on work split from {plan['source_issue_key']} during sprint closure."),
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
        transitions.append(_transition_to_status(jira, plan["source_issue_key"], plan["source_transition_status"]))
    all_move = list(dict.fromkeys((preview["move_issue_keys"] or []) + new_issue_keys))
    moved_batches = jira.move_issues_to_sprint(next_sprint_id, all_move) if all_move else []
    closed = jira.update_sprint(sprint_id, {"state": "closed"})
    return {
        "applied": True,
        "created_issues": created,
        "source_transitions": transitions,
        "moved_to_next_sprint": all_move,
        "move_batches": moved_batches,
        "closed_sprint": closed,
        "next_sprint_capacity": preview["next_sprint_capacity"],
        "warnings": preview["warnings"],
    }


@mcp.tool()
def list_local_repositories() -> dict:
    """List locally checked-out repositories under LOCAL_REPO_ROOT. Read-only."""
    root = settings.local_repo_path
    if not root:
        return {"configured": False, "repositories": [], "error": "LOCAL_REPO_ROOT is not configured"}
    return {"configured": True, "root": str(root), "repositories": discover_repositories(root)}


@mcp.tool()
def scan_repository_packages() -> dict:
    """Scan local dependency and container manifests across all checked-out repositories. Read-only."""
    root = settings.local_repo_path
    if not root:
        return {"configured": False, "packages": [], "error": "LOCAL_REPO_ROOT is not configured"}
    rows = scan_manifests(root)
    return {"configured": True, "root": str(root), "count": len(rows), "packages": rows}


@mcp.tool()
def analyze_security_package_updates(instance: str, project_key: str | None = None, limit: int = 2000) -> dict:
    """Normalize Operational Security Issue tickets into package remediation candidates and compare them with versions found in local repositories. Read-only."""
    jira = client(instance)
    project = project_key or jira.cfg.default_project
    marker = settings.security_issue_summary_marker.replace('"', '\\"')
    jql = f'project = {project} AND summary ~ "\\"{marker}\\"" ORDER BY updated DESC' if project else f'summary ~ "\\"{marker}\\"" ORDER BY updated DESC'
    issues = jira.search(jql, ["summary", "description", "status", "updated", "labels", "components"], min(limit, settings.max_search_results))
    ticket_rows = []
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for issue in issues:
        f = issue.get("fields") or {}
        text = (f.get("summary") or "") + "\n" + _text_from_adf(f.get("description"))
        signals = extract_security_signals(text)
        ticket_rows.append({"issue_key": issue["key"], "summary": f.get("summary"), **signals})
        for fix in signals["fixed_versions"]:
            pkg = fix.get("package")
            ver = fix.get("required_version")
            if pkg and ver:
                key = (pkg, ver)
                row = aggregate.setdefault(key, {"package": pkg, "required_version": ver, "issue_keys": [], "cves": set()})
                row["issue_keys"].append(issue["key"])
                row["cves"].update(signals["cves"])
    repo_rows = scan_manifests(settings.local_repo_path) if settings.local_repo_path else []
    repo_by_package = defaultdict(list)
    for row in repo_rows:
        if row.get("package"):
            repo_by_package[str(row["package"]).casefold()].append(row)
    normalized = []
    for row in aggregate.values():
        normalized.append({
            "package": row["package"], "required_version": row["required_version"],
            "ticket_count": len(set(row["issue_keys"])), "issue_keys": sorted(set(row["issue_keys"])),
            "cves": sorted(row["cves"]), "repo_occurrences": repo_by_package.get(row["package"].casefold(), []),
        })
    normalized.sort(key=lambda r: (-r["ticket_count"], r["package"]))
    return {"matched_tickets": len(issues), "normalized_upgrade_actions": normalized, "raw_ticket_analysis": ticket_rows, "repo_scan_available": bool(settings.local_repo_path)}


@mcp.tool()
def engineering_health(instance: str, jql: str, stale_days: int = 90, limit: int = 5000) -> dict:
    """Summarize engineering operational health: stale, blocked, unassigned, status mix, and architectural-domain labels."""
    issues = client(instance).search(jql, ["summary", "status", "assignee", "updated", "created", "labels", "priority"], min(limit, settings.max_search_results))
    return {"instance": instance, "jql": jql, **health_summary(issues, stale_days)}


def _log_startup_report(report: dict[str, Any]) -> None:
    safe = {"project_root": report["project_root"], "loaded_env_files": report["loaded_env_files"], "mode": report["mode"], "mcp": report["mcp"], "jira_instances_file": report["jira_instances_file"], "instances": [{"name": r["name"], "type": r["type"], "credentials_loaded": r["credentials_loaded"]} for r in report["instances"]], "local_repo_root": report["local_repo_root"], "warnings": report["warnings"]}
    logger.info("Startup configuration:\n%s", json.dumps(safe, indent=2))


if __name__ == "__main__":
    startup_report = validate_startup_configuration()
    _log_startup_report(startup_report)
    mcp.settings.host = settings.mcp_host
    mcp.settings.port = settings.mcp_port
    mcp.run(transport="streamable-http")
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
