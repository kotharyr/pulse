"""Local browser acceptance fixture. Real backend, fake Jira, no external sockets."""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

root = TemporaryDirectory(prefix="pulse-browser-")
folder = Path(root.name)
config = folder / "instances.json"
config.write_text(json.dumps({"cloud": {"type": "cloud", "base_url": "https://fixture.invalid",
    "credentials": "browser", "default_project": "ENG", "default_board_id": 7, "sprint_capacity_points": 20}}))
os.environ.update({"MODE": "recommend_only", "JIRA_INSTANCES_FILE": str(config), "MCP_HOST": "127.0.0.1",
    "MCP_PORT": os.environ["PULSE_BROWSER_PORT"], "MCP_BEARER_TOKEN": "pulse-browser-test",
    "PULSE_STATE_DB": str(folder/"state.sqlite3"), "BULK_BATCH_SIZE": "50", "JIRA_BROWSER_EMAIL": "fixture@example.invalid",
    "JIRA_BROWSER_API_TOKEN": "fixture", "LOCAL_REPO_ROOT": str(folder/"repositories")})
(folder/"repositories").mkdir()

# Protect the fixture even if a future code path attempts a real connection.
_connect = socket.socket.connect

def local_only(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
        raise AssertionError("External network forbidden in browser acceptance")
    return _connect(sock, address)

socket.socket.connect = local_only

from test_durable_execution import RecoverableJira
from engineering_ops.config import settings
from engineering_ops.backend import backend
from engineering_ops.services.environment import EnvironmentCache
from engineering_ops.services.saved_views import SavedViewStore
from engineering_ops.server import create_mcp_server
import uvicorn


class BrowserJira(RecoverableJira):
    def __init__(self):
        super().__init__()
        self.cfg = settings.jira_instances()["cloud"]
        self.sprints[1].update({"name": "Sprint 1"})
        self.sprints[2].update({"name": "Sprint 2"})

    def search(self, jql, fields, limit):
        if jql.startswith("labels ="):
            return super().search(jql, fields, limit)
        return [deepcopy(row) for row in self.all_issues.values()][:limit]

    def fields(self):
        return [{"id": "customfield_1", "name": "Story Points", "custom": True},
                {"id": "customfield_2", "name": "Target Quarter", "custom": True}]

    def projects(self, limit=100): return [{"id": "1", "key": "ENG", "name": "Engineering"}]
    def boards(self, project=None, limit=100): return [{"id": 7, "name": "Delivery", "type": "scrum"}]
    def board_sprints(self, board_id, state=None, limit=100):
        return [deepcopy(s) for s in self.sprints.values() if state is None or s["state"] == state]
    def issue_types(self): return [{"id": "1", "name": "Story"}]
    def priorities(self): return [{"id": "1", "name": "Medium"}]
    def project_components(self, project): return []
    def project_versions(self, project): return []
    def mutate(self, *args): raise AssertionError("Browser acceptance must never mutate Jira")


jira = BrowserJira()
backend.client_getter = lambda instance: jira
backend.environment_cache = EnvironmentCache(folder/"environment.json")
backend.saved_view_store = SavedViewStore(folder/"views.json")

if __name__ == "__main__":
    uvicorn.run(create_mcp_server().streamable_http_app(), host="127.0.0.1", port=int(os.environ["PULSE_BROWSER_PORT"]), log_level="warning")
