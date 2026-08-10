from engineering_ops.services.sprints import overcommit_analysis


def test_points_overcommit():
    result = overcommit_analysis(40, 15, 50, buffer_percent=10)
    assert result["overcommitted"] is True
    assert result["safe_capacity_story_points"] == 45
    assert result["over_by_story_points"] == 10


def test_points_within_capacity():
    result = overcommit_analysis(30, 5, 50, buffer_percent=10)
    assert result["overcommitted"] is False
