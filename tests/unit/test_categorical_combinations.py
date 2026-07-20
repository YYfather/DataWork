from itertools import product

import numpy as np
import pandas as pd
import pytest

from datawork.application.analysis_service import AnalysisService
from datawork.application.executors import get_executor
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan
from datawork.engine.batch import BatchAnalysisResult


service = AnalysisService()


def test_all_categorical_methods_have_executor_and_parameters_metadata():
    methods = [method for method in list_methods() if method.category.startswith("分类")]
    assert len(methods) >= 20
    for method in methods:
        assert method.purpose
        assert method.variable_relationship
        assert method.variable_requirements
        assert method.output_metrics
        assert get_executor(method.executor)
        for parameter in method.parameters:
            assert parameter.label_zh
            assert parameter.description


def test_factor_combination_batch_expands_combinations_and_adjusts_pvalues():
    rows = []
    rng = np.random.default_rng(12)
    factors = ["A", "B", "C", "D"]
    for levels in product(["0", "1"], repeat=4):
        for repeat in range(8):
            effect = sum((index + 1) * (level == "1") for index, level in enumerate(levels))
            row = {name: level for name, level in zip(factors, levels)}
            row["y"] = effect + rng.normal(0, 0.8)
            rows.append(row)
    result = service.run(
        pd.DataFrame(rows),
        AnalysisPlan(
            dependent_variables=["y"], fixed_factors=factors, method="twoway_anova",
            factor_combinations_enabled=True, factor_combination_min_order=2,
            factor_combination_max_order=2, combination_p_adjust="holm",
        ),
    )
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 6
    assert set(result.summary_df["factor_combination"].dropna()) == {
        "A × B", "A × C", "A × D", "B × C", "B × D", "C × D"
    }
    assert "p_adjusted_across_tasks" in result.summary_df
    assert result.summary_df["p_adjust_method"].eq("holm").all()
    assert "raw_conclusion" in result.overview_df
    assert set(result.overview_df["raw_conclusion"]) <= {"原始显著", "原始不显著"}
    assert "p_adjusted_across_tasks" in result.overview_df
    assert set(result.overview_df["conclusion"]) <= {"校正后显著", "校正后不显著"}


def test_none_adjustment_preserves_pvalues_and_custom_combination_names():
    rng = np.random.default_rng(18)
    rows = []
    for a, b in product(["0", "1"], repeat=2):
        for _ in range(16):
            rows.append({"A": a, "B": b, "y": 2 * int(a) + int(b) + rng.normal(0, 0.7)})
    result = service.run(
        pd.DataFrame(rows),
        AnalysisPlan(
            interface_mode="professional",
            dependent_variables=["y"], fixed_factors=["A", "B"], method="oneway_anova",
            factor_combinations_enabled=True, factor_combination_min_order=1,
            factor_combination_max_order=1, factor_combination_labels={"A": "主处理模型", "B": "辅助处理模型"},
            cross_model_p_adjust="none",
        ),
    )
    assert isinstance(result, BatchAnalysisResult)
    tests = result.summary_df.loc[result.summary_df["result_type"].eq("test")]
    assert tests["p_adjust_method"].eq("none").all()
    assert tests["p_adjusted_across_tasks"].isna().all()
    assert tests["significant_adjusted"].isna().all()
    assert set(tests["factor_combination"]) == {"主处理模型", "辅助处理模型"}
    assert set(tests["factor_columns"]) == {"A", "B"}
    assert set(result.overview_df["conclusion"]) <= {"原始显著", "原始不显著"}
    assert result.overview_df["raw_conclusion"].equals(result.overview_df["conclusion"])
    assert "p_adjusted_across_tasks" not in result.overview_df
    assert result.settings["cross_model_p_adjust"] == "none"
    assert result.settings["factor_combination_labels"] == {"A": "主处理模型", "B": "辅助处理模型"}


def test_custom_combination_names_must_be_unique():
    with pytest.raises(ValueError, match="组合名称不能重复"):
        AnalysisPlan(
            interface_mode="professional", dependent_variables=["y"], fixed_factors=["A", "B"],
            method="oneway_anova", factor_combinations_enabled=True,
            factor_combination_min_order=1, factor_combination_max_order=1,
            factor_combination_labels={"A": "同名模型", "B": "同名模型"},
        )


def test_chi_square_sampling_modes_and_k_group_posthoc():
    table_df = pd.DataFrame({
        "a": ["A"] * 25 + ["B"] * 25,
        "b": ["yes"] * 18 + ["no"] * 7 + ["yes"] * 8 + ["no"] * 17,
    })
    result = service.run(
        table_df,
        AnalysisPlan(
            fixed_factors=["a", "b"], method="chi_square_independence",
            method_parameters={
                "continuity_correction": "off", "power_divergence": "pearson",
                "p_value_method": "permutation", "n_resamples": 499,
                "random_seed": 7,
            },
        ),
    )
    assert 0 <= result.primary_tests[0].p_value <= 1
    assert result.data_snapshot["p_value_method"] == "permutation"

    groups = pd.DataFrame({
        "outcome": [1] * 18 + [0] * 12 + [1] * 12 + [0] * 18 + [1] * 6 + [0] * 24,
        "group": ["A"] * 30 + ["B"] * 30 + ["C"] * 30,
    })
    result = service.run(
        groups,
        AnalysisPlan(
            dependent_variables=["outcome"], fixed_factors=["group"], method="k_proportion_chi_square",
            method_parameters={"success_level": "1", "pairwise_posthoc": True, "pairwise_p_adjust": "holm"},
        ),
    )
    assert len(result.contrasts) == 3
    assert all(item.correction == "holm" for item in result.contrasts)


