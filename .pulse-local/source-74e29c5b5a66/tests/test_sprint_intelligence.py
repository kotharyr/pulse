from engineering_ops.services.sprints import sprint_intelligence


def issue(key, status, points, assignee, components=None, labels=None):
    category = "done" if status == "Done" else "indeterminate"
    return {
        "key": key,
        "fields": {
            "summary": f"{key} summary",
            "status": {"name": status, "statusCategory": {"key": category}},
            "assignee": {"displayName": assignee},
            "components": [{"name": name} for name in components or []],
            "labels": labels or [],
            "customfield_10016": points,
        },
    }


def test_sprint_intelligence_capacity_math_and_overcommit_detection():
    current = [
        issue("ENG-1", "Done", 5, "Asha", ["Platform"]),
        issue("ENG-2", "In Progress", 8, "Asha", ["Platform"], ["blocked"]),
        issue("ENG-3", "To Do", 3, "Ben", ["Data"]),
        issue("ENG-4", "Done", 2, "Ben", [], ["team:Infra"]),
    ]
    next_issues = [issue("ENG-5", "To Do", 10, "Cara", ["Platform"])]

    report = sprint_intelligence(
        current,
        next_issues,
        "Story Points",
        "customfield_10016",
        {"story_points": 15, "issue_count": None, "source": "configured"},
    )

    assert report["completion_percent"] == 50
    assert report["story_points"] == {
        "completed": 7,
        "remaining": 11,
        "total": 18,
        "completion_percent": 38.9,
    }
    assert report["projected_next_sprint_load"]["projected_story_points"] == 21
    assert report["next_sprint_capacity"]["story_points"] == 15
    assert report["overcommit"]["overcommitted"] is True
    assert report["overcommit"]["overcommit_percentage"] == 40
    assert report["blocked_work"][0]["issue_key"] == "ENG-2"
    assert [row["source_issue_key"] for row in report["issue_split_proposals"]] == ["ENG-2", "ENG-3"]


def test_sprint_intelligence_groups_completion_by_engineer_and_team():
    current = [
        issue("ENG-1", "Done", 5, "Asha", ["Platform"]),
        issue("ENG-2", "In Progress", 8, "Asha", ["Platform"]),
        issue("ENG-3", "To Do", 3, "Ben", ["Data"]),
        issue("ENG-4", "Done", 2, "Ben", [], ["team:Infra"]),
    ]

    report = sprint_intelligence(
        current,
        [],
        "Story Points",
        "customfield_10016",
        {"story_points": 30, "issue_count": None, "source": "configured"},
    )

    engineers = {row["name"]: row for row in report["progress_by_engineer"]}
    assert engineers["Asha"]["story_points"] == 13
    assert engineers["Asha"]["done_story_points"] == 5
    assert engineers["Ben"]["remaining_story_points"] == 3

    teams = {row["name"]: row for row in report["progress_by_team"]}
    assert teams["Platform"]["story_points"] == 13
    assert teams["Data"]["remaining_story_points"] == 3
    assert teams["Infra"]["done_story_points"] == 2
