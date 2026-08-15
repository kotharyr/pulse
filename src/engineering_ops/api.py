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


def console_routes() -> tuple[tuple[str, tuple[str, ...], Any], ...]:
    return (
        ("/console", ("GET",), console_index),
        ("/console/", ("GET",), console_index),
        ("/console/{asset}", ("GET",), console_asset),
        ("/api/instances", ("GET",), api_instances),
        ("/api/issues", ("GET",), api_issue_search),
        ("/api/sprint/analysis", ("GET",), api_sprint_analysis),
        ("/api/executions/preview", ("POST",), api_execution_preview),
        ("/api/executions/{preview_id}/apply", ("POST",), api_execution_apply),
        ("/api/executions/{preview_id}/reject", ("POST",), api_execution_reject),
        ("/api/executions", ("GET",), api_execution_history),
    )
