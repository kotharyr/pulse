from datetime import date
from types import SimpleNamespace

from engineering_ops.config import FiscalQuarterConfig
from engineering_ops.services.executions import ExecutionHistory
from engineering_ops.services.audit import AuditTrail
from engineering_ops.services.portfolio_hygiene import PortfolioHygieneService


class FakePortfolioJira:
    name = "onprem"

    def __init__(self):
        self.cfg = SimpleNamespace(
            instance_type="datacenter",
            kind="datacenter",
            default_project="ENG",
            quarter_field_name="Target Quarter",
            team_field_name="Team",
            pt_field_name="PT",
            team_pt_field_name="Team/PT",
            start_date_field_name="Start date",
            end_date_field_name="End date",
            hierarchy_field_names=["Parent Link"],
        )
        self.updated_fields = []
        self.updated_operations = []
        self.issues = {
            "INIT-1": self.issue("INIT-1", "Initiative", parent=None, quarter="FY27Q1"),
            "PF-1": self.issue("PF-1", "Portfolio Feature", parent="INIT-1", quarter="FY27Q1", start=None, end="2026-10-01"),
            "EPIC-1": self.issue("EPIC-1", "Epic", parent="PF-1", quarter="FY27Q1", start="2026-08-01", end="2026-10-31"),
            "US-1": self.issue("US-1", "User Story", parent="EPIC-1", labels=["team-a"]),
            "US-2": self.issue("US-2", "User Story", parent="EPIC-1", labels=["QP-FY26Q4-committed", "keep"]),
            "BUG-1": self.issue("BUG-1", "Bug", parent=None),
            "CYCLE-1": self.issue("CYCLE-1", "User Story", parent="CYCLE-2"),
            "CYCLE-2": self.issue("CYCLE-2", "Epic", parent="CYCLE-1", quarter="FY27Q1"),
        }

    def issue(self, key, issue_type, *, parent=None, quarter=None, start=None, end=None, labels=None):
        fields = {
            "summary": f"{key} summary",
            "issuetype": {"name": issue_type},
            "project": {"key": "ENG"},
            "labels": labels or [],
            "status": {"name": "To Do"},
            "customfield_15": {"value": "Platform Excellence", "child": {"value": "Muon"}},
        }
        if parent:
            fields["parent"] = {"key": parent}
        if quarter is not None:
            fields["customfield_10"] = {"value": quarter}
        if start is not None:
            fields["customfield_11"] = start
        if end is not None:
            fields["customfield_12"] = end
        return {"key": key, "fields": fields}

    def fields(self):
        return [
            {"id": "customfield_10", "name": "Target Quarter", "custom": True},
            {"id": "customfield_11", "name": "Start date", "custom": True},
            {"id": "customfield_12", "name": "End date", "custom": True},
            {"id": "customfield_13", "name": "Parent Link", "custom": True},
            {"id": "customfield_14", "name": "Team", "custom": True},
            {"id": "customfield_15", "name": "Team/PT", "custom": True},
        ]

    def search(self, jql, fields, limit):
        self.last_search = (jql, fields, limit)
        keys = ["PF-1", "EPIC-1", "US-1", "US-2", "BUG-1", "CYCLE-1", "CYCLE-2"]
        return [self.issues[key] for key in keys][:limit]

    def get_issue(self, key, fields=None):
        return self.issues[key]

    def update_issue(self, issue_key, fields):
        self.updated_fields.append((issue_key, fields))
        self.issues[issue_key]["fields"].update(fields)

    def update_issue_operations(self, issue_key, update):
        self.updated_operations.append((issue_key, update))
        labels = self.issues[issue_key]["fields"].setdefault("labels", [])
        for operation in update["labels"]:
            if "remove" in operation and operation["remove"] in labels:
                labels.remove(operation["remove"])
            if "add" in operation and operation["add"] not in labels:
                labels.append(operation["add"])


class FakePortfolioBackend:
    def __init__(self, jira, mode="recommend_only"):
        self.jira = jira
        self.settings = SimpleNamespace(
            mode=mode,
            fiscal_calendar={
                "FY27Q1": FiscalQuarterConfig(start=date(2026, 8, 1), end=date(2026, 10, 31)),
                "FY27Q2": FiscalQuarterConfig(start=date(2026, 11, 1), end=date(2027, 1, 31)),
            },
            max_search_results=5000,
            fiscal_year_start_month=8,
            fiscal_year_start_day=1,
            portfolio_team_options=["Platform Excellence"],
            portfolio_pt_options=["Muon", "Atlas", "Phoenix", "Dragon"],
        )
        self.execution_store = ExecutionHistory()
        self.audit_trail = AuditTrail()

    def client(self, instance):
        assert instance == "onprem"
        return self.jira

    def get_saved_view(self, name):
        return {"view": {"name": name, "jql": "project = ENG AND labels = portfolio"}}


