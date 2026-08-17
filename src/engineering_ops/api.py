from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from engineering_ops.backend import backend as shared_backend

backend = shared_backend
STATIC_DIR = Path(__file__).resolve().parent / "console" / "static"


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def _int_query(request: Request, name: str, default: int | None = None) -> int | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    return int(raw)


async def _payload(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


async def console_index(_: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def console_asset(request: Request) -> FileResponse | JSONResponse:
    asset = request.path_params["asset"]
    if asset not in {"app.js", "styles.css"}:
        return _error("Asset not found", 404)
    return FileResponse(STATIC_DIR / asset)


async def api_instances(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.list_jira_instances)
    return JSONResponse(result)


async def api_issue_search(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    jql = request.query_params.get("jql")
    if not instance or not jql:
        return _error("instance and jql are required")
    try:
        page = _int_query(request, "page", 1) or 1
        page_size = _int_query(request, "page_size", 25) or 25
        result = await anyio.to_thread.run_sync(lambda: backend.search_issues_page(instance, jql, page=page, page_size=page_size))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_sprint_analysis(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    sprint_id = _int_query(request, "sprint_id")
    next_sprint_id = _int_query(request, "next_sprint_id")
    if not instance or sprint_id is None:
        return _error("instance and sprint_id are required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.analyze_current_sprint(instance, sprint_id, next_sprint_id))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_sprint_discovery(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    project = request.query_params.get("project")
    if not instance:
        return _error("instance is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.discover_console_sprints(instance, project))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_environment(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    if not instance:
        return _error("instance is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.discover_environment(instance))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_environment_refresh(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}
    instance = payload.get("instance") or request.query_params.get("instance")
    project = payload.get("project") or request.query_params.get("project")
    if not instance:
        return _error("instance is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.refresh_environment(instance, project))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_environment_summary(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.get_environment_summary(instance))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_saved_views(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.list_saved_views)
    return JSONResponse(result)


async def api_saved_view(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.get_saved_view(name))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_saved_view_issues(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    try:
        page = _int_query(request, "page", 1) or 1
        page_size = _int_query(request, "page_size", 25) or 25
        result = await anyio.to_thread.run_sync(lambda: backend.search_saved_view(name, page, page_size))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_saved_view_upsert(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
        result = await anyio.to_thread.run_sync(lambda: backend.save_operational_view(payload))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(f"Missing required field: {exc.args[0]}")
    except Exception as exc:
        return _error(str(exc))


async def api_saved_view_delete(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.delete_operational_view(name))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_repositories(_: Request) -> JSONResponse:
    result = await anyio.to_thread.run_sync(backend.repository_inventory)
    return JSONResponse(result)


async def api_security_remediation(request: Request) -> JSONResponse:
    instance = request.query_params.get("instance")
    project = request.query_params.get("project")
    limit = _int_query(request, "limit", 2000) or 2000
    if not instance:
        return _error("instance is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.analyze_security_package_updates(instance, project, limit))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_execution_preview(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
        action = payload["action"]
        parameters = payload.get("parameters") or {}
        result = await anyio.to_thread.run_sync(lambda: backend.create_execution_preview(action, parameters))
        return JSONResponse(result, status_code=201)
    except KeyError as exc:
        return _error(f"Missing required field: {exc.args[0]}")
    except Exception as exc:
        return _error(str(exc))


async def api_execution_apply(request: Request) -> JSONResponse:
    preview_id = request.path_params["preview_id"]
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.apply_execution_preview(preview_id))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_execution_reject(request: Request) -> JSONResponse:
    preview_id = request.path_params["preview_id"]
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.reject_execution_preview(preview_id))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_execution_history(request: Request) -> JSONResponse:
    limit = _int_query(request, "limit", 50) or 50
    result = await anyio.to_thread.run_sync(lambda: backend.execution_history(limit))
    return JSONResponse(result)


async def api_orchestration_engineering_review(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.engineering_review(**payload))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_sprint_analysis(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.sprint_analysis(**payload))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_sprint_close_preview(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.sprint_close_preview_workflow(**payload))
        return JSONResponse(result, status_code=201)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_sprint_close_apply(request: Request) -> JSONResponse:
    payload = await _payload(request)
    preview_id = payload.get("preview_id")
    if not preview_id:
        return _error("preview_id is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.sprint_close_apply_workflow(preview_id))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_portfolio_review(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.portfolio_review(**payload))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_backlog_review(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.backlog_review(**payload))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_security_remediation(request: Request) -> JSONResponse:
    payload = await _payload(request)
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.security_remediation_analysis(**payload))
        return JSONResponse(result)
    except Exception as exc:
        return _error(str(exc))


async def api_orchestration_saved_view_review(request: Request) -> JSONResponse:
    payload = await _payload(request)
    view_name = payload.pop("view_name", None) or payload.pop("name", None)
    if not view_name:
        return _error("view_name is required")
    try:
        result = await anyio.to_thread.run_sync(lambda: backend.saved_view_review(view_name, **payload))
        return JSONResponse(result)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        return _error(str(exc))


def console_routes() -> tuple[tuple[str, tuple[str, ...], Any], ...]:
    return (
        ("/console", ("GET",), console_index),
        ("/console/", ("GET",), console_index),
        ("/console/{asset}", ("GET",), console_asset),
        ("/api/instances", ("GET",), api_instances),
        ("/api/issues", ("GET",), api_issue_search),
        ("/api/environment", ("GET",), api_environment),
        ("/api/environment/refresh", ("POST",), api_environment_refresh),
        ("/api/environment/summary", ("GET",), api_environment_summary),
        ("/api/views", ("GET",), api_saved_views),
        ("/api/views", ("POST",), api_saved_view_upsert),
        ("/api/views/{name}", ("GET",), api_saved_view),
        ("/api/views/{name}", ("DELETE",), api_saved_view_delete),
        ("/api/views/{name}/issues", ("GET",), api_saved_view_issues),
        ("/api/repositories", ("GET",), api_repositories),
        ("/api/security/remediation", ("GET",), api_security_remediation),
        ("/api/sprint/discovery", ("GET",), api_sprint_discovery),
        ("/api/sprint/analysis", ("GET",), api_sprint_analysis),
        ("/api/executions/preview", ("POST",), api_execution_preview),
        ("/api/executions/{preview_id}/apply", ("POST",), api_execution_apply),
        ("/api/executions/{preview_id}/reject", ("POST",), api_execution_reject),
        ("/api/executions", ("GET",), api_execution_history),
        ("/api/orchestration/engineering-review", ("POST",), api_orchestration_engineering_review),
        ("/api/orchestration/sprint-analysis", ("POST",), api_orchestration_sprint_analysis),
        ("/api/orchestration/sprint-close-preview", ("POST",), api_orchestration_sprint_close_preview),
        ("/api/orchestration/sprint-close-apply", ("POST",), api_orchestration_sprint_close_apply),
        ("/api/orchestration/portfolio-review", ("POST",), api_orchestration_portfolio_review),
        ("/api/orchestration/backlog-review", ("POST",), api_orchestration_backlog_review),
        ("/api/orchestration/security-remediation-analysis", ("POST",), api_orchestration_security_remediation),
        ("/api/orchestration/saved-view-review", ("POST",), api_orchestration_saved_view_review),
    )
