import numpy as np
import pandas as pd

from datawork.application.analysis_service import AnalysisService
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan


service = AnalysisService()


def test_registry_methods_have_complete_user_guidance():
    methods = list_methods()
    assert len(methods) >= 27
    assert sum(method.is_runnable for method in methods) >= 26
    for method in methods:
        assert method.category
        assert method.purpose
        assert method.variable_relationship
        assert method.variable_requirements
        assert method.output_metrics
        if method.is_runnable:
            assert method.executor


def test_descriptive_and_one_sample_ttest():
    df = pd.DataFrame({"height": [9.0, 10.0, 11.0, 12.0, 8.0]})
    descriptive = service.run(
        df,
        AnalysisPlan(dependent_variables=["height"], method="descriptive_statistics"),
    )
    assert descriptive.descriptive_stats[0]["variable"] == "height"

    result = service.run(
        df,
        AnalysisPlan(dependent_variables=["height"], method="one_sample_ttest", test_value=10.0),
    )
    assert result.primary_tests[0].statistic_name == "t"
    assert result.primary_tests[0].effect_size_name == "Cohen's d"


def test_nonparametric_independent_and_paired_methods():
    independent = pd.DataFrame({
        "value": [1, 2, 2, 3, 6, 7, 8, 9],
        "group": ["A"] * 4 + ["B"] * 4,
    })
    mann = service.run(
        independent,
        AnalysisPlan(dependent_variables=["value"], fixed_factors=["group"], method="mann_whitney_u"),
    )
    assert mann.primary_tests[0].statistic_name == "U"

    paired = pd.DataFrame({"before": [1, 2, 3, 4, 5], "after": [2, 3, 4, 5, 7]})
    wilcoxon = service.run(
        paired,
        AnalysisPlan(dependent_variables=["before", "after"], method="wilcoxon_signed_rank"),
    )
    assert wilcoxon.primary_tests[0].statistic_name == "W"


def test_kruskal_and_correlations():
    df = pd.DataFrame({
        "value": [1, 2, 3, 4, 5, 6, 10, 11, 12],
        "group": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
        "x": np.arange(1, 10),
        "y": np.arange(1, 10) * 2 + np.array([0, 1, -1, 0, 1, -1, 0, 1, -1]),
    })
    kruskal = service.run(
        df,
        AnalysisPlan(dependent_variables=["value"], fixed_factors=["group"], method="kruskal_wallis"),
    )
    assert kruskal.primary_tests[0].statistic_name == "H"

    for method, statistic_name in [
        ("pearson_correlation", "r"),
        ("spearman_correlation", "rho"),
        ("kendall_correlation", "tau"),
    ]:
        result = service.run(df, AnalysisPlan(dependent_variables=["x", "y"], method=method))
        assert result.primary_tests[0].statistic_name == statistic_name


def test_linear_and_logistic_regression():
    x = np.arange(1, 31, dtype=float)
    linear_df = pd.DataFrame({"y": 3.0 + 1.8 * x + np.sin(x), "x": x})
    linear = service.run(
        linear_df,
        AnalysisPlan(dependent_variables=["y"], covariates=["x"], method="linear_regression"),
    )
    assert any("x" in item.term for item in linear.coefficients)
    assert any(item.name == "R-squared" for item in linear.fit_statistics)

    logistic_df = pd.DataFrame({
        "outcome": [0] * 10 + [1] * 10,
        "x": list(range(10)) + list(range(5, 15)),
        "group": ["A", "B"] * 10,
    })
    logistic = service.run(
        logistic_df,
        AnalysisPlan(
            dependent_variables=["outcome"],
            fixed_factors=["group"],
            covariates=["x"],
            method="logistic_regression",
        ),
    )
    assert logistic.coefficients
    assert any(item.transformed_name == "odds ratio" for item in logistic.coefficients)


def test_categorical_methods():
    independence_df = pd.DataFrame({
        "treatment": ["A"] * 20 + ["B"] * 20,
        "response": ["yes"] * 12 + ["no"] * 8 + ["yes"] * 5 + ["no"] * 15,
    })
    chi = service.run(
        independence_df,
        AnalysisPlan(fixed_factors=["treatment", "response"], method="chi_square_independence"),
    )
    assert chi.primary_tests[0].statistic_name == "chi-square"

    fisher_df = pd.DataFrame({
        "treatment": ["A"] * 8 + ["B"] * 8,
        "response": ["yes"] * 6 + ["no"] * 2 + ["yes"] * 2 + ["no"] * 6,
    })
    fisher = service.run(
        fisher_df,
        AnalysisPlan(fixed_factors=["treatment", "response"], method="fisher_exact"),
    )
    assert fisher.primary_tests[0].statistic_name == "odds ratio"

    gof_df = pd.DataFrame({"class": ["A"] * 10 + ["B"] * 20 + ["C"] * 30})
    gof = service.run(
        gof_df,
        AnalysisPlan(
            fixed_factors=["class"],
            method="chi_square_goodness_of_fit",
            expected_proportions=[1 / 3, 1 / 3, 1 / 3],
        ),
    )
    assert gof.primary_tests[0].statistic_name == "chi-square"


def test_ancova_repeated_and_friedman():
    ancova_rows = []
    for group, offset in [("A", 0.0), ("B", 2.0)]:
        for baseline in range(1, 11):
            ancova_rows.append({"outcome": 5 + offset + 0.7 * baseline + (baseline % 2) * 0.2, "group": group, "baseline": baseline})
    ancova_result = service.run(
        pd.DataFrame(ancova_rows),
        AnalysisPlan(
            dependent_variables=["outcome"], fixed_factors=["group"], covariates=["baseline"], method="ancova"
        ),
    )
    assert ancova_result.omnibus_tests
    assert ancova_result.coefficients

    repeated_rows = []
    for subject in range(1, 9):
        for time, shift in [("T1", 0.0), ("T2", 1.0), ("T3", 2.0)]:
            repeated_rows.append({"subject": subject, "time": time, "value": subject + shift + (subject % 2) * 0.1})
    repeated_df = pd.DataFrame(repeated_rows)
    repeated = service.run(
        repeated_df,
        AnalysisPlan(
            dependent_variables=["value"], subject_id="subject", repeated_factor="time", method="repeated_measures_anova"
        ),
    )
    assert repeated.omnibus_tests

    friedman = service.run(
        repeated_df,
        AnalysisPlan(dependent_variables=["value"], subject_id="subject", repeated_factor="time", method="friedman_test"),
    )
    assert friedman.primary_tests[0].statistic_name == "chi-square"
