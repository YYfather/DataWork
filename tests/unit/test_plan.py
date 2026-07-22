import pandas as pd
import pytest

from datawork.core.plan import AnalysisPlan, migrate_saved_derived_roles
from datawork.application.analysis_service import AnalysisService


def test_mixed_anova_requires_complete_roles():
    with pytest.raises(ValueError, match="受试者/样本 ID"):
        AnalysisPlan(dependent_variables=["y"], fixed_factors=["g"], method="mixed_anova")


def test_mixed_anova_plan_is_available():
    plan = AnalysisPlan(
        dependent_variables=["y"],
        fixed_factors=["group"],
        subject_id="subject",
        repeated_factor="time",
        method="mixed_anova",
    )
    assert plan.method == "mixed_anova"


def test_split_column_cannot_also_be_model_factor_without_professional_groups():
    with pytest.raises(ValueError, match="专业模式"):
        AnalysisPlan(
            dependent_variables=["y"],
            fixed_factors=["g"],
            split_by=["g"],
            method="oneway_anova",
        )


def test_professional_split_column_can_also_be_factor_with_two_levels_per_group():
    plan = AnalysisPlan(
        interface_mode="professional",
        dependent_variables=["y"],
        fixed_factors=["g"],
        split_by=["g"],
        split_rules=[{
            "column": "g", "kind": "categorical",
            "groups": [
                {"label": "前组", "values": ["A", "B"]},
                {"label": "后组", "values": ["C", "D"]},
            ],
        }],
        method="oneway_anova",
    )
    frame = pd.DataFrame({
        "g": ["A", "A", "B", "B", "C", "C", "D", "D"],
        "y": [1, 2, 3, 4, 5, 6, 7, 8],
    })
    assert AnalysisService().execute(frame, plan).result.results


def test_dual_role_split_rejects_single_value_group():
    with pytest.raises(ValueError, match="每组至少需要两个"):
        AnalysisPlan(
            interface_mode="professional",
            dependent_variables=["y"], fixed_factors=["g"], split_by=["g"],
            split_rules=[{
                "column": "g", "kind": "categorical",
                "groups": [
                    {"label": "单值", "values": ["A"]},
                    {"label": "其余", "values": ["B", "C"]},
                ],
            }],
            method="oneway_anova",
        )


def test_ordinary_split_still_allows_one_custom_single_value_group():
    plan = AnalysisPlan(
        interface_mode="professional",
        dependent_variables=["y"], split_by=["g"],
        split_rules=[{
            "column": "g", "kind": "categorical",
            "groups": [{"label": "只分析A", "values": ["A"]}],
        }],
        method="one_sample_ttest",
    )
    assert plan.split_by == ["g"]


def test_dual_role_split_is_blocked_when_complete_cases_leave_one_level():
    plan = AnalysisPlan(
        interface_mode="professional",
        dependent_variables=["y"], fixed_factors=["g"], split_by=["g"],
        split_rules=[{
            "column": "g", "kind": "categorical",
            "groups": [
                {"label": "前组", "values": ["A", "B"]},
                {"label": "后组", "values": ["C", "D"]},
            ],
        }],
        method="oneway_anova",
    )
    frame = pd.DataFrame({
        "g": ["A", "A", "B", "B", "C", "C", "D", "D"],
        "y": [1.0, 2.0, None, None, 5.0, 6.0, 7.0, 8.0],
    })
    with pytest.raises(ValueError, match="最终分析子集"):
        AnalysisService().execute(frame, plan)


def test_custom_columns_cannot_reference_other_custom_columns():
    with pytest.raises(ValueError, match="不能引用其他自定义列"):
        AnalysisPlan(
            interface_mode="professional",
            dependent_variables=["b"],
            derived_columns=[
                {"name": "a", "formula": "[x] + 1", "source_columns": ["x"]},
                {"name": "b", "formula": "[a] * 2", "source_columns": ["a"]},
            ],
            method="one_sample_ttest",
        )


