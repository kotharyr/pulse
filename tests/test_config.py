from engineering_ops.config import PROJECT_ROOT, JiraInstanceConfig, settings


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
