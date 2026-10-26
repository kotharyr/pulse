#!/usr/bin/env python3
"""Read-only acceptance probe for an existing authenticated HTTP Jira MCP server."""
import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import tomllib

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def summarize(result):
    payload = result.structuredContent
    if payload is None:
        text = "\n".join(item.text for item in result.content if item.type == "text")
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            payload = None
    failed = result.isError or (isinstance(payload, dict) and (payload.get("success") is False or payload.get("status") == "error" or bool(payload.get("error"))))
    return {"passed": not bool(failed), "response_keys": sorted(payload) if isinstance(payload, dict) else [],
            "returned_items": len(payload) if isinstance(payload, list) else None}


async def smoke(config_path, server, project=None):
    if project and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", project):
        raise ValueError("Project must be a Jira project key")
    cfg = tomllib.loads(Path(config_path).expanduser().read_text())["mcp_servers"][server]
    if not cfg.get("enabled", True) or not cfg.get("url", "").startswith("https://"):
        raise ValueError("An enabled HTTPS MCP configuration is required")
    checks = []
    try:
        async with streamablehttp_client(cfg["url"], headers=cfg.get("http_headers"), timeout=15, sse_read_timeout=30) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                checks.append({"check": "mcp_initialization", "passed": True, "tool_count": len(tools)})
                for suffix, args in [
                    ("get_triage_current_user", {}),
                    ("search_issues_page", {"jql": f"project = {project} ORDER BY updated DESC" if project else "updated >= -30d ORDER BY updated DESC", "max_results": 2}),
                    ("get_field_info", {"field_names": ["Story Points", "Target Quarter"]}),
                ]:
                    matches = [tool for tool in tools if tool.name == suffix or tool.name.endswith("_" + suffix)]
                    if len(matches) != 1:
                        checks.append({"check": suffix, "passed": False, "reason": "Read capability unavailable or ambiguous"})
                        continue
                    result = await session.call_tool(matches[0].name, args)
                    checks.append({"check": suffix, **summarize(result)})
    except Exception as exc:
        checks.append({"check": "connection", "passed": False, "error_type": type(exc).__name__})
    return {"mode": "recommend_only", "transport": "mcp", "server": server, "project": project,
            "checked_at": datetime.now(UTC).isoformat(), "mutations_attempted": 0, "checks": checks,
            "passed": bool(checks) and all(check["passed"] for check in checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path.home()/".codex/config.toml"))
    parser.add_argument("--server", required=True)
    parser.add_argument("--project", help="Optional Jira project key; an instance name is not a project key")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(smoke(args.config, args.server, args.project))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
