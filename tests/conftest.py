"""Offline test defaults: never use local Jira settings or real network connections."""
import os
import socket

import pytest

os.environ["MODE"] = "recommend_only"
os.environ["JIRA_INSTANCES_FILE"] = "config/jira_instances.example.json"
os.environ["MCP_HOST"] = "127.0.0.1"
os.environ["MCP_BEARER_TOKEN"] = ""
os.environ["LOCAL_REPO_ROOT"] = ""


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("External network connections are disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
