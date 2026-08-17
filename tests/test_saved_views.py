from types import SimpleNamespace

from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.services.saved_views import SavedViewStore


class FakeSettings:
    max_search_results = 5000

    def jira_instances(self):
        return {"onprem": SimpleNamespace(default_project="WXCNP")}


class FakeSearchJira:
    def search(self, jql, fields, limit):
        return [{"key": "WXCNP-1", "fields": {"summary": "Saved view result"}}]


def test_saved_view_crud_is_local(tmp_path):
    store = SavedViewStore(tmp_path / "views.json")
    backend = EngineeringOpsBackend(
        client_getter=lambda instance: FakeSearchJira(),
        settings=FakeSettings(),
        saved_view_store=store,
    )

    defaults = backend.list_saved_views()["views"]
    assert any(view["name"] == "Operational Security Issues" for view in defaults)

    saved = backend.save_operational_view({
        "name": "Platform Backlog",
        "instance": "onprem",
        "jql": "project = WXCNP ORDER BY updated DESC",
        "metadata": {"team": "platform"},
        "default_columns": ["key", "summary"],
        "default_sort": "updated DESC",
        "dashboard_type": "backlog",
    })["view"]
    assert saved["id"] == "platform-backlog"
    assert backend.get_saved_view("Platform Backlog")["view"]["instance"] == "onprem"

    result = backend.search_saved_view("platform backlog")
    assert result["results"]["issues"][0]["key"] == "WXCNP-1"

    deleted = backend.delete_operational_view("Platform Backlog")
    assert deleted == {"deleted": True, "id": "platform-backlog"}
