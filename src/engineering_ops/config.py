from __future__ import annotations

import json
import os
import re
<<<<<<< HEAD
from datetime import date
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
<<<<<<< HEAD
from pydantic import BaseModel, Field, field_validator, model_validator
=======
from pydantic import BaseModel, Field, model_validator
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_LOCAL_FILE = PROJECT_ROOT / ".env.local"


def _load_project_environment() -> list[str]:
    """Load project environment independently of the process working directory.

    Precedence (highest first):
      1. Existing process environment (shell, Docker, Kubernetes, secret manager)
      2. .env.local
      3. .env

    Existing process variables are deliberately never overwritten.
    """
    merged: dict[str, str] = {}
    loaded: list[str] = []
    if ENV_FILE.exists():
        merged.update({k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None})
        loaded.append(str(ENV_FILE))
    if ENV_LOCAL_FILE.exists():
        merged.update({k: v for k, v in dotenv_values(ENV_LOCAL_FILE).items() if v is not None})
        loaded.append(str(ENV_LOCAL_FILE))
    for key, value in merged.items():
        os.environ.setdefault(key, value)
    return loaded


LOADED_ENV_FILES = _load_project_environment()


class LegacyAuthConfig(BaseModel):
    """Backward compatibility for pre-1.0 jira_instances.json files."""
    mode: Literal["basic", "bearer", "pat"]
    username_env: str | None = None
    secret_env: str


class JiraInstanceConfig(BaseModel):
    instance_type: Literal["cloud", "datacenter", "server"] = Field(alias="type")
    base_url: str
    credentials: str | None = None
    default_project: str | None = None
    quarter_field_name: str = "Target Quarter"
    story_points_field_name: str = "Story Points"
<<<<<<< HEAD
    team_field_name: str = "Team"
    pt_field_name: str = "PT"
    team_pt_field_name: str = "Team/PT"
    start_date_field_name: str = "Start date"
    end_date_field_name: str = "End date"
    hierarchy_field_names: list[str] = Field(default_factory=lambda: ["Parent Link", "Epic Link"])
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
    default_board_id: int | None = None
    sprint_capacity_points: float | None = None
    sprint_capacity_issue_count: int | None = None
    sprint_capacity_buffer_percent: float = 0.0
    verify_ssl: bool = True

    # Accepted only to make upgrades non-breaking. New configs should not use it.
    legacy_kind: Literal["cloud", "datacenter", "server"] | None = Field(default=None, alias="kind", exclude=True)
    legacy_auth: LegacyAuthConfig | None = Field(default=None, alias="auth", exclude=True)
    legacy_api_version: str | None = Field(default=None, alias="api_version", exclude=True)

<<<<<<< HEAD
    model_config = {"populate_by_name": True, "extra": "forbid"}
=======
    model_config = {"populate_by_name": True, "extra": "ignore"}
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, data: Any) -> Any:
        if isinstance(data, dict) and "type" not in data and "kind" in data:
            data = dict(data)
            data["type"] = data["kind"]
        return data

    @model_validator(mode="after")
    def clean(self) -> "JiraInstanceConfig":
        self.base_url = self.base_url.rstrip("/")
<<<<<<< HEAD
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must use http:// or https://")
        if self.sprint_capacity_points is not None and self.sprint_capacity_points <= 0:
            raise ValueError("sprint_capacity_points must be greater than zero")
        if self.sprint_capacity_issue_count is not None and self.sprint_capacity_issue_count <= 0:
            raise ValueError("sprint_capacity_issue_count must be greater than zero")
        if not 0 <= self.sprint_capacity_buffer_percent < 100:
            raise ValueError("sprint_capacity_buffer_percent must be between 0 and 100")
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
        if not self.credentials:
            # Credential reference defaults to instance name later in Settings.jira_instances().
            self.credentials = None
        return self

    @property
    def kind(self) -> str:
        """Compatibility alias used by existing service code."""
        return self.instance_type

    @property
    def api_version(self) -> str:
        """API version is an adapter concern, not user configuration."""
        return "3" if self.instance_type == "cloud" else "2"


