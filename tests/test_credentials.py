import os

from engineering_ops.config import JiraInstanceConfig, resolve_credentials


def test_cloud_credential_inference(monkeypatch):
    monkeypatch.setenv("JIRA_CLOUD_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_CLOUD_API_TOKEN", "token")
    cfg = JiraInstanceConfig.model_validate({"type": "cloud", "base_url": "https://x", "credentials": "cloud"})
    cred = resolve_credentials("cloud", cfg)
    assert cred.method == "cloud_api_token"
    assert cred.username == "user@example.com"


def test_datacenter_pat_is_preferred(monkeypatch):
    monkeypatch.setenv("JIRA_ONPREM_PAT", "pat")
    monkeypatch.setenv("JIRA_ONPREM_USERNAME", "user")
    monkeypatch.setenv("JIRA_ONPREM_PASSWORD", "password")
    cfg = JiraInstanceConfig.model_validate({"type": "datacenter", "base_url": "https://x", "credentials": "onprem"})
    cred = resolve_credentials("onprem", cfg)
    assert cred.method == "personal_access_token"
    assert cred.secret == "pat"


def test_datacenter_basic_fallback(monkeypatch):
    monkeypatch.delenv("JIRA_ONPREM_PAT", raising=False)
    monkeypatch.setenv("JIRA_ONPREM_USERNAME", "user")
    monkeypatch.setenv("JIRA_ONPREM_PASSWORD", "password")
    cfg = JiraInstanceConfig.model_validate({"type": "datacenter", "base_url": "https://x", "credentials": "onprem"})
    cred = resolve_credentials("onprem", cfg)
    assert cred.method == "basic_fallback"
    assert cred.username == "user"
