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

from engineering_ops.auth import StaticBearerTokenVerifier
from engineering_ops.backend import backend
from engineering_ops.config import settings, validate_startup_configuration
from engineering_ops.plugins import CapabilityPlugin, PluginRegistry
from engineering_ops.runtime import close_clients

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("engineering_ops")

system_readiness = backend.system_readiness
list_jira_instances = backend.list_jira_instances
test_jira_connection = backend.test_jira_connection
discover_jira_environment = backend.discover_jira_environment
search_issues = backend.search_issues
preview_field_updates = backend.preview_field_updates
report_quarter_progress = backend.report_quarter_progress
report_sprint_progress = backend.report_sprint_progress
analyze_next_sprint_capacity = backend.analyze_next_sprint_capacity
list_local_repositories = backend.list_local_repositories
scan_repository_packages = backend.scan_repository_packages


def apply_field_updates(instance: str, jql: str, updates: dict[str, Any], limit: int = 500) -> dict:
    """Apply a previously understood reversible field update. Blocked in recommend_only mode."""
    preview = backend.preview_field_updates(instance, jql, updates, limit)
    return backend.apply_field_updates(instance, jql, updates, limit, preview_id=preview["preview_id"])


def assign_to_quarter(instance: str, jql: str, quarter: str, dry_run: bool = True, limit: int = 500) -> dict:
    """Assign matching work to a displayed Target Quarter value without requiring field or option IDs."""
    if dry_run:
        return backend.assign_to_quarter(instance, jql, quarter, dry_run=True, limit=limit)
    preview = backend.assign_to_quarter(instance, jql, quarter, dry_run=True, limit=limit)
    return backend.assign_to_quarter(instance, jql, quarter, dry_run=False, limit=limit, preview_id=preview["preview_id"])


def preview_close_sprint(
    instance: str,
    sprint_id: int,
    next_sprint_id: int,
    move_issue_keys: list[str] | None = None,
    split_plans: list[dict[str, Any]] | None = None,
    rollover_all_incomplete: bool = False,
) -> dict:
    """Preview sprint closure, rollover, issue splitting, and next-sprint overcommit. Never writes. split_plans may include source_issue_key, new_summary, new_description, story_points, new_issue_type, parent_key, and source_transition_status."""
    return backend.preview_close_sprint(instance, sprint_id, next_sprint_id, move_issue_keys, split_plans, rollover_all_incomplete)


def apply_close_sprint(
    instance: str,
    sprint_id: int,
    next_sprint_id: int,
    move_issue_keys: list[str] | None = None,
    split_plans: list[dict[str, Any]] | None = None,
    rollover_all_incomplete: bool = False,
) -> dict:
    """Execute an explicitly approved sprint-close plan. Requires MODE=approved_destructive. Creates follow-on issues, transitions split sources, moves rollover work, then closes the sprint."""
    preview = backend.preview_close_sprint(instance, sprint_id, next_sprint_id, move_issue_keys, split_plans, rollover_all_incomplete)
    return backend.apply_close_sprint(
        instance,
        sprint_id,
        next_sprint_id,
        move_issue_keys,
        split_plans,
        rollover_all_incomplete,
        preview_id=preview["preview_id"],
    )


def analyze_security_package_updates(instance: str, project_key: str | None = None, limit: int = 2000) -> dict:
    """Normalize Operational Security Issue tickets into package remediation candidates and compare them with versions found in local repositories. Read-only."""
    return backend.analyze_security_package_updates(instance, project_key, limit)


def engineering_health(instance: str, jql: str, stale_days: int = 90, limit: int = 5000) -> dict:
    """Summarize engineering operational health: stale, blocked, unassigned, status mix, and architectural-domain labels."""
    return backend.engineering_health(instance, jql, stale_days, limit)


async def health(_: Request) -> JSONResponse:
    report = await anyio.to_thread.run_sync(lambda: system_readiness(check_connections=True))
    return JSONResponse({
        "status": "ok" if report["ok"] and report.get("connections_ok", False) else "not_ready",
        "mode": report["mode"],
        "instances": [{"name": row["name"], "type": row["type"], "credentials_loaded": row["credentials_loaded"]} for row in report["instances"]],
        "connections": report["connections"],
        "errors": report["errors"],
        "warnings": report["warnings"],
    }, status_code=200 if report["ok"] and report.get("connections_ok", False) else 503)


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
            ("/health/live", ("GET",), liveness),
        ),
    ))
    registry.add(CapabilityPlugin(
        name="jira",
        tools=(
            list_jira_instances,
            test_jira_connection,
            discover_jira_environment,
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
        tools=(list_local_repositories, scan_repository_packages),
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