<<<<<<< HEAD
class FiscalQuarterConfig(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def valid_range(self) -> "FiscalQuarterConfig":
        if self.end < self.start:
            raise ValueError("fiscal quarter end must be on or after start")
        return self


=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
class ResolvedCredential(BaseModel):
    method: Literal["cloud_api_token", "personal_access_token", "basic_fallback", "legacy"]
    username: str | None = None
    secret: str
    environment_variables: list[str]


class Settings(BaseSettings):
<<<<<<< HEAD
    state_db_file: str = Field("config/pulse-state.sqlite3", alias="PULSE_STATE_DB")
    model_config = SettingsConfigDict(env_file=None, extra="ignore", populate_by_name=True)

    mode: Literal["recommend_only", "safe_apply", "approved_destructive"] = Field("recommend_only", alias="MODE")
    mcp_host: str = Field("127.0.0.1", alias="MCP_HOST")
    mcp_port: int = Field(8080, alias="MCP_PORT")
    mcp_bearer_token: str | None = Field(None, alias="MCP_BEARER_TOKEN")
    mcp_public_url: str | None = Field(None, alias="MCP_PUBLIC_URL")
    jira_instances_file: str = Field("config/jira_instances.json", alias="JIRA_INSTANCES_FILE")
    request_timeout_seconds: float = Field(60, alias="REQUEST_TIMEOUT_SECONDS")
    max_search_results: int = Field(5000, alias="MAX_SEARCH_RESULTS")
    bulk_batch_size: int = Field(50, alias="BULK_BATCH_SIZE")
    local_repo_root: str | None = Field(None, alias="LOCAL_REPO_ROOT")
    security_issue_summary_marker: str = Field("Operational Security Issue", alias="SECURITY_ISSUE_SUMMARY_MARKER")
    fiscal_calendar: dict[str, FiscalQuarterConfig] = Field(default_factory=dict, alias="FISCAL_CALENDAR")
    fiscal_year_start_month: int = Field(8, alias="FISCAL_YEAR_START_MONTH")
    fiscal_year_start_day: int = Field(1, alias="FISCAL_YEAR_START_DAY")
    portfolio_team_options: list[str] = Field(default_factory=lambda: ["Platform Excellence"], alias="PORTFOLIO_TEAM_OPTIONS")
    portfolio_pt_options: list[str] = Field(default_factory=lambda: ["Muon", "Atlas", "Phoenix", "Dragon"], alias="PORTFOLIO_PT_OPTIONS")

    @field_validator("mcp_port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("MCP_PORT must be between 1 and 65535")
        return value

    @field_validator("request_timeout_seconds")
    @classmethod
    def positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be greater than zero")
        return value

    @field_validator("max_search_results")
    @classmethod
    def positive_search_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_SEARCH_RESULTS must be greater than zero")
        return value

    @field_validator("bulk_batch_size")
    @classmethod
    def valid_bulk_batch_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("BULK_BATCH_SIZE must be greater than zero")
        return value

    @field_validator("fiscal_calendar", mode="before")
    @classmethod
    def parse_fiscal_calendar(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            return json.loads(text)
        return value

    @field_validator("fiscal_year_start_month")
    @classmethod
    def valid_fiscal_year_start_month(cls, value: int) -> int:
        if not 1 <= value <= 12:
            raise ValueError("FISCAL_YEAR_START_MONTH must be between 1 and 12")
        return value

    @field_validator("fiscal_year_start_day")
    @classmethod
    def valid_fiscal_year_start_day(cls, value: int) -> int:
        if not 1 <= value <= 31:
            raise ValueError("FISCAL_YEAR_START_DAY must be between 1 and 31")
        return value

    @field_validator("portfolio_team_options", "portfolio_pt_options", mode="before")
    @classmethod
    def parse_string_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @property
    def state_db_path(self) -> Path:
        path = Path(self.state_db_file).expanduser()
        return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
=======
    model_config = SettingsConfigDict(env_file=None, extra="ignore", populate_by_name=True)

    mode: Literal["recommend_only", "safe_apply", "approved_destructive"] = Field("recommend_only", alias="MODE")
    mcp_host: str = Field("0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(8080, alias="MCP_PORT")
    mcp_bearer_token: str | None = Field(None, alias="MCP_BEARER_TOKEN")
    jira_instances_file: str = Field("config/jira_instances.json", alias="JIRA_INSTANCES_FILE")
    request_timeout_seconds: float = Field(60, alias="REQUEST_TIMEOUT_SECONDS")
    max_search_results: int = Field(5000, alias="MAX_SEARCH_RESULTS")
    bulk_batch_size: int = Field(500, alias="BULK_BATCH_SIZE")
    local_repo_root: str | None = Field(None, alias="LOCAL_REPO_ROOT")
    security_issue_summary_marker: str = Field("Operational Security Issue", alias="SECURITY_ISSUE_SUMMARY_MARKER")
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)

    @property
    def jira_instances_path(self) -> Path:
        configured = Path(self.jira_instances_file).expanduser()
        return configured.resolve() if configured.is_absolute() else (PROJECT_ROOT / configured).resolve()

    @property
    def local_repo_path(self) -> Path | None:
        if not self.local_repo_root:
            return None
        return Path(self.local_repo_root).expanduser().resolve()

    def jira_instances(self) -> dict[str, JiraInstanceConfig]:
        path = self.jira_instances_path
        if not path.exists():
            raise RuntimeError(f"Jira instances file not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in Jira instances file {path}: {exc}") from exc
        if not isinstance(data, dict) or not data:
            raise RuntimeError(f"Jira instances file must contain a non-empty object: {path}")
        result: dict[str, JiraInstanceConfig] = {}
        for name, raw in data.items():
            cfg = JiraInstanceConfig.model_validate(raw)
            if not cfg.credentials:
                cfg.credentials = name
            result[name] = cfg
        return result


settings = Settings()


def _credential_prefix(reference: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", reference).strip("_").upper()
    if not normalized:
        raise RuntimeError("Credential reference cannot be empty")
    return f"JIRA_{normalized}"


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def resolve_credentials(instance_name: str, cfg: JiraInstanceConfig) -> ResolvedCredential:
    """Resolve credentials without exposing HTTP auth mechanics in instance config.

    Cloud:
      JIRA_<REF>_EMAIL + JIRA_<REF>_API_TOKEN -> Basic(email, API token)

    Data Center / Server:
      Prefer JIRA_<REF>_PAT -> Bearer PAT
      Otherwise JIRA_<REF>_USERNAME + JIRA_<REF>_PASSWORD -> Basic fallback

    Existing pre-1.0 auth blocks remain supported during migration.
    """
    if cfg.legacy_auth:
        legacy = cfg.legacy_auth
        username = _required(legacy.username_env) if legacy.username_env else None
        return ResolvedCredential(
            method="legacy",
            username=username,
            secret=_required(legacy.secret_env),
            environment_variables=[x for x in [legacy.username_env, legacy.secret_env] if x],
        )

    ref = cfg.credentials or instance_name
    prefix = _credential_prefix(ref)

    if cfg.instance_type == "cloud":
        email_var = f"{prefix}_EMAIL"
        token_var = f"{prefix}_API_TOKEN"
        return ResolvedCredential(
            method="cloud_api_token",
            username=_required(email_var),
            secret=_required(token_var),
            environment_variables=[email_var, token_var],
        )

    pat_var = f"{prefix}_PAT"
    pat = os.getenv(pat_var)
    if pat:
        return ResolvedCredential(
            method="personal_access_token",
            secret=pat,
            environment_variables=[pat_var],
        )

    username_var = f"{prefix}_USERNAME"
    password_var = f"{prefix}_PASSWORD"
    if os.getenv(username_var) and os.getenv(password_var):
        return ResolvedCredential(
            method="basic_fallback",
            username=_required(username_var),
            secret=_required(password_var),
            environment_variables=[username_var, password_var],
        )

    raise RuntimeError(
        f"Instance '{instance_name}' credentials are not configured. "
        f"Set {pat_var} (preferred) or both {username_var} and {password_var}."
    )


def configuration_report() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    instances_report: list[dict[str, Any]] = []
    try:
        instances = settings.jira_instances()
    except Exception as exc:
        instances = {}
        errors.append(str(exc))

    for name, cfg in instances.items():
        try:
            cred = resolve_credentials(name, cfg)
            credentials_loaded = True
            credential_method = cred.method
            required_environment = cred.environment_variables
            credential_error = None
        except Exception as exc:
            credentials_loaded = False
            credential_method = None
            required_environment = []
            credential_error = str(exc)
            errors.append(str(exc))

        if cfg.legacy_auth:
            warnings.append(f"Instance '{name}' uses deprecated auth configuration; migrate to 'credentials'.")
        if cfg.legacy_api_version:
            warnings.append(f"Instance '{name}' config contains deprecated api_version; it is now inferred from type.")

        instances_report.append({
            "name": name,
            "type": cfg.instance_type,
            "base_url": cfg.base_url,
            "credentials": cfg.credentials,
            "credential_method": credential_method,
            "required_environment": required_environment,
            "credentials_loaded": credentials_loaded,
            "credential_error": credential_error,
        })

    repo_path = settings.local_repo_path
    if repo_path and not repo_path.exists():
        warnings.append(f"LOCAL_REPO_ROOT does not exist: {repo_path}")
    if not LOADED_ENV_FILES:
        warnings.append(
            f"No .env or .env.local file was found under project root {PROJECT_ROOT}; only process environment variables are available."
        )
<<<<<<< HEAD
    if settings.bulk_batch_size > 50:
        warnings.append(
            f"BULK_BATCH_SIZE={settings.bulk_batch_size} exceeds Jira's limit and will be capped at 50."
        )

    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if settings.mcp_host not in loopback_hosts and not settings.mcp_bearer_token:
        errors.append("MCP_BEARER_TOKEN is required when MCP_HOST is not a loopback address.")
    elif settings.mcp_host in loopback_hosts and not settings.mcp_bearer_token:
        warnings.append("MCP bearer authentication is disabled for loopback-only development.")
    if settings.mcp_host not in loopback_hosts and not settings.mcp_public_url:
        warnings.append("MCP_PUBLIC_URL should be set for correct deployed authentication metadata.")
=======
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)

    return {
        "ok": not errors,
        "project_root": str(PROJECT_ROOT),
        "loaded_env_files": LOADED_ENV_FILES,
        "mode": settings.mode,
<<<<<<< HEAD
        "fiscal_calendar": {
            name: {"start": cfg.start.isoformat(), "end": cfg.end.isoformat()}
            for name, cfg in settings.fiscal_calendar.items()
        },
        "fiscal_year_start": {
            "month": settings.fiscal_year_start_month,
            "day": settings.fiscal_year_start_day,
        },
        "portfolio_hygiene": {
            "team_options": settings.portfolio_team_options,
            "pt_options": settings.portfolio_pt_options,
        },
        "mcp": {
            "host": settings.mcp_host,
            "port": settings.mcp_port,
            "authentication_required": bool(settings.mcp_bearer_token),
        },
=======
        "mcp": {"host": settings.mcp_host, "port": settings.mcp_port},
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
        "jira_instances_file": str(settings.jira_instances_path),
        "instances": instances_report,
        "local_repo_root": str(repo_path) if repo_path else None,
        "errors": errors,
        "warnings": warnings,
    }


def validate_startup_configuration() -> dict[str, Any]:
    report = configuration_report()
    if report["errors"]:
        details = "\n".join(f" - {message}" for message in report["errors"])
        raise RuntimeError(f"Configuration validation failed:\n{details}")
    return report
