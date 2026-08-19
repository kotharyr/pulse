import pytest

from engineering_ops.config import PROJECT_ROOT, JiraInstanceConfig, Settings, settings


def test_url_trim():
    config = JiraInstanceConfig.model_validate({"type": "cloud", "base_url": "https://x/", "credentials": "cloud"})
    assert config.base_url == "https://x"


def test_project_root_contains_pyproject():
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_relative_instance_file_is_root_relative():
    assert settings.jira_instances_path == (PROJECT_ROOT / settings.jira_instances_file).resolve()


def test_api_version_is_inferred():
    cloud = JiraInstanceConfig.model_validate({"type": "cloud", "base_url": "https://x", "credentials": "cloud"})
    dc = JiraInstanceConfig.model_validate({"type": "datacenter", "base_url": "https://x", "credentials": "onprem"})
    assert cloud.api_version == "3"
    assert dc.api_version == "2"


def test_legacy_kind_is_migrated():
    cfg = JiraInstanceConfig.model_validate({"kind": "cloud", "base_url": "https://x", "credentials": "cloud"})
    assert cfg.instance_type == "cloud"


def test_instance_config_rejects_unknown_keys():
    with pytest.raises(ValueError):
        JiraInstanceConfig.model_validate({"type": "cloud", "base_url": "https://x", "typo": True})


def test_settings_default_to_loopback():
    isolated = Settings(_env_file=None, MCP_HOST="127.0.0.1", BULK_BATCH_SIZE=50)
    assert isolated.mcp_host == "127.0.0.1"


def test_fiscal_calendar_parses_from_environment_json():
    isolated = Settings(
        _env_file=None,
        MCP_HOST="127.0.0.1",
        BULK_BATCH_SIZE=50,
        FISCAL_CALENDAR='{"FY27Q1":{"start":"2026-08-01","end":"2026-10-31"}}',
    )

    assert isolated.fiscal_calendar["FY27Q1"].start.isoformat() == "2026-08-01"


def test_portfolio_hygiene_options_parse_comma_strings():
    isolated = Settings(
        _env_file=None,
        MCP_HOST="127.0.0.1",
        BULK_BATCH_SIZE=50,
        PORTFOLIO_TEAM_OPTIONS="Platform Excellence",
        PORTFOLIO_PT_OPTIONS="Muon,Atlas,Phoenix,Dragon",
    )

    assert isolated.portfolio_team_options == ["Platform Excellence"]
    assert isolated.portfolio_pt_options == ["Muon", "Atlas", "Phoenix", "Dragon"]
