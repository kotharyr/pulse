"""Read-only validation shared by issue creation and execution recovery."""
from __future__ import annotations

from typing import TYPE_CHECKING

from engineering_ops.services.executions import fingerprint

if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient
    from engineering_ops.issue_creation_models import CreationPreview


def reporter_matches(jira: JiraClient, issue_key: str, expected_version: str) -> bool:
    """Read the issue directly because Jira's search index may lag behind changes.

    Let read/identity errors propagate: callers distinguish an unreadable reporter
    from a known mismatch, but neither may be treated as a failed create.
    """
    issue = jira.get_issue(issue_key, ["reporter"])
    user = (issue.get("fields") or {}).get("reporter") or {}
    return fingerprint(jira.reporter_value(user)) == expected_version


def preview_matches(current: CreationPreview, reviewed: CreationPreview) -> bool:
    """Compare the complete stored contract, including target and payload hashes."""
    return fingerprint(current) == fingerprint(reviewed)
