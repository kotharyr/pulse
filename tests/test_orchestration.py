from types import SimpleNamespace

from engineering_ops.models import Confidence, Finding, Metric, Recommendation, Risk, SourceCoverage
from engineering_ops.services.orchestration import EngineeringOrchestrator


class FakeOrchestrationBackend:
    settings = SimpleNamespace(mode="recommend_only")

    def __init__(self):
        self.calls = []
        self.applied = False

    def list_jira_instances(self):
        return {"instances": [{"name": "cloud", "kind": "cloud", "default_project": "ENG"}]}

    def discover_console_sprints(self, instance, project=None):
        self.calls.append(("discover_sprints", instance, project))
        return {
            "current_sprint": {"id": 12, "name": "Sprint 12"},
            "next_sprint": {"id": 13, "name": "Sprint 13"},
            "selection": {"next_strategy": "number"},
        }

    def discover_environment(self, instance, project=None, include_internal_ids=False):
        self.calls.append(("environment", instance, project, include_internal_ids))
        return {
            "target_quarter_values": ["FY27 Q2"],
            "sprints": [
                {"id": 12, "name": "Sprint 12", "state": "active"},
                {"id": 13, "name": "Sprint 13", "state": "future"},
            ],
        }

    def analyze_current_sprint(self, instance, sprint_id, next_sprint_id=None):
        self.calls.append(("sprint_analysis", instance, sprint_id, next_sprint_id))
        return {
            "sprint": {"id": sprint_id, "name": "Sprint 12"},
            "next_sprint": {"id": next_sprint_id, "name": "Sprint 13"},
            "recent_sprint_capacity_baseline": {"average_completed_story_points": 18},
            "analysis": {
                "story_points": {"completion_percent": 50, "completed": 10, "remaining": 10, "total": 20},
                "progress_by_team": [{"name": "Platform", "story_points": 20, "done_story_points": 10}],
                "progress_by_engineer": [{"name": "Ada", "story_points": 8, "done_story_points": 3}],
                "blocked_work": [{"issue_key": "ENG-2", "summary": "Blocked", "assignee": "Ada", "status": "Blocked"}],
                "rollover_candidates": [{"issue_key": "ENG-3", "summary": "Rollover", "assignee": "Ben", "status": "In Progress"}],
                "issue_split_proposals": [{"source_issue_key": "ENG-4", "new_summary": "Follow-on"}],
                "projected_next_sprint_load": {"projected_story_points": 30},
                "next_sprint_capacity": {"story_points": 20},
                "overcommit": {"overcommitted": True, "overcommit_percentage": 50},
            },
            "issues": [
                {"key": "ENG-1", "fields": {"summary": "Done", "status": {"name": "Done"}}},
                {"key": "ENG-2", "fields": {"summary": "Blocked", "status": {"name": "Blocked"}}},
            ],
        }

    def create_execution_preview(self, action, parameters):
        self.calls.append(("preview", action, parameters))
        return {
            "preview_id": "preview-1",
            "action": action,
            "status": "previewed",
            "preview": {
                "preview_id": "preview-1",
                "can_apply": False,
                "current_incomplete_issue_keys": ["ENG-2"],
                "move_issue_keys": ["ENG-2"],
                "split_plans": [],
                "warnings": ["NEXT SPRINT IS PROJECTED TO BE OVERCOMMITTED"],
                "next_sprint_capacity": {"overcommitted": True, "overcommit_percentage": 50},
            },
        }

    def apply_execution_preview(self, preview_id):
        self.calls.append(("apply", preview_id))
        return {
            "preview_id": preview_id,
            "status": "failed",
            "error": "preview_id does not match the current plan",
            "result": {"applied": False, "reason": "preview_id does not match the current plan"},
        }

    def engineering_health(self, instance, jql, stale_days=90, limit=100):
        self.calls.append(("health", instance, jql, stale_days, limit))
        return {
            "issue_count": 3,
            "stale_issue_keys": ["ENG-5"],
            "blocked_issue_keys": ["ENG-2"],
            "unassigned_issue_keys": ["ENG-6"],
            "domain_counts": {"domain-platform": 2},
        }

    def search_issues_page(self, instance, jql, page=1, page_size=25):
        self.calls.append(("search", instance, jql, page, page_size))
        return {
            "issues": [
                {"key": "ENG-5", "fields": {"summary": "Old work", "status": {"name": "To Do"}, "assignee": None}},
                {"key": "ENG-6", "fields": {"summary": "Fix", "status": {"name": "To Do"}, "labels": ["urgent"]}},
            ],
            "pagination": {"page": page, "count": 2},
        }

    def report_quarter_progress(self, instance, quarter, jql_extra="", limit=500):
        self.calls.append(("quarter", instance, quarter, jql_extra, limit))
        return {
            "quarter": quarter,
            "count": 2,
            "status_counts": {"Done": 1, "Blocked": 1},
            "issues": [{"key": "ENG-7", "fields": {"status": "Blocked"}}],
        }

    def analyze_security_package_updates(self, instance, project=None, limit=2000):
        self.calls.append(("security", instance, project, limit))
        return {
            "matched_tickets": 2,
            "remediation_actions": [
                {
                    "component": "openssl",
                    "required_version": "3.0.9",
                    "tickets_potentially_cleared": 2,
                    "confidence": 0.9,
                    "affected_jira_issues": ["SEC-1", "SEC-2"],
                    "cves": ["CVE-2026-0001"],
                    "repositories_requiring_upgrade": ["service-a"],
                    "already_fixed_repositories": [],
                }
            ],
            "raw_ticket_analysis": [],
            "repository_inventory": [{"name": "service-a"}],
        }

    def repository_inventory(self):
        self.calls.append(("repos",))
        return {"count": 1, "package_count": 3, "repositories": [{"name": "service-a"}]}

    def get_saved_view(self, name):
        self.calls.append(("view", name))
        return {"view": {"name": name, "instance": "cloud", "jql": "project = ENG"}}

    def search_saved_view(self, name, page=1, page_size=25):
        self.calls.append(("view_search", name, page, page_size))
        return {"results": self.search_issues_page("cloud", "project = ENG", page, page_size)}


