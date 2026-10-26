import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_config_v1.py"
SPEC = importlib.util.spec_from_file_location("migrate_config_v1", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_migration_preserves_nonstandard_legacy_credentials():
    migrated, warnings = MODULE.migrate({
        "corp": {
            "kind": "datacenter",
            "base_url": "https://jira.example.com",
            "auth": {"mode": "bearer", "secret_env": "SPECIAL_JIRA_TOKEN"},
        }
    })
    assert migrated["corp"]["auth"]["secret_env"] == "SPECIAL_JIRA_TOKEN"
    assert warnings


def test_migration_removes_conventional_legacy_credentials():
    migrated, warnings = MODULE.migrate({
        "cloud": {
            "kind": "cloud",
            "base_url": "https://example.atlassian.net",
            "auth": {
                "mode": "basic",
                "username_env": "JIRA_CLOUD_EMAIL",
                "secret_env": "JIRA_CLOUD_API_TOKEN",
            },
        }
    })
    assert "auth" not in migrated["cloud"]
    assert not warnings

