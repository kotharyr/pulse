from __future__ import annotations

from engineering_ops.adapters.jira import JiraClient, JiraClientManager
from engineering_ops.config import settings


client_manager = JiraClientManager()


def client(instance: str) -> JiraClient:
    configs = settings.jira_instances()
    if instance not in configs:
        raise ValueError(f"Unknown instance {instance!r}; available={list(configs)}")
    return client_manager.get(instance, configs[instance])


def close_clients() -> None:
    client_manager.close()
