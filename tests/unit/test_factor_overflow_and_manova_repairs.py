from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from datawork.application.analysis_service import AnalysisService
from datawork.application.executors import get_executor
from datawork.core.method_registry import get_method
from datawork.core.plan import AnalysisPlan
from datawork.core.validation import validate_plan_dataframe
from datawork.engine.batch import BatchAnalysisResult
from datawork.engine.manova import manova


service = AnalysisService()


def _factorial_frame(seed: int = 731, repeats: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for a, b, c in product(["0", "1"], repeat=3):
        for _ in range(repeats):
            rows.append({
                "A": a,
                "B": b,
                "C": c,
                "y": 2 * (a == "1") + 1.2 * (b == "1") + 0.7 * (c == "1") + rng.normal(0, 0.8),
            })
    return pd.DataFrame(rows)


def _interaction_frame(seed: int = 124) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for a, b in product(["A0", "A1"], ["B0", "B1"]):
        for _ in range(35):
            interaction = 4.5 if (a, b) in {("A0", "B0"), ("A1", "B1")} else -4.5
            latent = rng.normal()
            rows.append({
                "A": a,
                "B": b,
                "y": interaction + rng.normal(0, 0.8),
                "y1": interaction + latent + rng.normal(0, 0.5),
                "y2": 0.8 * interaction + 0.5 * latent + rng.normal(0, 0.6),
            })
    return pd.DataFrame(rows)


def test_oneway_overflow_defaults_to_all_single_factor_models() -> None:
    plan = AnalysisPlan(
        method="oneway_anova",
        dependent_variables=["y"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
    )
    assert plan.factor_combination_min_order == 1
    assert plan.factor_combination_max_order == 1

    result = service.run(_factorial_frame(), plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 3
    assert set(result.summary_df["factor_combination"].dropna()) == {"A", "B", "C"}


def test_twoway_overflow_defaults_to_all_two_factor_models() -> None:
    plan = AnalysisPlan(
        method="twoway_anova",
        dependent_variables=["y"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
    )
    assert plan.factor_combination_min_order == 2
    assert plan.factor_combination_max_order == 2

    result = service.run(_factorial_frame(), plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 3
    assert set(result.summary_df["factor_combination"].dropna()) == {"A × B", "A × C", "B × C"}
    assert result.summary_df["p_adjust_method"].eq("holm").all()
    report = validate_plan_dataframe(plan, _factorial_frame())
    warning = next(item for item in report.warnings if item.code == "factor_combination_batch")
    assert warning.details["factor_model_count"] == 3
    assert "3 个独立模型" in warning.message


def test_overflow_is_rejected_until_combination_mode_is_explicitly_enabled() -> None:
    with pytest.raises(ValidationError, match="最多允许 2 个固定因素"):
        AnalysisPlan(
            method="twoway_anova",
            dependent_variables=["y"],
            fixed_factors=["A", "B", "C"],
        )


def test_manova_is_joint_and_supports_explicit_factor_combination_batch() -> None:
    spec = get_method("threeway_manova")
    assert spec.dependent_mode == "joint"
    assert spec.min_dependent_vars == 2
    assert spec.supports_batch is True

    plan = AnalysisPlan(
        method="threeway_manova",
        dependent_variables=["y1", "y2"],
        fixed_factors=["A", "B", "C", "D"],
        factor_combinations_enabled=True,
    )
    assert plan.factor_combination_min_order == 3
    assert plan.factor_combination_max_order == 3

    rng = np.random.default_rng(81)
    rows: list[dict[str, object]] = []
    for values in product(["0", "1"], repeat=4):
        for _ in range(7):
            shift = sum((index + 1) * (value == "1") for index, value in enumerate(values))
            latent = rng.normal()
            rows.append({
                **dict(zip(["A", "B", "C", "D"], values)),
                "y1": shift + latent + rng.normal(0, 0.5),
                "y2": 0.6 * shift + 0.4 * latent + rng.normal(0, 0.6),
            })
    executable_plan = plan.model_copy(update={
        "method_parameters": {
            **plan.method_parameters,
            "multivariate_test": "pillai",
            "follow_up_mode": "none",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        }
    })
    result = service.run(pd.DataFrame(rows), executable_plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 4
    assert set(result.summary_df["factor_combination"].dropna()) == {
        "A × B × C", "A × B × D", "A × C × D", "B × C × D",
    }


def test_manova_explicit_emm_selection_reaches_engine() -> None:
    frame = _interaction_frame()
    plan = AnalysisPlan(
        method="twoway_manova",
        dependent_variables=["y1", "y2"],
        fixed_factors=["A", "B"],
        estimate_marginal_means=True,
        emm_factors=["A", "B"],
        method_parameters={
            "multivariate_test": "pillai",
            "follow_up_mode": "all",
            "follow_up_correction": "holm",
        },
    )
    result = get_executor("twoway_manova")(frame, plan)
    assert result.data_snapshot["estimate_marginal_means"] is True
    assert result.data_snapshot["emm_factors"] == ["A", "B"]
    assert result.estimated_marginal_means
    assert any("用户指定 MANOVA 跟进 EMM" in item.source for item in result.estimated_marginal_means)


def test_manova_condition_number_is_scale_invariant_and_bartlett_is_residual_based() -> None:
    frame = _interaction_frame()
    base = manova(frame, ["y1", "y2"], ["A", "B"], parameters={"multivariate_test": "pillai"})
    scaled_frame = frame.assign(y2=frame["y2"] * 1_000_000)
    scaled = manova(scaled_frame, ["y1", "y2"], ["A", "B"], parameters={"multivariate_test": "pillai"})
    assert base is not None and scaled is not None
    assert np.isclose(
        base.data_snapshot["outcome_matrix_condition_number"],
        scaled.data_snapshot["outcome_matrix_condition_number"],
        rtol=1e-6,
    )
    assert any("残差相关矩阵" in item.test_name for item in base.diagnostics)


def test_manova_always_outputs_preselected_primary_statistic_first() -> None:
    result = manova(
        _interaction_frame(),
        ["y1", "y2"],
        ["A", "B"],
        parameters={
            "multivariate_test": "wilks",
            "primary_multivariate_test": "pillai",
            "follow_up_mode": "none",
        },
    )

    assert result is not None
    first_by_effect = {}
    names_by_effect = {}
    for item in result.omnibus_tests:
        first_by_effect.setdefault(item.effect, item.statistic_name)
        names_by_effect.setdefault(item.effect, set()).add(item.statistic_name)
    assert all(name == "Pillai 轨迹" for name in first_by_effect.values())
    assert all({"Pillai 轨迹", "Wilks' Lambda"} <= names for names in names_by_effect.values())


def test_significant_interactions_generate_adjusted_simple_effects() -> None:
    frame = _interaction_frame()
    two_way = service.run(
        frame,
        AnalysisPlan(
            method="twoway_anova",
            dependent_variables=["y"],
            fixed_factors=["A", "B"],
            method_parameters={"posthoc_method": "holm", "simple_effect_correction": "holm"},
        ),
    )
    assert two_way.simple_effects
    assert all(item.p_adjusted is not None for item in two_way.simple_effects)
    assert all(item.correction == "holm" for item in two_way.simple_effects)
    assert not any(item.contrast.startswith("[A]") or item.contrast.startswith("[B]") for item in two_way.contrasts)

    multi = manova(
        frame,
        ["y1", "y2"],
        ["A", "B"],
        parameters={
            "multivariate_test": "pillai",
            "follow_up_mode": "all",
            "follow_up_correction": "holm",
            "simple_effect_correction": "holm",
            "posthoc_method": "holm",
        },
    )
    assert multi is not None
    assert multi.simple_effects
    assert multi.follow_up_tests
    assert all(item.sum_sq is not None and item.mean_sq is not None for item in multi.follow_up_tests)
    assert all(item.p_adjusted is not None for item in multi.simple_effects)
    assert not any("| A]" in item.contrast or "| B]" in item.contrast for item in multi.contrasts)


def test_dunnett_controls_can_be_mapped_per_factor() -> None:
    rng = np.random.default_rng(99)
    one_rows: list[dict[str, object]] = []
    for group, shift in [("CK", 0.0), ("T1", 2.0), ("T2", 3.0)]:
        for _ in range(24):
            one_rows.append({"group": group, "y": shift + rng.normal(0, 0.6)})
    one = service.run(
        pd.DataFrame(one_rows),
        AnalysisPlan(
            method="oneway_anova",
            dependent_variables=["y"],
            fixed_factors=["group"],
            method_parameters={"posthoc_method": "dunnett", "control_group": "group=CK"},
        ),
    )
    assert one.contrasts
    assert all("CK" in item.contrast for item in one.contrasts)

    two_rows: list[dict[str, object]] = []
    for f1, f2 in product(["L0", "L1", "L2"], ["X0", "X1", "X2"]):
        for _ in range(18):
            mean = 1.5 * (f1 != "L0") + 1.1 * (f2 != "X0")
            two_rows.append({"F1": f1, "F2": f2, "y": mean + rng.normal(0, 0.7)})
    two = service.run(
        pd.DataFrame(two_rows),
        AnalysisPlan(
            method="twoway_anova",
            dependent_variables=["y"],
            fixed_factors=["F1", "F2"],
            method_parameters={
                "posthoc_method": "dunnett",
                "control_group": "F1=L0;F2=X0",
                "simple_effect_correction": "holm",
            },
        ),
    )
    assert two.contrasts
    assert any("L0" in item.contrast for item in two.contrasts)
    assert any("X0" in item.contrast for item in two.contrasts)
