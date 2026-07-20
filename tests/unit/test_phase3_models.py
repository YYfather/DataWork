import numpy as np
import pandas as pd

from datawork.application.executors import list_executor_names
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan
from datawork.engine.advanced_methods import mixed_anova, repeated_measures_anova
from datawork.engine.model_support import sphericity_result
from datawork.engine.regression_methods import linear_regression


def _balanced_mixed_frame() -> pd.DataFrame:
    rows = []
    subject = 0
    offsets = [-1.5, -0.5, 0.5, 1.5]
    for group_index, group in enumerate(["A", "B"]):
        for offset in offsets:
            subject += 1
            for time_index, time in enumerate(["T1", "T2", "T3"]):
                interaction = group_index * time_index * 1.5
                value = 10 + group_index * 2 + time_index * 1.2 + interaction + offset
                rows.append({"subject": f"S{subject}", "group": group, "time": time, "y": value})
    return pd.DataFrame(rows)


def test_every_runnable_method_has_registered_executor():
    executors = list_executor_names()
    missing = {spec.executor for spec in list_methods(runnable_only=True)} - executors
    assert missing == set()


def test_mixed_anova_returns_three_effects_and_adjustments():
    result = mixed_anova(
        _balanced_mixed_frame(), "y", "subject", "time", "group", 0.05,
        {"pairwise_correction": "holm"}, estimate_emm=True, diagnostic_plots=True,
    )
    assert [test.effect for test in result.omnibus_tests] == ["group", "time", "group × time"]
    assert len(result.estimated_marginal_means) == 6
    assert result.contrasts
    assert result.diagnostic_plots
    assert result.omnibus_tests[1].f_value > 0


def test_repeated_anova_exposes_sphericity_and_pairwise_results():
    frame = _balanced_mixed_frame().query("group == 'A'")
    result = repeated_measures_anova(
        frame, "y", "subject", "time", 0.05,
        {"sphericity_correction": "auto", "pairwise_correction": "holm"},
        estimate_emm=True, diagnostic_plots=True,
    )
    assert len(result.omnibus_tests) == 1
    assert len(result.estimated_marginal_means) == 3
    assert len(result.contrasts) == 3
    assert result.diagnostic_plots


def test_sphericity_two_levels_is_not_applicable():
    wide = pd.DataFrame({"T1": [1, 2, 3], "T2": [2, 3, 4]})
    assert sphericity_result(wide) is None


def test_linear_regression_model_emm_and_diagnostics():
    frame = pd.DataFrame({
        "y": [1.0, 2.2, 2.8, 4.1, 4.8, 6.2, 6.9, 8.2],
        "x": [0, 1, 2, 3, 4, 5, 6, 7],
        "group": ["A", "A", "A", "A", "B", "B", "B", "B"],
    })
    result = linear_regression(
        frame, "y", ["group"], ["x"], 0.05,
        emm_factors=["group"], contrast_correction="holm", diagnostic_plots=True,
    )
    assert len(result.estimated_marginal_means) == 2
    assert len(result.contrasts) == 1
    assert len(result.diagnostic_plots) >= 3


def test_phase3_plan_options_round_trip():
    plan = AnalysisPlan(
        dependent_variables=["y"], fixed_factors=["group", "time"],
        random_factors=["subject"], random_slopes=["time"],
        method="linear_mixed_model", estimate_marginal_means=True,
        emm_factors=["group"], contrast_correction="holm", diagnostic_plots=True,
    )
    payload = plan.model_dump(mode="json")
    assert payload["random_slopes"] == ["time"]
    assert payload["estimate_marginal_means"] is True


def test_linear_mixed_model_random_slope_and_reml_reporting():
    from datawork.engine.regression_methods import linear_mixed_model
    rng = np.random.default_rng(42)
    rows = []
    for group_index in range(10):
        intercept = rng.normal(0, 0.8)
        slope = rng.normal(0, 0.2)
        for time in range(5):
            rows.append({
                "cluster": f"C{group_index}",
                "condition": "A" if group_index < 5 else "B",
                "time": float(time),
                "y": 2 + 0.7 * time + intercept + slope * time + rng.normal(0, 0.2),
            })
    result = linear_mixed_model(
        pd.DataFrame(rows), "y", ["condition"], ["time"], "cluster", 0.05,
        parameters={"reml": True, "optimizer": "lbfgs", "max_iterations": 500},
        random_slopes=["time"], emm_factors=["condition"], diagnostic_plots=True,
    )
    names = {item.name for item in result.fit_statistics}
    assert "AIC" not in names
    assert "BIC" not in names
    assert any("REML" in warning for warning in result.warnings)
    assert any(name.startswith("Random covariance") for name in names)
