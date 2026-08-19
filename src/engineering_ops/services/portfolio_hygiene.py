from __future__ import annotations

import json
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any

from engineering_ops.services.fields import resolve_field


INITIATIVE_TYPE = "initiative"
PORTFOLIO_TYPES = {"portfolio feature", "epic"}
STORY_TYPES = {"user story", "story"}
QP_LABEL_RE = re.compile(r"^QP-[A-Za-z0-9]+-committed$", re.I)
ORDER_BY_RE = re.compile(r"\s+ORDER\s+BY\s+.+$", re.I)


def _today() -> date:
    return datetime.now(UTC).date()


def _hash_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(text.encode("utf-8")).hexdigest()[:16]


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _quote_field_name(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def _quote_jql_list(values: list[str]) -> str:
    return "(" + ", ".join(_quote_jql(value) for value in values) + ")"


def _quote_jql(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return '""'
    if text.replace("_", "").replace("-", "").isalnum() and text.upper() == text:
        return text
    return '"' + text.replace('"', '\\"') + '"'


def _strip_order_by(jql: str) -> str:
    return ORDER_BY_RE.sub("", str(jql or "")).strip()


def _display(value: Any) -> Any:
    if isinstance(value, list):
        return [_display(item) for item in value]
    if isinstance(value, dict):
        for key in ("name", "value", "displayName", "key"):
            if value.get(key) is not None:
                return value[key]
        return {key: _display(item) for key, item in value.items()}
    return value


def _team_pt_display(value: Any) -> tuple[Any, Any, Any]:
    if isinstance(value, dict):
        parent = value.get("value") or value.get("name") or value.get("displayName") or value.get("key")
        child = _display(value.get("child")) if value.get("child") else None
        if child:
            return parent, child, f"{parent} / {child}" if parent else child
        return None, parent, parent
    displayed = _display(value)
    return None, displayed, displayed


def _issue_type(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return str(((fields.get("issuetype") or {}).get("name")) or "")


def _project_key(issue: dict[str, Any]) -> str | None:
    fields = issue.get("fields") or {}
    project = fields.get("project") or {}
    return project.get("key") or project.get("name")


def _parent_key_from_value(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("key", "value", "name"):
            candidate = value.get(key)
            if candidate and re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", str(candidate), re.I):
                return str(candidate).upper()
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", value, re.I):
        return value.upper()
    return None


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:10]


def _labels(issue: dict[str, Any]) -> list[str]:
    value = (issue.get("fields") or {}).get("labels") or []
    return [str(label) for label in value if str(label).strip()]


@dataclass
class ResolvedQuarter:
    name: str | None
    start: date | None
    end: date | None
    source: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "source": self.source,
            "notes": self.notes,
        }


class PortfolioHygieneService:
    """Portfolio hierarchy and quarter-hygiene capability shared by MCP, REST, and UI."""

    def __init__(self, backend: Any, today: date | None = None):
        self.backend = backend
        self.today = today or _today()

    @property
    def mode(self) -> str:
        return getattr(self.backend.settings, "mode", "recommend_only")

    def resolve_fiscal_quarter(self, quarter: str | None = None) -> ResolvedQuarter:
        calendar = getattr(self.backend.settings, "fiscal_calendar", {}) or {}
        normalized = {str(name).replace(" ", ""): (name, cfg) for name, cfg in calendar.items()}
        start_month = int(getattr(self.backend.settings, "fiscal_year_start_month", 8) or 8)
        start_day = int(getattr(self.backend.settings, "fiscal_year_start_day", 1) or 1)
        if quarter:
            key = str(quarter).replace(" ", "")
            match = normalized.get(key)
            if not match:
                inferred = self._quarter_from_name(quarter, start_month, start_day)
                if inferred:
                    return inferred
                return ResolvedQuarter(quarter, None, None, "override", [f"Fiscal quarter {quarter} is not configured."])
            name, cfg = match
            return ResolvedQuarter(str(name), cfg.start, cfg.end, "override", [])
        for name, cfg in calendar.items():
            if cfg.start <= self.today <= cfg.end:
                return ResolvedQuarter(str(name), cfg.start, cfg.end, "calendar", [])
        return self._quarter_from_date(start_month, start_day)

    def _quarter_from_date(self, start_month: int, start_day: int) -> ResolvedQuarter:
        fiscal_start = date(self.today.year, start_month, min(start_day, monthrange(self.today.year, start_month)[1]))
        if self.today < fiscal_start:
            fiscal_start = date(self.today.year - 1, start_month, min(start_day, monthrange(self.today.year - 1, start_month)[1]))
        months_elapsed = (self.today.year - fiscal_start.year) * 12 + self.today.month - fiscal_start.month
        if self.today.day < fiscal_start.day:
            months_elapsed -= 1
        quarter_index = max(0, min(3, months_elapsed // 3))
        quarter_start = _add_months(fiscal_start, quarter_index * 3)
        quarter_end = _add_months(quarter_start, 3) - timedelta(days=1)
        fiscal_year = fiscal_start.year + 1
        label = f"FY{str(fiscal_year)[-2:]}Q{quarter_index + 1}"
        return ResolvedQuarter(label, quarter_start, quarter_end, "fiscal_year_start", [])

    def _quarter_from_name(self, quarter: str, start_month: int, start_day: int) -> ResolvedQuarter | None:
        match = re.fullmatch(r"\s*FY(\d{2,4})\s*Q([1-4])\s*", str(quarter), re.I)
        if not match:
            return None
        year = int(match.group(1))
        fiscal_year = 2000 + year if year < 100 else year
        quarter_index = int(match.group(2)) - 1
        start_year = fiscal_year - 1
        fiscal_start = date(start_year, start_month, min(start_day, monthrange(start_year, start_month)[1]))
        quarter_start = _add_months(fiscal_start, quarter_index * 3)
        quarter_end = _add_months(quarter_start, 3) - timedelta(days=1)
        return ResolvedQuarter(f"FY{str(fiscal_year)[-2:]}Q{quarter_index + 1}", quarter_start, quarter_end, "fiscal_year_start_override", [])

    def context(self, instance: str = "onprem", quarter: str | None = None) -> dict[str, Any]:
        try:
            instance_cfg = self.backend.settings.jira_instances().get(instance)
        except Exception:
            instance_cfg = None
        return {
            "instance": instance,
            "fiscal_quarter": self.resolve_fiscal_quarter(quarter).to_dict(),
            "team_options": list(getattr(self.backend.settings, "portfolio_team_options", []) or []),
            "pt_options": list(getattr(self.backend.settings, "portfolio_pt_options", []) or []),
            "field_names": {
                "team": getattr(instance_cfg, "team_field_name", "Team"),
                "pt": getattr(instance_cfg, "team_pt_field_name", "Team/PT"),
                "team_pt": getattr(instance_cfg, "team_pt_field_name", "Team/PT"),
            },
        }

    def _scope_jql(
        self,
        jira: Any,
        *,
        project: str | None = None,
        team: str | None = None,
        pt: str | None = None,
        saved_view: str | None = None,
    ) -> tuple[str | None, list[str]]:
        notes: list[str] = []
        cfg = jira.cfg
        clauses: list[str] = []
        if saved_view:
            view = self.backend.get_saved_view(saved_view)["view"]
            clauses.append(f"({_strip_order_by(view['jql'])})")
        else:
            selected_project = project or jira.cfg.default_project
            if not selected_project:
                return None, ["Portfolio Hygiene requires a saved view, project, or default_project to avoid unbounded searches."]
            clauses.append(f"project = {_quote_jql(selected_project)}")
        if project and saved_view:
            clauses.append(f"project = {_quote_jql(project)}")
        team_pt_field = _quote_field_name(getattr(cfg, "team_pt_field_name", "Team/PT"))
        if team:
            notes.append(f"Team {team} is scoped through the configured Team/PT field.")
        if pt:
            clauses.append(f"{team_pt_field} = {_quote_jql(pt)}")
        elif team:
            pt_options = list(getattr(self.backend.settings, "portfolio_pt_options", []) or [])
            if pt_options:
                clauses.append(f"{team_pt_field} in {_quote_jql_list(pt_options)}")
            else:
                notes.append("No PT options are configured, so Team scope did not narrow Jira results.")
        return " AND ".join(clauses) + " ORDER BY updated DESC", notes

    def _resolve_fields(self, jira: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
        cfg = jira.cfg
        requested = {
            "target_quarter": cfg.quarter_field_name,
            "team_pt": getattr(cfg, "team_pt_field_name", "Team/PT"),
            "start_date": getattr(cfg, "start_date_field_name", "Start date"),
            "end_date": getattr(cfg, "end_date_field_name", "End date"),
        }
        resolved: dict[str, dict[str, Any]] = {}
        notes: list[str] = []
        for key, name in requested.items():
            try:
                resolved[key] = {"name": name, **resolve_field(jira, name)}
            except Exception as exc:
                notes.append(f"{name} could not be resolved: {exc}")
        hierarchy_names = list(getattr(cfg, "hierarchy_field_names", []) or [])
        hierarchy_fields = []
        for name in hierarchy_names:
            try:
                hierarchy_fields.append({"name": name, **resolve_field(jira, name)})
            except Exception:
                continue
        resolved["hierarchy"] = {"fields": hierarchy_fields}
        return resolved, notes

    def _search_fields(self, resolved: dict[str, dict[str, Any]]) -> list[str]:
        fields = ["summary", "issuetype", "project", "parent", "labels", "assignee", "status"]
        for key in ("target_quarter", "team_pt", "start_date", "end_date"):
            if resolved.get(key, {}).get("id"):
                fields.append(resolved[key]["id"])
        for field in resolved.get("hierarchy", {}).get("fields", []):
            fields.append(field["id"])
        return list(dict.fromkeys(fields))

    def _parent_key(self, issue: dict[str, Any], resolved: dict[str, dict[str, Any]]) -> str | None:
        fields = issue.get("fields") or {}
        parent = _parent_key_from_value(fields.get("parent"))
        if parent:
            return parent
        for field in resolved.get("hierarchy", {}).get("fields", []):
            parent = _parent_key_from_value(fields.get(field["id"]))
            if parent:
                return parent
        return None

    def _field_value(self, issue: dict[str, Any], resolved: dict[str, dict[str, Any]], key: str) -> Any:
        field_id = resolved.get(key, {}).get("id")
        if not field_id:
            return None
        return _display((issue.get("fields") or {}).get(field_id))

    def _issue_public(self, issue: dict[str, Any], resolved: dict[str, dict[str, Any]]) -> dict[str, Any]:
        fields = issue.get("fields") or {}
        team_pt_id = resolved.get("team_pt", {}).get("id")
        team, pt, team_pt = _team_pt_display(fields.get(team_pt_id)) if team_pt_id else (None, None, None)
        return {
            "issue_key": issue.get("key"),
            "issue_type": _issue_type(issue),
            "summary": fields.get("summary"),
            "project": _project_key(issue),
            "team": team,
            "pt": pt,
            "team_pt": team_pt,
            "target_quarter": self._field_value(issue, resolved, "target_quarter"),
        }

    def _ancestry(self, jira: Any, issue: dict[str, Any], resolved: dict[str, dict[str, Any]], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
        path = []
        seen: set[str] = set()
        current = issue
        while current:
            key = str(current.get("key"))
            path.append(self._issue_public(current, resolved))
            if key in seen:
                return {"valid": False, "problem": "cycle", "path": path}
            seen.add(key)
            if _issue_type(current).casefold() == INITIATIVE_TYPE:
                return {"valid": True, "problem": None, "path": path}
            parent_key = self._parent_key(current, resolved)
            if not parent_key:
                problem = "missing_parent" if len(path) == 1 else "terminates_without_initiative"
                return {"valid": False, "problem": problem, "path": path}
            if parent_key in cache:
                current = cache[parent_key]
                continue
            try:
                parent = jira.get_issue(parent_key, self._search_fields(resolved))
            except Exception as exc:
                path.append({"issue_key": parent_key, "problem": str(exc)})
                return {"valid": False, "problem": "broken_parent_chain", "path": path}
            cache[parent_key] = parent
            current = parent
        return {"valid": False, "problem": "broken_parent_chain", "path": path}

    def _hierarchy_finding(self, issue: dict[str, Any], ancestry: dict[str, Any]) -> dict[str, Any]:
        public = ancestry["path"][0] if ancestry.get("path") else {"issue_key": issue.get("key")}
        problem = ancestry.get("problem") or "invalid_ancestry"
        labels = {
            "missing_parent": "Missing parent",
            "terminates_without_initiative": "Ancestry terminates before Initiative",
            "broken_parent_chain": "Broken parent chain",
            "cycle": "Hierarchy cycle",
        }
        return {
            "id": f"{issue.get('key')}:hierarchy:{problem}",
            **public,
            "category": "hierarchy",
            "problem": labels.get(problem, "Invalid Initiative ancestry"),
            "current_value": " > ".join(row.get("issue_key", "") for row in ancestry.get("path", [])),
            "expected_value": "Ancestor chain reaches Initiative",
            "auto_fixable": False,
            "status": "MANUAL_REVIEW",
            "ancestry_path": ancestry.get("path", []),
            "candidate_parents": [],
            "recommended_action": "Select a valid parent or repair the broken hierarchy in Jira after review.",
        }

    def _date_findings(
        self,
        issue: dict[str, Any],
        resolved: dict[str, dict[str, Any]],
        quarter: ResolvedQuarter,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not quarter.start or not quarter.end:
            return [], []
        public = self._issue_public(issue, resolved)
        findings = []
        changes = []
        checks = [
            ("start_date", quarter.start.isoformat()),
            ("end_date", quarter.end.isoformat()),
        ]
        for key, expected in checks:
            field = resolved.get(key)
            if not field:
                continue
            current = _date_text(self._field_value(issue, resolved, key))
            if current == expected:
                continue
            problem = "Missing quarter date" if not current else "Incorrect quarter date"
            finding = {
                "id": f"{issue.get('key')}:dates:{key}",
                **public,
                "category": "dates",
                "field": field["name"],
                "problem": problem,
                "current_value": current,
                "expected_value": expected,
                "auto_fixable": True,
                "status": "AUTO_FIXABLE",
                "ancestry_path": [],
                "recommended_action": f"Set {field['name']} to {expected}.",
            }
            findings.append(finding)
            changes.append({
                "change_id": finding["id"],
                "category": "dates",
                "issue_key": issue.get("key"),
                "field": field["name"],
                "current_value": current,
                "proposed_value": expected,
                "safe_apply": True,
            })
        return findings, changes

    def _label_finding(
        self,
        issue: dict[str, Any],
        resolved: dict[str, dict[str, Any]],
        ancestry_path: list[dict[str, Any]],
        canonical_label: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        labels = _labels(issue)
        qp_labels = [label for label in labels if QP_LABEL_RE.match(label)]
        remove_labels = [label for label in qp_labels if label != canonical_label]
        add_labels = [] if canonical_label in qp_labels else [canonical_label]
        if len(qp_labels) == 1 and qp_labels[0] == canonical_label:
            return None, None
        unrelated = [label for label in labels if not QP_LABEL_RE.match(label)]
        proposed = sorted(dict.fromkeys([*unrelated, canonical_label]))
        if not qp_labels:
            problem = "Missing quarter commitment label"
        elif len(qp_labels) > 1:
            problem = "Multiple quarter commitment labels"
        else:
            problem = "Wrong-quarter commitment label"
        public = self._issue_public(issue, resolved)
        finding = {
            "id": f"{issue.get('key')}:labels:commitment",
            **public,
            "category": "labels",
            "problem": problem,
            "current_value": labels,
            "expected_value": canonical_label,
            "auto_fixable": True,
            "status": "AUTO_FIXABLE",
            "ancestry_path": ancestry_path,
            "recommended_action": f"Ensure exactly one QP commitment label: {canonical_label}.",
        }
        change = {
            "change_id": finding["id"],
            "category": "labels",
            "issue_key": issue.get("key"),
            "current_value": labels,
            "proposed_value": proposed,
            "add_labels": add_labels,
            "remove_labels": remove_labels,
            "safe_apply": True,
        }
        return finding, change

    def review(
        self,
        *,
        instance: str = "onprem",
        quarter: str | None = None,
        project: str | None = None,
        team: str | None = None,
        pt: str | None = None,
        saved_view: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        jira = self.backend.client(instance)
        cfg = jira.cfg
        if cfg.instance_type == "cloud":
            return {
                "instance": instance,
                "mode": self.mode,
                "fiscal_quarter": self.resolve_fiscal_quarter(quarter).to_dict(),
                "scope": {"project": project, "team": team, "pt": pt, "saved_view": saved_view, "limit": limit},
                "total_checked": 0,
                "initiative_ancestry_valid_count": 0,
                "missing_parent_count": 0,
                "invalid_ancestry_count": 0,
                "date_violations": {"total": 0, "missing": 0, "incorrect": 0},
                "label_violations": {"total": 0, "missing": 0, "wrong_quarter": 0, "multiple": 0},
                "auto_fixable_count": 0,
                "manual_review_count": 0,
                "findings": [],
                "proposed_changes": [],
                "confidence": {"score": 0.0, "level": "low"},
                "data_quality_notes": ["Portfolio Hygiene currently applies only to Jira Data Center/Server instances."],
            }
        fiscal = self.resolve_fiscal_quarter(quarter)
        resolved, notes = self._resolve_fields(jira)
        jql, scope_notes = self._scope_jql(jira, project=project, team=team, pt=pt, saved_view=saved_view)
        notes.extend(scope_notes)
        if not jql:
            return {
                "instance": instance,
                "mode": self.mode,
                "fiscal_quarter": fiscal.to_dict(),
                "scope": {"project": project, "team": team, "pt": pt, "saved_view": saved_view, "jql": None},
                "total_checked": 0,
                "initiative_ancestry_valid_count": 0,
                "missing_parent_count": 0,
                "invalid_ancestry_count": 0,
                "date_violations": {"total": 0, "missing": 0, "incorrect": 0},
                "label_violations": {"total": 0, "missing": 0, "wrong_quarter": 0, "multiple": 0},
                "auto_fixable_count": 0,
                "manual_review_count": 0,
                "findings": [],
                "proposed_changes": [],
                "confidence": {"score": 0.3, "level": "low"},
                "data_quality_notes": [*fiscal.notes, *notes],
            }
        fields = self._search_fields(resolved)
        issues = jira.search(jql, fields, min(max(1, int(limit)), self.backend.settings.max_search_results))
        cache = {issue["key"]: issue for issue in issues if issue.get("key")}
        findings: list[dict[str, Any]] = []
        proposed_changes: list[dict[str, Any]] = []
        ancestry_valid = 0
        missing_parent = 0
        invalid_ancestry = 0
        missing_dates = 0
        incorrect_dates = 0
        missing_labels = 0
        wrong_labels = 0
        multiple_labels = 0
        canonical_label = f"QP-{fiscal.name}-committed" if fiscal.name else None

        for issue in issues:
            ancestry = self._ancestry(jira, issue, resolved, cache)
            if ancestry["valid"]:
                ancestry_valid += 1
            else:
                problem = ancestry.get("problem")
                if problem == "missing_parent":
                    missing_parent += 1
                invalid_ancestry += 1
                findings.append(self._hierarchy_finding(issue, ancestry))

            issue_type = _issue_type(issue).casefold()
            issue_quarter = str(self._field_value(issue, resolved, "target_quarter") or "").replace(" ", "")
            current_quarter = str(fiscal.name or "").replace(" ", "")
            if issue_type in PORTFOLIO_TYPES and current_quarter and issue_quarter == current_quarter:
                date_findings, date_changes = self._date_findings(issue, resolved, fiscal)
                for finding in date_findings:
                    if finding["problem"].startswith("Missing"):
                        missing_dates += 1
                    else:
                        incorrect_dates += 1
                findings.extend(date_findings)
                proposed_changes.extend(date_changes)

            if canonical_label and issue_type in STORY_TYPES and ancestry["valid"]:
                current_quarter_ancestor = any(
                    str(row.get("issue_type") or "").casefold() in PORTFOLIO_TYPES
                    and str(row.get("target_quarter") or "").replace(" ", "") == current_quarter
                    for row in ancestry.get("path", [])[1:]
                )
                if current_quarter_ancestor:
                    finding, change = self._label_finding(issue, resolved, ancestry.get("path", []), canonical_label)
                    if finding and change:
                        if finding["problem"].startswith("Missing"):
                            missing_labels += 1
                        elif finding["problem"].startswith("Multiple"):
                            multiple_labels += 1
                        else:
                            wrong_labels += 1
                        findings.append(finding)
                        proposed_changes.append(change)

        auto_fixable = [finding for finding in findings if finding.get("auto_fixable")]
        manual_review = [finding for finding in findings if not finding.get("auto_fixable")]
        score = 0.85 if resolved.get("target_quarter") and not fiscal.notes else 0.55
        result = {
            "instance": instance,
            "mode": self.mode,
            "fiscal_quarter": fiscal.to_dict(),
            "scope": {
                "project": project or getattr(cfg, "default_project", None),
                "team": team,
                "pt": pt,
                "saved_view": saved_view,
                "jql": jql,
                "limit": limit,
            },
            "total_checked": len(issues),
            "initiative_ancestry_valid_count": ancestry_valid,
            "missing_parent_count": missing_parent,
            "invalid_ancestry_count": invalid_ancestry,
            "date_violations": {
                "total": missing_dates + incorrect_dates,
                "missing": missing_dates,
                "incorrect": incorrect_dates,
            },
            "label_violations": {
                "total": missing_labels + wrong_labels + multiple_labels,
                "missing": missing_labels,
                "wrong_quarter": wrong_labels,
                "multiple": multiple_labels,
            },
            "auto_fixable_count": len(auto_fixable),
            "manual_review_count": len(manual_review),
            "findings": findings,
            "proposed_changes": proposed_changes,
            "confidence": {
                "score": score,
                "level": "high" if score >= 0.8 else "medium",
            },
            "data_quality_notes": [*fiscal.notes, *notes],
        }
        result["review_id"] = _hash_payload({key: value for key, value in result.items() if key != "review_id"})
        return result

    def _changes_from_findings(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        changes = []
        for finding in findings:
            if not finding.get("auto_fixable"):
                continue
            if finding.get("category") == "dates":
                changes.append({
                    "change_id": finding["id"],
                    "category": "dates",
                    "issue_key": finding["issue_key"],
                    "field": finding["field"],
                    "current_value": finding.get("current_value"),
                    "proposed_value": finding.get("expected_value"),
                    "safe_apply": True,
                })
            elif finding.get("category") == "labels":
                current = [str(label) for label in finding.get("current_value") or []]
                expected = str(finding.get("expected_value"))
                changes.append({
                    "change_id": finding["id"],
                    "category": "labels",
                    "issue_key": finding["issue_key"],
                    "current_value": current,
                    "proposed_value": sorted(dict.fromkeys([label for label in current if not QP_LABEL_RE.match(label)] + [expected])),
                    "add_labels": [] if expected in current else [expected],
                    "remove_labels": [label for label in current if QP_LABEL_RE.match(label) and label != expected],
                    "safe_apply": True,
                })
        return changes

    def preview_fix(
        self,
        *,
        instance: str = "onprem",
        quarter: str | None = None,
        project: str | None = None,
        team: str | None = None,
        pt: str | None = None,
        saved_view: str | None = None,
        limit: int = 500,
        findings: list[dict[str, Any]] | None = None,
        proposed_changes: list[dict[str, Any]] | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        if proposed_changes is None:
            if findings is not None:
                proposed_changes = self._changes_from_findings(findings)
                review = {"findings": findings, "data_quality_notes": []}
            else:
                review = self.review(instance=instance, quarter=quarter, project=project, team=team, pt=pt, saved_view=saved_view, limit=limit)
                proposed_changes = review.get("proposed_changes") or []
                findings = review.get("findings") or []
        else:
            review = {"findings": findings or [], "data_quality_notes": []}
        allowed = {str(category) for category in categories or []}
        changes = [change for change in proposed_changes if not allowed or change.get("category") in allowed]
        manual_exclusions = [
            finding for finding in review.get("findings", [])
            if not finding.get("auto_fixable") and (not allowed or finding.get("category") in allowed)
        ]
        preview = {
            "mode": self.mode,
            "instance": instance,
            "categories": sorted(allowed),
            "change_count": len(changes),
            "changes": changes,
            "manual_review_exclusions": manual_exclusions,
            "data_quality_notes": review.get("data_quality_notes", []),
            "can_apply": self.mode == "safe_apply" and bool(changes),
        }
        preview["preview_id"] = _hash_payload({key: value for key, value in preview.items() if key != "preview_id"})
        record = self.backend.execution_store.add_preview(
            "portfolio_hygiene_fix",
            instance,
            {
                "instance": instance,
                "quarter": quarter,
                "project": project,
                "team": team,
                "pt": pt,
                "saved_view": saved_view,
                "limit": limit,
                "categories": categories or [],
            },
            preview,
        )
        self.backend.audit_trail.record(
            "portfolio_hygiene_preview_created",
            target=instance,
            outcome="previewed",
            details={"preview_id": record["preview_id"], "changes": len(changes)},
        )
        return record

    def _apply_date_change(self, jira: Any, change: dict[str, Any]) -> dict[str, Any]:
        field = resolve_field(jira, change["field"])
        issue = jira.get_issue(change["issue_key"], [field["id"]])
        current = _date_text((issue.get("fields") or {}).get(field["id"]))
        if current != change.get("current_value"):
            return {
                "issue_key": change["issue_key"],
                "change_id": change["change_id"],
                "ok": False,
                "reason": "source issue changed since preview",
            }
        jira.update_issue(change["issue_key"], {field["id"]: change["proposed_value"]})
        return {"issue_key": change["issue_key"], "change_id": change["change_id"], "ok": True}

    def _apply_label_change(self, jira: Any, change: dict[str, Any]) -> dict[str, Any]:
        issue = jira.get_issue(change["issue_key"], ["labels"])
        current = _labels(issue)
        preview_qp = sorted(label for label in change.get("current_value") or [] if QP_LABEL_RE.match(label))
        current_qp = sorted(label for label in current if QP_LABEL_RE.match(label))
        if current_qp != preview_qp:
            return {
                "issue_key": change["issue_key"],
                "change_id": change["change_id"],
                "ok": False,
                "reason": "source issue labels changed since preview",
            }
        operations = []
        for label in change.get("remove_labels") or []:
            if label in current:
                operations.append({"remove": label})
        for label in change.get("add_labels") or []:
            if label not in current:
                operations.append({"add": label})
        if operations:
            jira.update_issue_operations(change["issue_key"], {"labels": operations})
        return {"issue_key": change["issue_key"], "change_id": change["change_id"], "ok": True}

    def apply(self, preview_id: str, *, allow_parent_changes: bool = False) -> dict[str, Any]:
        record = self.backend.execution_store.get_record(preview_id).to_dict()
        if record["action"] != "portfolio_hygiene_fix":
            return {"applied": False, "preview_id": preview_id, "reason": "preview_id does not reference a Portfolio Hygiene preview"}
        preview = record["preview"]
        instance = record["instance"]
        if self.mode != "safe_apply":
            result = {"applied": False, "preview_id": preview_id, "reason": "MODE must be safe_apply"}
            self.backend.execution_store.mark_applied(preview_id, result)
            return result
        jira = self.backend.client(instance)
        results = []
        for change in preview.get("changes") or []:
            try:
                if change.get("category") == "dates":
                    results.append(self._apply_date_change(jira, change))
                elif change.get("category") == "labels":
                    results.append(self._apply_label_change(jira, change))
                elif change.get("category") == "hierarchy":
                    results.append({
                        "issue_key": change.get("issue_key"),
                        "change_id": change.get("change_id"),
                        "ok": False,
                        "reason": "parent changes require explicit approved destructive review" if not allow_parent_changes else "no unambiguous parent change available",
                    })
                else:
                    results.append({
                        "issue_key": change.get("issue_key"),
                        "change_id": change.get("change_id"),
                        "ok": False,
                        "reason": "unsupported change category",
                    })
            except Exception as exc:
                results.append({
                    "issue_key": change.get("issue_key"),
                    "change_id": change.get("change_id"),
                    "ok": False,
                    "error": str(exc),
                })
        result = {
            "applied": bool(results) and all(row.get("ok") for row in results),
            "preview_id": preview_id,
            "results": results,
        }
        self.backend.execution_store.mark_applied(preview_id, result)
        self.backend.audit_trail.record(
            "portfolio_hygiene_apply",
            target=instance,
            outcome="succeeded" if result["applied"] else "failed",
            details={"preview_id": preview_id, "results": len(results)},
        )
        return result
