from __future__ import annotations

from itertools import product

import pandas as pd
import pytest
from pydantic import ValidationError

from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import MethodStatus, list_methods
from datawork.core.plan import AnalysisPlan
from datawork.core.task_expansion import outcome_tasks
from datawork.engine.batch import BatchAnalysisResult


def _manova_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, block, replicate in product(["A", "B"], ["X", "Y"], range(8)):
        shift = (group == "B") * 1.2 + (block == "Y") * 0.4
        rows.append({
            "group": group,
            "block": block,
            "split": "early" if replicate < 4 else "late",
            "y1": replicate * 0.31 + shift,
            "y2": replicate * 0.22 - shift * 0.4 + (replicate % 2) * 0.15,
            "y3": replicate * 0.17 + shift * 0.7 + (replicate % 3) * 0.11,
            "y4": replicate * 0.27 - shift * 0.2 + (replicate % 4) * 0.09,
        })
    return pd.DataFrame(rows)


def test_v16_manual_groups_infer_manual_mode_without_new_field() -> None:
    plan = AnalysisPlan.model_validate({
        "interface_mode": "professional",
        "method": "oneway_manova",
        "dependent_variables": ["y1", "y2", "y3", "y4"],
        "dependent_variable_groups": [
            {"name": "前组", "dependent_variables": ["y1", "y2"]},
            {"name": "后组", "dependent_variables": ["y3", "y4"]},
        ],
        "fixed_factors": ["group"],
    })
    assert plan.dependent_task_mode == "manual_groups"
    assert [task.name for task in outcome_tasks(plan)] == ["前组", "后组"]


def test_manova_combinations_are_unordered_stable_and_can_overlap() -> None:
    plan = AnalysisPlan(
        interface_mode="professional",
        method="oneway_manova",
        dependent_variables=["y1", "y2", "y3", "y4"],
        fixed_factors=["group"],
        dependent_task_mode="combinations",
        dependent_combination_min_size=2,
        dependent_combination_max_size=3,
        dependent_combination_labels={"y1 + y2": "核心性状"},
    )
    tasks = outcome_tasks(plan)
    assert len(tasks) == 10
    assert tasks[0].variables == ("y1", "y2")
    assert tasks[0].name == "核心性状"
    assert tasks[-1].variables == ("y2", "y3", "y4")
    assert sum("y1" in task.variables for task in tasks) > 1
    assert ("y2", "y1") not in [task.variables for task in tasks]


def test_dependent_combinations_require_professional_joint_method() -> None:
    with pytest.raises(ValidationError, match="专业模式"):
        AnalysisPlan(
            method="oneway_manova",
            dependent_variables=["y1", "y2"],
            fixed_factors=["group"],
            dependent_task_mode="combinations",
        )
    with pytest.raises(ValidationError, match="不是联合响应方法"):
        AnalysisPlan(
            interface_mode="professional",
            method="oneway_anova",
            dependent_variables=["y1", "y2"],
            fixed_factors=["group"],
            dependent_task_mode="combinations",
        )


def test_dependent_combination_validation_rejects_range_and_unknown_labels() -> None:
    base = {
        "interface_mode": "professional",
        "method": "oneway_manova",
        "dependent_variables": ["y1", "y2", "y3"],
        "fixed_factors": ["group"],
        "dependent_task_mode": "combinations",
    }
    with pytest.raises(ValidationError, match="不能大于最大"):
        AnalysisPlan(**base, dependent_combination_min_size=3, dependent_combination_max_size=2)
    with pytest.raises(ValidationError, match="不存在的因变量组合"):
        AnalysisPlan(**base, dependent_combination_labels={"y1 + missing": "错误组合"})


def test_preflight_and_execution_share_exact_dependent_combination_tasks() -> None:
    frame = _manova_frame()
    plan = AnalysisPlan(
        interface_mode="professional",
        method="oneway_manova",
        dependent_variables=["y1", "y2", "y3", "y4"],
        fixed_factors=["group"],
        dependent_task_mode="combinations",
        dependent_combination_min_size=2,
        dependent_combination_max_size=2,
        method_parameters={"follow_up_mode": "none"},
        diagnostic_plots=False,
    )
    report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
    assert report.ready
    assert report.batch_summary["dependent_combination_count"] == 6
    assert report.batch_summary["expanded_task_count"] == 6
    assert report.batch_summary["dimensions"][:3] == [
        "dependent_combination",
        "dependent_columns",
        "dependent_combination_size",
    ]

    result = AnalysisService().run(frame, plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 6
    assert result.split_cols[:3] == report.batch_summary["dimensions"][:3]
    assert {
        item.subset_info["dependent_combination"] for item in result.results
    } == {
        "y1 + y2", "y1 + y3", "y1 + y4",
        "y2 + y3", "y2 + y4", "y3 + y4",
    }
    assert all(item.result is not None and not item.error for item in result.results)


def test_all_combination_sizes_over_hard_limit_are_rejected_before_execution() -> None:
    outcomes = [f"y{index}" for index in range(10)]
    with pytest.raises(ValidationError, match="1013 个组合"):
        AnalysisPlan(
            interface_mode="professional",
            method="oneway_manova",
            dependent_variables=outcomes,
            fixed_factors=["group"],
            dependent_task_mode="combinations",
            dependent_combination_min_size=2,
            dependent_combination_max_size=10,
        )


def test_every_visible_runnable_core_is_formally_implemented() -> None:
    methods = [item for item in list_methods() if item.visible and item.is_runnable]
    assert len(methods) == 47
    assert {item.name for item in methods if item.status is not MethodStatus.IMPLEMENTED} == set()
