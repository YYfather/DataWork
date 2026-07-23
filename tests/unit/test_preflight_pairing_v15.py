from __future__ import annotations

from datawork.application.preflight_service import PreflightService

from test_pairing_workflow_v15 import _frame, _plan


def test_preflight_exposes_pairing_audit_and_three_dimensional_task_tree() -> None:
    plan = _plan()
    report = PreflightService().inspect(_frame(), plan.model_dump(mode="json"))

    assert report.pairing_summary["enabled"] is True
    assert report.pairing_summary["successful_pairs"] == 48
    assert report.pairing_summary["pairing_order"] == "按匹配组内原始导入行顺序"
    assert report.batch_summary["outcome_group_count"] == 2
    assert report.batch_summary["factor_model_count"] == 1
    assert report.batch_summary["split_group_count"] == 2
    assert report.batch_summary["expanded_task_count"] == 4
    assert report.task_hierarchy["task_count"] == 4
    assert [item["name"] for item in report.task_hierarchy["outcome_groups"]] == [
        "time-1",
        "time-2",
    ]
    assert all("dependent_group" in item for item in report.task_hierarchy["tasks"])


def test_preflight_marks_unrelated_split_as_post_pair_only() -> None:
    payload = _plan(split_by=["year", "mode"]).model_dump(mode="json")
    report = PreflightService().inspect(_frame(), payload)
    relationships = {
        item["column"]: item["relationship"]
        for item in report.pairing_summary["split_relationships"]
    }
    assert relationships == {
        "year": "参与匹配并拆分",
        "mode": "参与匹配并拆分",
    }


def test_preflight_marks_non_match_split_without_changing_pair_count() -> None:
    plan = _plan(split_by=["year", "source"])
    report = PreflightService().inspect(_frame(), plan.model_dump(mode="json"))
    relationship = next(
        item
        for item in report.pairing_summary["split_relationships"]
        if item["column"] == "source"
    )
    assert relationship["relationship"] == "仅配对后拆分"
    assert relationship["detail"] == "与公式无关；配对完成后作用于整个分析任务"
    assert relationship["recommend_add_to_match"] is False
    assert report.pairing_summary["successful_pairs"] == 48
