"""Description links are the inclusion ledger for Cloud sprint placeholders."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaceholderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_instance: str = Field(min_length=1)
    instance: str = Field(min_length=1, description="Destination GPK2 connection")
    sprint_id: int = Field(gt=0)
    project: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    issue_type: str = Field(default="Story", min_length=1)
    user_mappings: dict[str, str] = Field(default_factory=dict)
    additional_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_mappings")
    @classmethod
    def nonempty_mappings(cls, mappings: dict[str, str]) -> dict[str, str]:
        if any(not key.strip() or not name.strip() for key, name in mappings.items()):
            raise ValueError("Account mappings require a Cloud account and GPK2 username")
        return {key: name.strip() for key, name in mappings.items()}


@dataclass(frozen=True)
class SourceStory:
    key: str
    summary: str
    url: str
    account_id: str | None
    assignee: str
    email: str | None
    points: float | None

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key, "summary": self.summary, "url": self.url,
            "assignee": self.assignee, "email": self.email, "points": self.points,
        }


def points_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    result = float(number)
    return result if result != float("inf") else None


def sum_points(values: list[float]) -> float:
    total = float(sum((Decimal(str(value)) for value in values), Decimal(0)))
    if not math.isfinite(total):
        raise ValueError("Story-point total is too large")
    return total


def source_link(base_url: str, key: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", key):
        raise ValueError("Jira returned an invalid issue key")
    return base_url.rstrip("/") + "/browse/" + key


def included_keys(description: str, source_base: str) -> set[str]:
    """Recognize wiki, Markdown and plain links only from this Cloud instance.

    Key text alone never proves inclusion. Host and context path are checked so
    similarly named issues on another Jira instance cannot suppress real work.
    """
    base = urlsplit(source_base.rstrip("/"))
    prefix = base.path.rstrip("/") + "/browse/"
    keys = set()
    for url in re.findall(r"https?://[^\s<>|)\]]+", description):
        parsed = urlsplit(url.rstrip(".,;"))
        if parsed.scheme != base.scheme or parsed.netloc.lower() != base.netloc.lower():
            continue
        if not parsed.path.startswith(prefix):
            continue
        key = parsed.path[len(prefix):]
        if re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", key):
            keys.add(key)
    return keys


def append_stories(description: str, stories: list[SourceStory], sprint: dict) -> str:
    if not description:
        description = (
            "h2. Cloud sprint reconciliation\n"
            f"Sprint: {' '.join(sprint['name'].split())} (ID: {sprint['id']})\n\n"
            "h3. Included Cloud issues"
        )
    lines = [
        f"* [{story.key}|{story.url}] "
        f"({story.points:g} story points)"
        for story in stories
    ]
    return description + "\n" + "\n".join(lines)