def test_exact_paired_stratified_and_agreement_categorical_methods():
    exact_df = pd.DataFrame({
        "treatment": ["A"] * 12 + ["B"] * 12,
        "response": ["yes"] * 9 + ["no"] * 3 + ["yes"] * 3 + ["no"] * 9,
    })
    for method in ["fisher_exact", "barnard_exact", "boschloo_exact"]:
        result = service.run(exact_df, AnalysisPlan(fixed_factors=["treatment", "response"], method=method))
        assert 0 <= result.primary_tests[0].p_value <= 1

    paired = pd.DataFrame({
        "r1": ["A", "A", "B", "B", "C", "C", "A", "B", "C", "A", "B", "C"] * 3,
        "r2": ["A", "B", "B", "C", "C", "A", "A", "B", "C", "B", "B", "C"] * 3,
        "r3": ["A", "A", "B", "B", "C", "C", "A", "B", "C", "A", "C", "C"] * 3,
    })
    for method in ["bowker_symmetry", "stuart_maxwell", "cohen_kappa"]:
        result = service.run(paired, AnalysisPlan(dependent_variables=["r1", "r2"], method=method))
        assert result.primary_tests
    fleiss = service.run(paired, AnalysisPlan(dependent_variables=["r1", "r2", "r3"], method="fleiss_kappa"))
    assert -1 <= fleiss.primary_tests[0].statistic_value <= 1

    q_df = pd.DataFrame({
        "q1": [1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        "q2": [1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 0],
        "q3": [0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0],
    })
    q = service.run(q_df, AnalysisPlan(dependent_variables=["q1", "q2", "q3"], method="cochran_q_test"))
    assert q.primary_tests[0].statistic_name == "Q"

    strata_rows = []
    for stratum, counts in {
        "S1": {(1, 1): 14, (1, 0): 6, (0, 1): 7, (0, 0): 13},
        "S2": {(1, 1): 12, (1, 0): 8, (0, 1): 6, (0, 0): 14},
        "S3": {(1, 1): 10, (1, 0): 10, (0, 1): 5, (0, 0): 15},
    }.items():
        for (exposure, outcome), count in counts.items():
            strata_rows += [{"outcome": outcome, "exposure": exposure, "strata": stratum}] * count
    strata_df = pd.DataFrame(strata_rows)
    for method in ["cochran_mantel_haenszel", "breslow_day"]:
        result = service.run(
            strata_df,
            AnalysisPlan(dependent_variables=["outcome"], fixed_factors=["exposure", "strata"], method=method),
        )
        assert result.primary_tests


def test_proportions_trend_and_categorical_regressions():
    binary = pd.DataFrame({"flag": ["yes"] * 36 + ["no"] * 24})
    for method in ["exact_binomial_test", "one_sample_proportion_ztest"]:
        result = service.run(binary, AnalysisPlan(fixed_factors=["flag"], method=method, method_parameters={"success_level": "yes"}))
        assert result.primary_tests

    trend_rows = []
    for dose, successes in [("low", 5), ("mid", 12), ("high", 20)]:
        trend_rows += [{"response": "yes", "dose": dose}] * successes
        trend_rows += [{"response": "no", "dose": dose}] * (25 - successes)
    trend = service.run(
        pd.DataFrame(trend_rows),
        AnalysisPlan(
            dependent_variables=["response"], fixed_factors=["dose"], method="cochran_armitage_trend",
            method_parameters={"success_level": "yes", "level_order": "low,mid,high", "scores": "0,1,2", "alternative": "greater"},
        ),
    )
    assert trend.primary_tests[0].p_value < 0.01

    rng = np.random.default_rng(4)
    n = 180
    x = rng.normal(size=n)
    group = np.where(rng.random(n) > 0.5, "B", "A")
    latent = x + (group == "B") * 0.4 + rng.normal(size=n)
    outcome = np.where(latent < -0.5, "low", np.where(latent < 0.7, "mid", "high"))
    frame = pd.DataFrame({"outcome": outcome, "x": x, "group": group})
    multi = service.run(
        frame,
        AnalysisPlan(dependent_variables=["outcome"], fixed_factors=["group"], covariates=["x"], method="multinomial_logistic_regression"),
    )
    assert multi.coefficients
    ordinal = service.run(
        frame,
        AnalysisPlan(
            dependent_variables=["outcome"], fixed_factors=["group"], covariates=["x"], method="ordinal_logistic_regression",
            method_parameters={"level_order": "low,mid,high"},
        ),
    )
    assert ordinal.coefficients
