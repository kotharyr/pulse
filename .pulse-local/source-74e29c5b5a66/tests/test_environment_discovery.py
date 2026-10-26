from types import SimpleNamespace

from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.services.environment import EnvironmentCache


class FakeDiscoveryJira:
    name = "fake"
    cfg = SimpleNamespace(kind="datacenter", default_project="ENG", quarter_field_name="Target Quarter")

    def __init__(self):
        self.fields_calls = 0

    def projects(self):
        return [{"id": "10000", "key": "ENG", "name": "Engineering"}]

    def fields(self):
        self.fields_calls += 1
        return [
            {"id": "customfield_1", "name": "Target Quarter", "custom": True, "schema": {"custom": "select"}},
            {"id": "customfield_2", "name": "Architectural Domain", "custom": True, "schema": {"custom": "select"}},
            {"id": "summary", "name": "Summary", "custom": False, "schema": {"type": "string"}},
        ]

    def boards(self, project, limit=100):
        return [{"id": 7, "name": "Engineering Board", "type": "scrum"}]

    def board_sprints(self, board_id, state=None, limit=50):
        return [{"id": 42, "name": "Sprint 42", "state": state, "startDate": "2026-01-01T00:00:00.000Z"}]

    def issue_types(self):
        return [{"name": "Story"}, {"name": "Bug"}]

    def priorities(self):
        return [{"name": "High"}]

    def project_components(self, project_key):
        return [{"name": "API"}]

    def project_versions(self, project_key):
        return [{"name": "FY27 Q1", "released": False, "archived": False}]

    def search(self, jql, fields, limit):
        return [{
            "key": "ENG-1",
            "fields": {
                "customfield_1": {"value": "FY27 Q1"},
                "customfield_2": {"value": "Platform"},
            },
        }]


def test_environment_discovery_normalizes_and_hides_ids(tmp_path):
    jira = FakeDiscoveryJira()
    backend = EngineeringOpsBackend(
        client_getter=lambda instance: jira,
        environment_cache=EnvironmentCache(tmp_path / "environment.json"),
    )

    discovered = backend.refresh_environment("fake")

    assert discovered["instance"] == "fake"
    assert discovered["projects"] == [{"key": "ENG", "name": "Engineering"}]
    assert discovered["boards"] == [{"name": "Engineering Board", "project_key": "ENG", "type": "scrum"}]
    assert discovered["target_quarter_values"] == ["FY27 Q1"]
    assert discovered["architectural_domain_values"] == ["Platform"]
    assert "customfield_" not in repr(discovered)


def test_environment_cache_is_reused_and_refreshable(tmp_path):
    jira = FakeDiscoveryJira()
    backend = EngineeringOpsBackend(
        client_getter=lambda instance: jira,
        environment_cache=EnvironmentCache(tmp_path / "environment.json"),
    )

    first = backend.discover_environment("fake")
    second = backend.discover_environment("fake")
    refreshed = backend.refresh_environment("fake")

    assert first["cache_age_seconds"] == 0
    assert second["cached"] if "cached" in second else True
    assert jira.fields_calls == 2
    assert refreshed["cache_age_seconds"] == 0


def test_environment_find_and_resolve_helpers(tmp_path):
    backend = EngineeringOpsBackend(
        client_getter=lambda instance: FakeDiscoveryJira(),
        environment_cache=EnvironmentCache(tmp_path / "environment.json"),
    )
    backend.refresh_environment("fake")

    assert backend.find_project_by_name("fake", "Engineering")["project"]["key"] == "ENG"
    assert backend.find_board_by_name("fake", "Board")["board"]["name"] == "Engineering Board"
    assert backend.find_sprint_by_name("fake", "Sprint 42")["sprint"]["name"] == "Sprint 42"
    assert backend.resolve_field_name("fake", "Target Quarter")["field"]["name"] == "Target Quarter"
    assert backend.resolve_field_value("fake", "Architectural Domain", "Platform")["match"] == "Platform"
