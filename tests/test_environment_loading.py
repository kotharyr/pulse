import os
from pathlib import Path

<<<<<<< HEAD
from engineering_ops.config import LOADED_ENV_FILES, PROJECT_ROOT, configuration_report, settings
=======
from engineering_ops.config import LOADED_ENV_FILES, PROJECT_ROOT, configuration_report
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)


def test_environment_paths_are_project_rooted():
    for loaded in LOADED_ENV_FILES:
        assert Path(loaded).parent == PROJECT_ROOT


def test_configuration_report_is_secret_safe():
    report = configuration_report()
    serialized = repr(report)
    for name in (
        "JIRA_CLOUD_API_TOKEN",
        "JIRA_ONPREM_PAT",
        "JIRA_ONPREM_PASSWORD",
        "MCP_BEARER_TOKEN",
    ):
        value = os.getenv(name)
        if value:
            assert value not in serialized
<<<<<<< HEAD


def test_non_loopback_bind_requires_mcp_token(monkeypatch):
    monkeypatch.setattr(settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(settings, "mcp_bearer_token", None)
    report = configuration_report()
    assert not report["ok"]
    assert any("MCP_BEARER_TOKEN" in error for error in report["errors"])
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
