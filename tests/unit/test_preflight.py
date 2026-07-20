import pandas as pd
import pytest

from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.plan import AnalysisPlan
from datawork.engine.categorical_methods import stuart_maxwell_test


def test_generic_batch_does_not_depend_on_domain_column_names():
    frame = pd.DataFrame({
        "wave": ["x"] * 6 + ["y"] * 6,
        "category": ["left"] * 3 + ["right"] * 3 + ["left"] * 3 + ["right"] * 3,
        "score": [1, 2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 7],
    })
    raw = {
        "dependent_variables": ["score"],
        "fixed_factors": ["category"],
        "split_by": ["wave"],
        "method": "welch_ttest",
    }
    report = PreflightService().inspect(frame, raw)
    assert report.ready is True
    assert report.batch_summary["group_count"] == 2

    result = AnalysisService().run(frame, AnalysisPlan.model_validate(raw))
    assert result.split_cols == ["wave"]
    assert result.summary_df is not None
    assert result.summary_df.shape[0] == 2


def test_preflight_reports_role_overlap_without_running_analysis():
    frame = pd.DataFrame({"x": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]})
    report = PreflightService().inspect(frame, {
        "dependent_variables": ["x"],
        "fixed_factors": ["g"],
        "split_by": ["g"],
        "method": "welch_ttest",
    })
    assert report.ready is False
    assert any(issue.code == "overlapping_roles" for issue in report.issues)


def test_multiple_outcome_columns_expand_into_generic_batch_tasks():
    frame = pd.DataFrame({
        "block": ["one"] * 6 + ["two"] * 6,
        "group": ["A"] * 3 + ["B"] * 3 + ["A"] * 3 + ["B"] * 3,
        "measure_alpha": [1, 2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 7],
        "measure_beta": [10, 11, 12, 15, 16, 17, 11, 12, 13, 16, 17, 18],
    })
    raw = {
        "dependent_variables": ["measure_alpha", "measure_beta"],
        "fixed_factors": ["group"],
        "split_by": ["block"],
        "method": "welch_ttest",
    }
    plan = AnalysisPlan.model_validate(raw)
    assert plan.is_batch is True
    report = PreflightService().inspect(frame, raw)
    assert report.ready is True
    assert report.batch_summary["group_count"] == 4

    result = AnalysisService().run(frame, plan)
    assert result.summary_df is not None
    assert result.summary_df.shape[0] == 4
    assert set(result.summary_df["dependent_variable"]) == {"measure_alpha", "measure_beta"}


def test_stuart_maxwell_blocks_singular_covariance_instead_of_returning_nan():
    frame = pd.DataFrame({
        "before": ["A", "B", "C", "A"],
        "after": ["A", "B", "C", "A"],
    })
    raw = {
        "dependent_variables": ["before", "after"],
        "method": "stuart_maxwell",
    }
    report = PreflightService().inspect(frame, raw)
    assert report.ready is False
    assert any(
        issue.code == "singular_marginal_homogeneity_covariance"
        for issue in report.issues
    )
    with pytest.raises(ValueError, match="协方差矩阵不可逆"):
        stuart_maxwell_test(frame, "before", "after", 0.05)


def test_batch_subsets_are_revalidated_before_execution():
    frame = pd.DataFrame({
        "split": ["main"] * 6 + ["tiny"] * 2,
        "r1": ["A", "A", "B", "B", "C", "C", "C", "C"],
        "r2": ["A", "B", "B", "C", "C", "A", "C", "C"],
        "r3": ["A", "A", "B", "C", "C", "B", "C", "C"],
    })
    raw = {
        "dependent_variables": ["r1", "r2", "r3"],
        "split_by": ["split"],
        "method": "fleiss_kappa",
    }
    report = PreflightService().inspect(frame, raw)
    assert report.batch_summary["problem_group_count"] == 1
    result = AnalysisService().run(frame, AnalysisPlan.model_validate(raw))
    tiny = next(item for item in result.results if item.subset_info["split"] == "tiny")
    assert tiny.error
    assert not tiny.records
