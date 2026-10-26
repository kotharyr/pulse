"""Render the issue template as Jira wiki text or Atlassian Document Format."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from engineering_ops.issue_creation_models import DescriptionSection

if TYPE_CHECKING:
    from engineering_ops.adapters.jira import JiraClient


AdfNode = dict[str, Any]


def wiki_text(text: str) -> str:
    # Markdown bold uses double stars; Jira wiki uses single stars.
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return re.sub(r"(?m)^- ", "* ", text)


def wiki_description(sections: list[DescriptionSection]) -> str:
    rendered = []
    for title, body in sections:
        if isinstance(body, list):
            text = "\n".join("* " + wiki_text(item) for item in body)
        else:
            text = wiki_text(body)
        rendered.append(f"h2. {title}\n\n{text}")
    return "\n\n".join(rendered)


def adf_paragraph(text: str) -> AdfNode:
    content = []
    for part in re.split(r"(\*\*.+?\*\*)", text):
        if not part:
            continue
        bold = part.startswith("**")
        node: AdfNode = {"type": "text", "text": part[2:-2] if bold else part}
        if bold:
            node["marks"] = [{"type": "strong"}]
        content.append(node)
    return {"type": "paragraph", "content": content}


def adf_list_item(text: str) -> AdfNode:
    return {"type": "listItem", "content": [adf_paragraph(text)]}


def adf_text_blocks(text: str) -> list[AdfNode]:
    """Group consecutive Markdown bullets; emit other nonblank lines as paragraphs."""
    nodes = []
    bullets = []
    # The sentinel flushes a trailing list without special end-of-input logic.
    for line in [*text.splitlines(), ""]:
        if line.startswith("- "):
            bullets.append(adf_list_item(line[2:]))
            continue
        if bullets:
            nodes.append({"type": "bulletList", "content": bullets})
            bullets = []
        if line.strip():
            nodes.append(adf_paragraph(line))
    return nodes


def adf_description(sections: list[DescriptionSection]) -> AdfNode:
    nodes = []
    for title, body in sections:
        nodes.append({
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": title}],
        })
        if isinstance(body, list):
            nodes.append({
                "type": "bulletList",
                "content": [adf_list_item(item) for item in body],
            })
        else:
            nodes.extend(adf_text_blocks(body))
    return {"type": "doc", "version": 1, "content": nodes}


def formatted_description(
    jira: JiraClient, sections: list[DescriptionSection]
) -> str | AdfNode:
    if jira.platform_api_version == "3":
        return adf_description(sections)
    return wiki_description(sections)
