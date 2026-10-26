"""Retrieve Jira create-screen metadata and the authenticated reporter identity."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

# Preserve the existing adapter import path while rendering lives separately.
from engineering_ops.adapters.issue_descriptions import (
    formatted_description as formatted_description,
)
from engineering_ops.issue_creation_models import (
    CreationField,
    CreationMetadata,
    ReporterIdentity,
)

if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient


MetadataRow = dict[str, Any]


def metadata_pages(jira: JiraClient, path: str, key: str) -> list[MetadataRow]:
    from engineering_ops.adapters.jira import JiraError

    rows: list[MetadataRow] = []
    while True:
        data = jira.request("GET", path, params={"startAt": len(rows), "maxResults": 50})
        batch = data.get(key, data.get("values", []))
        rows.extend(batch)
        total = data.get("total")
        if data.get("isLast") is True or (total is not None and len(rows) >= total):
            return rows
        if data.get("isLast") is None and total is None:
            raise JiraError("Creation metadata omitted pagination boundaries")
        if not batch:
            raise JiraError("Creation metadata pagination stopped before all fields were returned")


def paginated_metadata(
    jira: JiraClient, project: str, issue_type: str
) -> CreationMetadata:
    root = f"/rest/api/{jira.platform_api_version}/issue/createmeta"
    project_path = quote(project, safe="")
    types = metadata_pages(jira, f"{root}/{project_path}/issuetypes", "issueTypes")
    matches = [row for row in types if row["name"].casefold() == issue_type.casefold()]
    if len(matches) != 1:
        choices = ", ".join(row["name"] for row in types)
        raise ValueError("Choose an available issue type: " + choices)
    selected = matches[0]
    type_path = quote(str(selected["id"]), safe="")
    fields = metadata_pages(
        jira, f"{root}/{project_path}/issuetypes/{type_path}", "fields"
    )
    # Jira supplies open JSON objects; keep all metadata for approval fingerprints.
    fields_by_id = cast(
        dict[str, CreationField],
        {row.get("fieldId") or row["key"]: row for row in fields},
    )
    return {
        "project": project,
        "issue_type": {"id": str(selected["id"]), "name": selected["name"]},
        "fields": fields_by_id,
    }


def legacy_metadata(jira: JiraClient, project: str, issue_type: str) -> CreationMetadata:
    data = jira.request(
        "GET",
        f"/rest/api/{jira.platform_api_version}/issue/createmeta",
        params={
            "projectKeys": project,
            "issuetypeNames": issue_type,
            "expand": "projects.issuetypes.fields",
        },
    )
    matches = [
        (project_row, type_row)
        for project_row in data.get("projects", [])
        for type_row in project_row.get("issuetypes", [])
        if project_row.get("key", "").casefold() == project.casefold()
        and type_row.get("name", "").casefold() == issue_type.casefold()
    ]
    if len(matches) != 1:
        raise ValueError("Project or issue type is unavailable for creation")
    project_row, selected = matches[0]
    return {
        "project": project_row["key"],
        "issue_type": {"id": str(selected["id"]), "name": selected["name"]},
        "fields": selected.get("fields", {}),
    }


def creation_metadata(jira: JiraClient, project: str, issue_type: str) -> CreationMetadata:
    from engineering_ops.adapters.jira import JiraError

    try:
        return paginated_metadata(jira, project, issue_type)
    except JiraError as exc:
        if jira.platform_api_version != "2" or exc.status_code not in {404, 405}:
            raise
    # Older Server/DC installations predate the paginated create metadata API.
    return legacy_metadata(jira, project, issue_type)


def reporter_value(jira: JiraClient, user: dict[str, Any]) -> ReporterIdentity:
    """Use authenticated Jira identity, never the Chat actor or a supplied reporter."""
    key = "accountId" if jira.platform_api_version == "3" else "name"
    if user.get("active") is False or not user.get(key):
        raise ValueError("The selected Jira connection has no active reporter identity")
    return {key: user[key]}
