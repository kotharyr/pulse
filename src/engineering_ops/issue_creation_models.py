"""Draft input and internal contracts for Jira issue creation.

Typed dictionaries document Jira's JSON boundaries without changing their stored
shape. Dataclasses give the preparation stages named results instead of tuples.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator


DescriptionSection = tuple[str, str | list[str]]
JiraFields = dict[str, Any]
ReporterIdentity = dict[str, str]


class IssueTypeMetadata(TypedDict):
    id: str
    name: str


class FieldSchema(TypedDict, total=False):
    type: str
    items: str
    custom: str


class FieldChoice(TypedDict, total=False):
    id: str
    value: str
    name: str
    displayName: str


class CreationField(TypedDict):
    name: str
    required: NotRequired[bool]
    hasDefaultValue: NotRequired[bool]
    operations: NotRequired[list[str]]
    allowedValues: NotRequired[list[FieldChoice]]
    schema: NotRequired[FieldSchema]


class CreationMetadata(TypedDict):
    project: str
    issue_type: IssueTypeMetadata
    fields: dict[str, CreationField]


class CreationParameters(TypedDict):
    instance: str
    draft: dict[str, Any]
    project: NotRequired[str | None]
    issue_type: NotRequired[str]
    additional_fields: NotRequired[dict[str, Any] | None]


class CreationPreview(TypedDict):
    instance: str
    project: str
    issue_type: str
    summary: str
    description: str
    additional_fields: dict[str, Any]
    reporter: str
    reporter_source: str
    reporter_version: str
    recovery_label: str
    metadata_version: str
    connector_version: str
    payload_version: str


class CreationRecord(TypedDict):
    preview_id: str
    instance: str
    parameters: CreationParameters
    preview: CreationPreview


@dataclass(frozen=True)
class CreationContext:
    metadata: CreationMetadata
    reporter: ReporterIdentity
    reporter_name: str


@dataclass(frozen=True)
class PreparedCreation:
    preview: CreationPreview
    fields: JiraFields


class UserStory(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: str = Field(min_length=1)
    want: str = Field(min_length=1)
    benefit: str = Field(min_length=1)

    def markdown(self) -> str:
        return (
            f"**As a** {self.role},\n\n"
            f"**I want** {self.want},\n\n"
            f"**so that** {self.benefit}."
        )


class IssueDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=255)
    overview: str = Field(
        min_length=1,
        description="Content of the Description's Summary section",
    )
    user_story: UserStory
    description: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    business_value: list[str] = Field(min_length=1)

    @field_validator("summary")
    @classmethod
    def single_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("Summary must be a single line")
        return value

    @field_validator(
        "acceptance_criteria", "dependencies", "out_of_scope", "business_value"
    )
    @classmethod
    def nonempty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError(
                "Section items cannot be blank; use 'None' when explicitly out of scope"
            )
        return [value.strip() for value in values]

    def sections(self) -> list[DescriptionSection]:
        return [
            ("Summary", self.overview),
            ("User Story", self.user_story.markdown()),
            ("Description", self.description),
            ("Acceptance Criteria", self.acceptance_criteria),
            ("Dependencies", self.dependencies),
            ("Out of Scope", self.out_of_scope),
            ("Business Value", self.business_value),
        ]

    def markdown(self) -> str:
        sections = []
        for title, body in self.sections():
            text = "\n".join("- " + item for item in body) if isinstance(body, list) else body
            sections.append(f"## {title}\n\n{text}")
        return "\n\n".join(sections)
