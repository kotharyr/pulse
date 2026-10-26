"""Creation metadata and description serialization shared by Jira connectors."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote


if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient


def creation_metadata(jira: JiraClient, project: str, issue_type: str) -> dict:
    from engineering_ops.adapters.jira import JiraError

    root = f"/rest/api/{jira.platform_api_version}"
    project_path = quote(project, safe="")

    def pages(path: str, key: str) -> list[dict[str, Any]]:
        rows = []
        while True:
            data = jira.request("GET", path, params={"startAt": len(rows), "maxResults": 50})
            batch = data.get(key, data.get("values", []))
            rows.extend(batch)
            if data.get("isLast") is True or (data.get("total") is not None and len(rows) >= data["total"]):
                return rows
            if data.get("isLast") is None and data.get("total") is None:
                raise JiraError("Creation metadata omitted pagination boundaries")
            if not batch:
                raise JiraError("Creation metadata pagination stopped before all fields were returned")

    try:
        types = pages(f"{root}/issue/createmeta/{project_path}/issuetypes", "issueTypes")
        matches = [row for row in types if row["name"].casefold() == issue_type.casefold()]
        if len(matches) != 1:
            raise ValueError("Choose an available issue type: " + ", ".join(row["name"] for row in types))
        selected = matches[0]
        fields = pages(f"{root}/issue/createmeta/{project_path}/issuetypes/{quote(str(selected['id']), safe='')}", "fields")
        fields = {row.get("fieldId") or row["key"]: row for row in fields}
        return {"project": project, "issue_type": {"id": str(selected["id"]), "name": selected["name"]}, "fields": fields}
    except JiraError as exc:
        if jira.platform_api_version != "2" or exc.status_code not in {404, 405}:
            raise
    # Older Server/DC installations predate the paginated create metadata API.
    data = jira.request("GET", f"{root}/issue/createmeta", params={"projectKeys": project, "issuetypeNames": issue_type, "expand": "projects.issuetypes.fields"})
    matches = [(p, t) for p in data.get("projects", []) for t in p.get("issuetypes", [])
               if p.get("key", "").casefold() == project.casefold() and t.get("name", "").casefold() == issue_type.casefold()]
    if len(matches) != 1:
        raise ValueError("Project or issue type is unavailable for creation")
    project_row, selected = matches[0]
    return {"project": project_row["key"], "issue_type": {"id": str(selected["id"]), "name": selected["name"]}, "fields": selected.get("fields", {})}


def reporter_value(jira: JiraClient, user: dict) -> dict:
    """Use authenticated Jira identity, never the Chat actor or a supplied reporter."""
    key = "accountId" if jira.platform_api_version == "3" else "name"
    if user.get("active") is False or not user.get(key):
        raise ValueError("The selected Jira connection has no active reporter identity")
    return {key: user[key]}


def formatted_description(jira: JiraClient, sections: list[tuple[str, str | list[str]]]) -> Any:
    """Render controlled section structure, with bold inline text and bullet lists."""
    if jira.platform_api_version != "3":
        def wiki(text: str) -> str:
            # The supplied draft uses Markdown bold; Jira wiki uses single stars.
            text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
            return re.sub(r"(?m)^- ", "* ", text)
        return "\n\n".join(f"h2. {title}\n\n" + ("\n".join("* " + wiki(s) for s in body) if isinstance(body, list) else wiki(body)) for title, body in sections)

    def paragraph(text: str) -> dict:
        content = []
        for part in re.split(r"(\*\*.+?\*\*)", text):
            if part:
                content.append({"type": "text", "text": part[2:-2] if part.startswith("**") else part,
                                **({"marks": [{"type": "strong"}]} if part.startswith("**") else {})})
        return {"type": "paragraph", "content": content}

    nodes = []
    for title, body in sections:
        nodes.append({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": title}]})
        if isinstance(body, list):
            nodes.append({"type": "bulletList", "content": [{"type": "listItem", "content": [paragraph(s)]} for s in body]})
        else:
            bullets = []
            for line in [*body.splitlines(), ""]:
                if line.startswith("- "):
                    bullets.append({"type": "listItem", "content": [paragraph(line[2:])]})
                    continue
                if bullets:
                    nodes.append({"type": "bulletList", "content": bullets})
                    bullets = []
                if line.strip():
                    nodes.append(paragraph(line))
    return {"type": "doc", "version": 1, "content": nodes}
