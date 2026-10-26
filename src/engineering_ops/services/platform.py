from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class PlatformDiagnostics:
    """Sanitized Pulse platform status, diagnostics, and metrics."""

    def __init__(self, backend: Any, started_at: float):
        self.backend = backend
        self.started_at = started_at

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "product": "Pulse",
            "service": "engineering-operations-platform",
            "mode": self.backend.settings.mode,
            "timestamp": now_iso(),
        }

    def readiness(self) -> dict[str, Any]:
        report = self.backend.configuration_reporter()
        ready = bool(report.get("ok"))
        return {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "mode": report.get("mode"),
            "errors": report.get("errors", []),
            "warnings": report.get("warnings", []),
            "connectors": self.connector_status(report),
        }

    def configuration_summary(self) -> dict[str, Any]:
        report = self.backend.configuration_reporter()
        return {
            "product": "Pulse",
            "mode": report.get("mode"),
            "project_root": report.get("project_root"),
            "loaded_env_files": report.get("loaded_env_files", []),
            "mcp": report.get("mcp", {}),
            "jira_instances_file": report.get("jira_instances_file"),
            "local_repo_root": report.get("local_repo_root"),
            "connector_count": len(report.get("instances", [])),
            "connectors": self.connector_status(report),
            "role_model": self.role_model(),
            "scheduler": self.scheduler_status(),
            "errors": report.get("errors", []),
            "warnings": report.get("warnings", []),
        }

    def connector_status(self, report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        current = report or self.backend.configuration_reporter()
        rows = []
        for instance in current.get("instances", []):
            rows.append({
                "name": instance.get("name"),
                "connector": "jira",
                "type": instance.get("type"),
                "base_url": instance.get("base_url"),
                "status": "configured" if instance.get("credentials_loaded") else "needs_credentials",
                "credentials_loaded": bool(instance.get("credentials_loaded")),
                "credential_method": instance.get("credential_method"),
                "error": instance.get("credential_error"),
            })
        repo_root = current.get("local_repo_root")
        rows.append({
            "name": "local_repositories",
            "connector": "repository_inventory",
            "type": "filesystem",
            "status": "configured" if repo_root else "not_configured",
            "root": repo_root,
        })
        rows.extend([
            {"name": "github", "connector": "github", "type": "future", "status": "not_configured"},
            {"name": "webex", "connector": "webex", "type": "future", "status": "not_configured"},
            {"name": "email", "connector": "email", "type": "future", "status": "not_configured"},
            {"name": "confluence", "connector": "confluence", "type": "future", "status": "not_configured"},
        ])
        return rows

    def diagnostics(self) -> dict[str, Any]:
        readiness = self.readiness()
        return {
            "product": "Pulse",
            "status": readiness["status"],
            "timestamp": now_iso(),
            "configuration": self.configuration_summary(),
            "metrics": self.system_metrics(),
            "audit": {"count": self.backend.audit_trail.count(), "recent": self.backend.audit_trail.list(20)},
            "execution_history": self.backend.execution_history(20),
            "readiness": readiness,
        }

    def system_metrics(self) -> dict[str, Any]:
        uptime = max(0, monotonic() - self.started_at)
        environment_cache = self.backend.environment_cache.all()
        saved_views = self.backend.list_saved_views().get("views", [])
        executions = self.backend.execution_history(100).get("executions", [])
        repo_path = self.backend.settings.local_repo_path
        return {
            "uptime_seconds": round(uptime, 3),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "process": {"pid": self._pid(), "implementation": platform.python_implementation()},
            "configured_instances": len(self.backend.settings.jira_instances()),
            "cached_environments": len(environment_cache),
            "saved_views": len(saved_views),
            "execution_records": len(executions),
            "audit_events": self.backend.audit_trail.count(),
            "local_repo_root_exists": bool(repo_path and Path(repo_path).exists()),
        }

    def scheduler_status(self) -> dict[str, Any]:
        return {
            "environment_refresh": {
                "enabled": False,
                "mode": "manual",
                "next_run": None,
                "last_run": max(
                    [row.get("refreshed_at") for row in self.backend.environment_cache.all().values() if row.get("refreshed_at")],
                    default=None,
                ),
            }
        }

    def role_model(self) -> dict[str, Any]:
        return {
            "viewer": ["read_health", "read_diagnostics", "run_read_only_reviews"],
            "operator": ["create_previews", "reject_previews", "refresh_environment"],
            "admin": ["configure_connectors", "publish_mcp_actions"],
            "destructive_operator": ["apply_approved_destructive_previews"],
        }

    def _pid(self) -> int:
        try:
            import os

            return os.getpid()
        except Exception:
            return 0
