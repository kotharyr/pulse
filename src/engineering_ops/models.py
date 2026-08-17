from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _drop_none(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


@dataclass(frozen=True)
class JiraInstance:
    name: str
    kind: str
    base_url: str
    default_project: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Project:
    key: str | None
    name: str | None
    internal_id: str | None = None

    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        row = {"key": self.key, "name": self.name}
        if include_internal:
            row["id"] = self.internal_id
        return _drop_none(row)


@dataclass(frozen=True)
class Board:
    name: str | None
    project_key: str | None = None
    board_type: str | None = None
    internal_id: int | None = None

    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        row = {"name": self.name, "project_key": self.project_key, "type": self.board_type}
        if include_internal:
            row["id"] = self.internal_id
        return _drop_none(row)


@dataclass(frozen=True)
class Sprint:
    name: str | None
    state: str | None
    board_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    internal_id: int | None = None
    board_internal_id: int | None = None

    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        row = {
            "name": self.name,
            "state": self.state,
            "board_name": self.board_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }
        if include_internal:
            row["id"] = self.internal_id
            row["board_id"] = self.board_internal_id
        return _drop_none(row)


@dataclass(frozen=True)
class Repository:
    name: str
    path: str
    relative_path: str
    languages: list[str] = field(default_factory=list)
    manifests: list[dict[str, Any]] = field(default_factory=list)
    packages: list[dict[str, Any]] = field(default_factory=list)
    container_images: list[dict[str, Any]] = field(default_factory=list)
    codeowners: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Package:
    name: str
    version: str | None
    ecosystem: str
    repo: str | None = None
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class SecurityFinding:
    issue_key: str
    summary: str | None
    cves: list[str]
    packages: list[str]
    fixed_versions: list[dict[str, Any]]
    affected_versions: list[str]
    repository_hints: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class RemediationAction:
    component: str
    required_version: str | None
    action_type: str
    affected_jira_issues: list[str]
    cves: list[str]
    affected_repositories: list[str]
    current_detected_versions: list[str]
    already_fixed_repositories: list[str]
    repositories_requiring_upgrade: list[str]
    unknown_repositories: list[str]
    tickets_potentially_cleared: int
    confidence: float
    parsing_rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class SavedView:
    name: str
    instance: str
    jql: str
    metadata: dict[str, Any] = field(default_factory=dict)
    default_columns: list[str] = field(default_factory=list)
    default_sort: str | None = None
    dashboard_type: str | None = None

    @property
    def id(self) -> str:
        return self.name.strip().casefold().replace(" ", "-")

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["id"] = self.id
        return _drop_none(row)


@dataclass(frozen=True)
class ExecutionPreview:
    preview_id: str
    action: str
    instance: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Finding:
    title: str
    description: str
    severity: str = "info"
    category: str | None = None
    evidence: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Risk:
    title: str
    description: str
    severity: str = "medium"
    affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Recommendation:
    action: str
    rationale: str
    priority: str = "medium"
    owner: str | None = None
    preview_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Metric:
    name: str
    value: Any
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class Confidence:
    score: float
    level: str
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class SourceCoverage:
    source: str
    status: str
    details: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass(frozen=True)
class ExecutionPreviewReference:
    preview_id: str
    action: str
    status: str
    can_apply: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))