def test_custom_column_limits_and_roles_are_enforced():
    too_many_sources = [f"x{i}" for i in range(11)]
    with pytest.raises(ValueError, match="最多引用 10"):
        AnalysisPlan(
            interface_mode="professional", method="one_sample_ttest",
            dependent_variables=["custom"],
            derived_columns=[{
                "name": "custom",
                "formula": " + ".join(f"[{name}]" for name in too_many_sources),
                "source_columns": too_many_sources,
            }],
        )

    definitions = [
        {"name": f"custom{i}", "formula": "[x] + 1", "source_columns": ["x"]}
        for i in range(11)
    ]
    with pytest.raises(ValueError, match="最多允许 10 个自定义列"):
        AnalysisPlan(
            interface_mode="professional", method="one_sample_ttest",
            dependent_variables=["custom0"], derived_columns=definitions,
        )

    for field, value in (
        ("fixed_factors", ["custom"]),
        ("covariates", ["custom"]),
        ("random_factors", ["custom"]),
        ("random_slopes", ["custom"]),
        ("split_by", ["custom"]),
    ):
        payload = {
            "interface_mode": "professional", "method": "one_sample_ttest",
            "dependent_variables": ["custom"], field: value,
            "derived_columns": [{"name": "custom", "formula": "[x] + 1", "source_columns": ["x"]}],
        }
        with pytest.raises(ValueError, match="只能作为因变量"):
            AnalysisPlan(**payload)


def test_custom_dependent_column_can_be_calibrated():
    plan = AnalysisPlan(
        interface_mode="professional", method="one_sample_ttest",
        dependent_variables=["custom"],
        derived_columns=[{"name": "custom", "formula": "[x] / 3", "source_columns": ["x"]}],
        calibration_enabled=True, calibration_columns=["custom"],
    )
    assert plan.calibration_columns == ["custom"]


def test_saved_plan_migration_removes_all_illegal_custom_column_roles():
    raw = {
        "interface_mode": "professional", "method": "welch_ttest",
        "dependent_variables": ["custom"], "fixed_factors": ["group", "custom"],
        "covariates": ["custom"], "random_factors": ["custom"],
        "random_slopes": ["custom"], "split_by": ["custom"],
        "subject_id": "custom", "repeated_factor": "custom",
        "emm_factors": ["custom"], "calibration_columns": ["custom", "other_custom"],
        "split_rules": [{"column": "custom", "kind": "categorical", "groups": []}],
        "factor_combination_labels": {"group × custom": "旧组合"},
        "derived_columns": [
            {"name": "custom", "formula": "[x] + 1", "source_columns": ["x"]},
            {"name": "other_custom", "formula": "[y] + 1", "source_columns": ["y"]},
        ],
    }
    cleaned, warnings = migrate_saved_derived_roles(raw)
    assert cleaned["fixed_factors"] == ["group"]
    assert all(not cleaned[field] for field in (
        "covariates", "random_factors", "random_slopes", "split_by", "emm_factors", "split_rules",
    ))
    assert cleaned["subject_id"] is None and cleaned["repeated_factor"] is None
    assert cleaned["calibration_columns"] == ["custom"]
    assert cleaned["factor_combination_labels"] == {}
    assert warnings and raw["fixed_factors"] == ["group", "custom"]


def test_covariate_is_not_silently_ignored():
    with pytest.raises(ValueError, match="不会使用协变量"):
        AnalysisPlan(
            dependent_variables=["y"], fixed_factors=["g"],
            covariates=["baseline"], method="oneway_anova",
        )


def test_unknown_column_is_rejected_before_execution():
    df = pd.DataFrame({"y": [1, 2, 3], "g": ["a", "a", "b"]})
    plan = AnalysisPlan(dependent_variables=["missing"], fixed_factors=["g"], method="oneway_anova")
    with pytest.raises(ValueError, match="不存在"):
        AnalysisService().run(df, plan)
