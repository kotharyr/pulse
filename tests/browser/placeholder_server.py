"""Loopback-only browser fixture: real Pulse routes, in-memory Jira adapters."""
import json
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
folder = TemporaryDirectory(prefix="pulse-placeholder-browser-")
root = Path(folder.name)
os.environ.update({
    "MODE": "safe_apply", "MCP_HOST": "127.0.0.1",
    "MCP_PORT": os.environ["PULSE_BROWSER_PORT"], "MCP_BEARER_TOKEN": "placeholder-browser-test",
    "PULSE_STATE_DB": str(root / "global.sqlite3"), "LOCAL_REPO_ROOT": "",
    "JIRA_INSTANCES_FILE": str(Path(__file__).resolve().parents[2] / "config/jira_instances.example.json"),
    "JIRA_CLOUD_EMAIL": "fixture@example.invalid", "JIRA_CLOUD_API_TOKEN": "fixture",
    "JIRA_ONPREM_PAT": "fixture",
})
connect = socket.socket.connect

def local_only(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
        raise AssertionError("External Jira/network access forbidden in this fixture")
    return connect(sock, address)

socket.socket.connect = local_only

from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn
import engineering_ops.api as api
import engineering_ops.server as server
from engineering_ops.services.saved_views import SavedViewStore
from test_sprint_placeholders import setup_backend

backend, source, target = setup_backend(root)
source.boards = lambda *a, **kw: [{"id": 7, "name": "SBG Cloud team"}]
source.board_sprints = lambda *a, **kw: [source.sprint(42)]
backend.list_jira_instances = lambda: {"instances": [
    {"name": "cloud", "kind": "cloud", "default_project": "SBG"},
    {"name": "gpk2", "kind": "datacenter", "default_project": "GPK"},
]}
backend.discover_console_sprints = lambda *a: {"current_sprint": None, "next_sprint": None}
backend.saved_view_store = SavedViewStore(root / "views.json")
backend.list_saved_views = lambda: {"views": []}
backend.platform_configuration = lambda: {"mode": "safe_apply", "connectors": []}
backend.connector_status = lambda: {"connectors": []}
backend.platform_diagnostics = lambda: {"status": "ok"}
backend.system_metrics = lambda: {}
api.backend = backend
server.backend = backend

async def add_points(request):
    source.issues[1]["fields"]["customfield_10001"] = 5
    return JSONResponse({"ok": True})

async def state(request):
    return JSONResponse({"calls": target.calls, "issues": target.issues})

app = server.create_mcp_server(validate_configuration=False).streamable_http_app()
app.routes.extend([Route("/__test/points", add_points, methods=["POST"]), Route("/__test/state", state)])
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["PULSE_BROWSER_PORT"]), log_level="warning")
