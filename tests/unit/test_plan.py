import pandas as pd
import pytest

from datawork.core.plan import AnalysisPlan
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


def test_split_column_cannot_also_be_model_factor():
    with pytest.raises(ValueError, match="不能同时进入模型"):
        AnalysisPlan(
            dependent_variables=["y"],
            fixed_factors=["g"],
            split_by=["g"],
            method="oneway_anova",
        )


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
