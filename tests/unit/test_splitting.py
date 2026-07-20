import pandas as pd

from datawork.core.plan import AnalysisPlan
from datawork.core.splitting import build_split_groups


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
