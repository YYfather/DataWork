import pandas as pd

from datawork.core.plan import AnalysisPlan
from datawork.core.splitting import build_split_groups
from datawork.core.formula import apply_derived_columns
from datawork.core.validation import validate_plan_dataframe


def _plan(**updates):
    payload = {"method": "one_sample_ttest", "dependent_variables": ["y"], "split_by": ["group"]}
    payload.update(updates)
    return AnalysisPlan.model_validate(payload)


def test_legacy_split_keeps_original_levels():
    frame = pd.DataFrame({"y": [1, 2, 3], "group": ["A", "A", "B"]})
    groups = build_split_groups(frame, _plan())
    assert [(labels["group"], len(subset)) for labels, subset in groups] == [("A", 2), ("B", 1)]


def test_categorical_rule_can_merge_original_levels():
    frame = pd.DataFrame({"y": [1, 2, 3, 4], "group": ["A", "B", "C", "D"]})
    plan = _plan(split_rules=[{
        "column": "group", "kind": "categorical",
        "groups": [{"label": "前两组", "values": ["A", "B"]}, {"label": "后三组", "values": ["C", "D"]}],
    }])
    groups = build_split_groups(frame, plan)
    assert [(labels["group"], subset["y"].tolist()) for labels, subset in groups] == [
        ("前两组", [1, 2]), ("后三组", [3, 4]),
    ]


def test_numeric_rule_uses_explicit_interval_boundaries():
    frame = pd.DataFrame({"y": [1, 2, 3, 4], "group": [0, 10, 20, 30]})
    plan = _plan(split_rules=[{
        "column": "group", "kind": "numeric",
        "groups": [
            {"label": "低", "upper": 20, "include_upper": False},
            {"label": "高", "lower": 20, "include_lower": True},
        ],
    }])
    groups = build_split_groups(frame, plan)
    assert [(labels["group"], subset["group"].tolist()) for labels, subset in groups] == [
        ("低", [0, 10]), ("高", [20, 30]),
    ]


def test_ordinary_single_value_custom_group_excludes_unassigned_levels():
    frame = pd.DataFrame({"y": [1, 2, 3], "group": ["A", "B", "C"]})
    plan = _plan(split_rules=[{
        "column": "group", "kind": "categorical",
        "groups": [{"label": "只分析A", "values": ["A"]}],
    }])
    groups = build_split_groups(frame, plan)
    assert len(groups) == 1
    assert groups[0][0] == {"group": "只分析A"}
    assert groups[0][1]["y"].tolist() == [1]


def test_custom_dependent_column_inherits_source_and_unrelated_splits():
    frame = pd.DataFrame({
        "A": [1, 1, 2, 2], "B": ["x", "y", "x", "y"],
        "Z": ["p", "p", "q", "q"], "value": [1.0, 2.0, 3.0, 4.0],
    })
    plan = _plan(
        interface_mode="professional", dependent_variables=["C"],
        split_by=["A", "B", "Z"],
        derived_columns=[{"name": "C", "formula": "[value] / 3", "source_columns": ["value"]}],
    )
    derived, _, _ = apply_derived_columns(frame, plan.derived_columns)
    groups = build_split_groups(derived, plan)
    assert len(groups) == 4
    assert {tuple(labels.values()) for labels, _ in groups} == {
        ("1", "x", "p"), ("1", "y", "p"), ("2", "x", "q"), ("2", "y", "q"),
    }
    assert derived["C"].tolist() == [0.33333333, 0.66666667, 1.0, 1.33333333]


def test_empty_cartesian_split_groups_are_skipped_but_available_to_preflight():
    frame = pd.DataFrame({"A": ["a", "b"], "B": ["x", "y"], "y": [1.0, 2.0]})
    plan = _plan(split_by=["A", "B"])
    assert len(build_split_groups(frame, plan)) == 2
    assert len(build_split_groups(frame, plan, include_empty=True)) == 4


def test_expanded_split_task_limit_is_reported_before_materialization():
    values = list(range(11))
    frame = pd.DataFrame({
        "A": values * 121,
        "B": [value for value in values for _ in range(11)] * 11,
        "C": [value for value in values for _ in range(121)],
        "y": list(range(1331)),
    })
    plan = _plan(split_by=["A", "B", "C"])
    report = validate_plan_dataframe(plan, frame)
    assert any(issue.code == "split_group_limit_exceeded" for issue in report.issues)