def test_portfolio_hygiene_review_detects_hierarchy_dates_and_labels():
    backend = FakePortfolioBackend(FakePortfolioJira())
    result = PortfolioHygieneService(backend, today=date(2026, 8, 18)).review(instance="onprem", limit=20)

    assert result["fiscal_quarter"]["name"] == "FY27Q1"
    assert result["total_checked"] == 7
    assert result["initiative_ancestry_valid_count"] == 4
    assert result["missing_parent_count"] == 1
    assert result["invalid_ancestry_count"] == 3
    assert result["date_violations"] == {"total": 4, "missing": 3, "incorrect": 1}
    assert result["label_violations"] == {"total": 2, "missing": 1, "wrong_quarter": 1, "multiple": 0}
    assert result["auto_fixable_count"] == 6
    assert result["manual_review_count"] == 3
    assert "customfield_" not in repr(result)
    assert result["scope"]["jql"] == "project = ENG ORDER BY updated DESC"
    label_finding = next(finding for finding in result["findings"] if finding["category"] == "labels")
    assert label_finding["team"] == "Platform Excellence"
    assert label_finding["pt"] == "Muon"
    assert label_finding["team_pt"] == "Platform Excellence / Muon"


def test_portfolio_hygiene_autopopulates_current_quarter_without_calendar():
    backend = FakePortfolioBackend(FakePortfolioJira())
    backend.settings.fiscal_calendar = {}

    result = PortfolioHygieneService(backend, today=date(2026, 8, 19)).context("onprem")

    assert result["fiscal_quarter"] == {
        "name": "FY27Q1",
        "start": "2026-08-01",
        "end": "2026-10-31",
        "source": "fiscal_year_start",
        "notes": [],
    }
    assert result["team_options"] == ["Platform Excellence"]
    assert result["pt_options"] == ["Muon", "Atlas", "Phoenix", "Dragon"]


def test_portfolio_hygiene_scopes_by_team_pt_fields_not_component():
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira)

    PortfolioHygieneService(backend, today=date(2026, 8, 18)).review(
        instance="onprem",
        team="Platform Excellence",
        pt="Muon",
        limit=1,
    )

    assert '"Team/PT" = "Muon"' in jira.last_search[0]
    assert "component" not in jira.last_search[0].casefold()


def test_portfolio_hygiene_team_all_pts_uses_configured_tuple_options():
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira)

    PortfolioHygieneService(backend, today=date(2026, 8, 18)).review(
        instance="onprem",
        team="Platform Excellence",
        limit=1,
    )

    assert '"Team/PT" in ("Muon", "Atlas", "Phoenix", "Dragon")' in jira.last_search[0]
    assert "component" not in jira.last_search[0].casefold()


def test_portfolio_hygiene_preview_is_stored_and_blocked_by_default():
    backend = FakePortfolioBackend(FakePortfolioJira(), mode="recommend_only")
    record = PortfolioHygieneService(backend, today=date(2026, 8, 18)).preview_fix(instance="onprem", categories=["dates", "labels"])

    assert record["action"] == "portfolio_hygiene_fix"
    assert record["status"] == "previewed"
    assert record["preview"]["change_count"] == 6
    assert record["preview"]["can_apply"] is False
    assert record["preview"]["manual_review_exclusions"] == []


def test_portfolio_hygiene_apply_requires_safe_apply_and_does_not_write():
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira, mode="recommend_only")
    service = PortfolioHygieneService(backend, today=date(2026, 8, 18))
    record = service.preview_fix(instance="onprem")

    result = service.apply(record["preview_id"])

    assert result["applied"] is False
    assert result["reason"] == "MODE must be safe_apply"
    assert jira.updated_fields == []
    assert jira.updated_operations == []


def test_portfolio_hygiene_apply_uses_label_operations_and_preserves_unrelated_labels():
    jira = FakePortfolioJira()
    backend = FakePortfolioBackend(jira, mode="safe_apply")
    service = PortfolioHygieneService(backend, today=date(2026, 8, 18))
    record = service.preview_fix(instance="onprem", categories=["labels"])

    result = service.apply(record["preview_id"])

    assert result["applied"] is True
    assert jira.updated_fields == []
    assert ("US-2", {"labels": [{"remove": "QP-FY26Q4-committed"}, {"add": "QP-FY27Q1-committed"}]}) in jira.updated_operations
    assert sorted(jira.issues["US-2"]["fields"]["labels"]) == ["QP-FY27Q1-committed", "keep"]
