#!/usr/bin/env python3
"""Opt-in read-only deployment checks for configured Pulse Jira adapters."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from engineering_ops.adapters.jira import JiraClient, JiraError
from engineering_ops.backend import EngineeringOpsBackend
from engineering_ops.config import settings


class ReadOnlyJiraClient(JiraClient):
    def request(self, method, path, **kwargs):
        search = method.upper() == "POST" and path in {"/rest/api/2/search", "/rest/api/3/search/jql"}
        if method.upper() != "GET" and not search:
            raise ValueError("Deployment smoke checks forbid Jira mutations")
        return super().request(method, path, **kwargs)


def smoke_instance(name):
    cfg = settings.jira_instances()[name]
    checks = []
    if not cfg.verify_ssl or not cfg.base_url.startswith("https://"):
        return {"instance": name, "type": cfg.instance_type, "passed": False,
                "checks": [{"check": "tls", "passed": False, "reason": "Verified HTTPS is required"}]}
    jira = None
    try:
        jira = ReadOnlyJiraClient(name, cfg)
        backend = EngineeringOpsBackend(client_getter=lambda _: jira)
        project = cfg.default_project
        # Quote the configured project as a literal, not a JQL expression.
        quoted = '"' + project.replace('\\', '\\\\').replace('"', '\\"') + '"' if project else None
        query = f"project = {quoted} ORDER BY updated DESC" if quoted else "updated >= -30d ORDER BY updated DESC"
        operations = [
            ("authentication", jira.myself),
            ("fields", jira.fields),
            ("projects", lambda: jira.projects(limit=5)),
            ("boards", lambda: jira.boards(project, limit=5)),
            ("sample_health_report", lambda: backend.engineering_health(name, query, limit=5)),
        ]
        for check, fn in operations:
            try:
                value = fn()
                checks.append({"check": check, "passed": True,
                               "count": len(value) if isinstance(value, list) else value.get("issue_count") if isinstance(value, dict) else None})
            except Exception as exc:
                checks.append({"check": check, "passed": False, "error_type": type(exc).__name__,
                               "http_status": exc.status_code if isinstance(exc, JiraError) else None})
                # Credentials or connectivity failure should not produce a burst of retries.
                if check == "authentication": break
    except Exception as exc:
        checks.append({"check": "configuration", "passed": False, "error_type": type(exc).__name__})
    finally:
        if jira is not None: jira.close()
    return {"instance": name, "type": cfg.instance_type, "passed": all(c["passed"] for c in checks), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", action="append", required=True, help="Explicitly authorized configured instance; repeat for multiple")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=8)
    args = parser.parse_args()
    configs = settings.jira_instances()
    if args.timeout <= 0 or any(name not in configs for name in args.instance):
        parser.error("Positive timeout and known instances are required")
    settings.mode = "recommend_only"
    settings.request_timeout_seconds = args.timeout
    with ThreadPoolExecutor(max_workers=min(len(args.instance), 4)) as workers:
        rows = list(workers.map(smoke_instance, args.instance))
    report = {"checked_at": datetime.now(UTC).isoformat(), "mode": "recommend_only", "mutations_attempted": 0,
              "instances": rows, "passed": all(row["passed"] for row in rows)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(args.output, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), "w") as file:
            json.dump(report, file, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