def test_response_models_are_serializable():
    rows = [
        Finding("Finding", "Found it").to_dict(),
        Risk("Risk", "Could hurt").to_dict(),
        Recommendation("Do this", "Because").to_dict(),
        Metric("count", 3, "items").to_dict(),
        Confidence(0.8, "high", ["one caveat"]).to_dict(),
        SourceCoverage("jira", "ok").to_dict(),
    ]

    assert rows[0]["title"] == "Finding"
    assert rows[3]["unit"] == "items"
    assert rows[4]["level"] == "high"


def test_orchestration_aggregates_engineering_review_without_writes():
    fake = FakeOrchestrationBackend()
    result = EngineeringOrchestrator(fake).engineering_review(instance="cloud", project="ENG", include_sections=["sprint", "repositories", "security"])

    assert result["workflow"] == "engineering_review"
    assert result["mode"] == "recommend_only"
    assert "cloud" in result["sections"]["instances"]
    assert any(metric["name"] == "repository_count" for metric in result["metrics"])
    assert ("repos",) in fake.calls
    assert fake.applied is False


def test_missing_sprint_source_returns_risk():
    class MissingSprintBackend(FakeOrchestrationBackend):
        def discover_console_sprints(self, instance, project=None):
            raise RuntimeError("Jira sprint API unavailable")

    result = EngineeringOrchestrator(MissingSprintBackend()).sprint_analysis(instance="cloud")

    assert result["workflow"] == "sprint_analysis"
    assert result["risks"][0]["title"] == "Sprint not resolved"
    assert result["source_coverage"][0]["status"] == "failed"


def test_partial_connector_failure_is_reported():
    class PartialFailureBackend(FakeOrchestrationBackend):
        def repository_inventory(self):
            raise RuntimeError("repo root unavailable")

    result = EngineeringOrchestrator(PartialFailureBackend()).engineering_review(instance="cloud", include_sections=["repositories"])

    assert result["summary"] == "Engineering review prepared for 1 instance(s)."
    assert result["source_coverage"][0]["source"] == "repository_inventory"
    assert result["source_coverage"][0]["status"] == "failed"


def test_sprint_close_preview_stores_preview_and_does_not_apply():
    fake = FakeOrchestrationBackend()
    result = EngineeringOrchestrator(fake).sprint_close_preview(instance="cloud", sprint_id=12, next_sprint_id=13)

    assert result["execution_preview"]["preview_id"] == "preview-1"
    assert result["sections"]["proposed_rollover"] == ["ENG-2"]
    assert ("preview", "close_sprint", {
        "instance": "cloud",
        "sprint_id": 12,
        "next_sprint_id": 13,
        "move_issue_keys": None,
        "split_plans": [],
        "rollover_all_incomplete": True,
    }) in fake.calls
    assert not any(call[0] == "apply" for call in fake.calls)


def test_sprint_close_apply_detects_stale_preview():
    result = EngineeringOrchestrator(FakeOrchestrationBackend()).sprint_close_apply("preview-1")

    assert result["workflow"] == "sprint_close_apply"
    assert any(risk["title"] == "Preview is stale" for risk in result["risks"])
    assert result["sections"]["result"]["applied"] is False


def test_saved_view_review_returns_paginated_issues():
    result = EngineeringOrchestrator(FakeOrchestrationBackend()).saved_view_review("Security Exceptions", page=2, page_size=10)

    assert result["workflow"] == "saved_view_review"
    assert result["metrics"][0]["value"] == 2
    assert result["sections"]["paginated_issues"]["pagination"]["page"] == 2
