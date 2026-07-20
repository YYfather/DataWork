from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.plan import AnalysisPlan
from datawork.engine.batch import BatchAnalysisResult


def _frame(order: int, seed: int = 20260719) -> tuple[pd.DataFrame, list[str]]:
    rng = np.random.default_rng(seed + order)
    factors = [f"因素{i + 1}" for i in range(order)]
    rows: list[dict[str, object]] = []
    for levels in product(["低", "高"], repeat=order):
        for _ in range(18):
            effect = sum((index + 1) * (value == "高") for index, value in enumerate(levels))
            latent = rng.normal()
            row = {factor: value for factor, value in zip(factors, levels)}
            row["性状1"] = 5 + effect + latent + rng.normal(0, 0.5)
            row["性状2"] = 2 + 0.65 * effect + 0.45 * latent + rng.normal(0, 0.55)
            rows.append(row)
    return pd.DataFrame(rows), factors


@pytest.mark.parametrize(
    ("method", "order"),
    [("oneway_manova", 1), ("twoway_manova", 2), ("threeway_manova", 3)],
)
def test_fixed_manova_preflight_accepts_completed_required_roles(method: str, order: int) -> None:
    frame, factors = _frame(order)
    raw = {
        "method": method,
        "dependent_variables": ["性状1", "性状2"],
        "fixed_factors": factors,
        "method_parameters": {
            "multivariate_test": "pillai",
            "follow_up_mode": "none",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        },
    }
    report = PreflightService().inspect(frame, raw)
    assert report.ready, [(item.code, item.message) for item in report.issues]
    result = AnalysisService().run(frame, AnalysisPlan(**raw))
    assert result.method.name == "manova"
    expected_effects = 2**order - 1
    assert len(result.omnibus_tests) == expected_effects


@pytest.mark.parametrize(
    ("method", "required"),
    [("oneway_manova", 1), ("twoway_manova", 2), ("threeway_manova", 3)],
)
def test_fixed_manova_missing_message_uses_exact_requirement(method: str, required: int) -> None:
    frame, factors = _frame(max(required, 1))
    raw = {
        "method": method,
        "dependent_variables": ["性状1", "性状2"],
        "fixed_factors": factors[: max(0, required - 1)],
    }
    report = PreflightService().inspect(frame, raw)
    assert not report.ready
    message = "；".join(item.message for item in report.issues)
    assert f"恰好需要 {required} 个固定/分类因素" in message


def test_twoway_manova_extra_candidate_requires_confirmation_then_runs_all_pairs() -> None:
    frame, factors = _frame(3)
    base = {
        "method": "twoway_manova",
        "dependent_variables": ["性状1", "性状2"],
        "fixed_factors": factors,
        "method_parameters": {
            "multivariate_test": "pillai",
            "follow_up_mode": "none",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        },
    }
    with pytest.raises(ValidationError, match="最多允许 2 个固定因素"):
        AnalysisPlan(**base)

    plan = AnalysisPlan(**base, factor_combinations_enabled=True)
    assert plan.factor_combination_min_order == 2
    assert plan.factor_combination_max_order == 2
    result = AnalysisService().run(frame, plan)
    assert isinstance(result, BatchAnalysisResult)
    assert set(result.summary_df["factor_combination"].dropna()) == {
        "因素1 × 因素2", "因素1 × 因素3", "因素2 × 因素3",
    }


def test_legacy_unified_manova_plan_migrates_by_saved_order() -> None:
    plan = AnalysisPlan(
        method="manova",
        dependent_variables=["性状1", "性状2"],
        fixed_factors=["因素1", "因素2", "因素3"],
        factor_combinations_enabled=True,
        method_parameters={"factor_model_order": "2"},
    )
    assert plan.method == "twoway_manova"
    assert "factor_model_order" not in plan.method_parameters
    assert plan.factor_combination_min_order == 2
    assert plan.factor_combination_max_order == 2
