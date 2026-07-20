from itertools import product

import numpy as np
import pandas as pd

from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import get_method
from datawork.engine.manova import manova
from datawork.engine.multiway_anova import multiway_anova


def _four_factor_frame() -> pd.DataFrame:
    rng = np.random.default_rng(2026)
    rows: list[dict[str, object]] = []
    for levels in product([0, 1], repeat=4):
        for _ in range(6):
            signal = 1.1 * levels[0] + 0.7 * levels[1] + 0.45 * levels[0] * levels[1]
            rows.append({
                **{f"F{index + 1}": str(level) for index, level in enumerate(levels)},
                "y1": signal + rng.normal(scale=0.5),
                "y2": 0.6 * signal + rng.normal(scale=0.6),
            })
    return pd.DataFrame(rows)


def test_multifactor_registry_exposes_only_orders_four_through_eight():
    for name in ("multifactor_anova", "multifactor_manova"):
        method = get_method(name)
        order = next(parameter for parameter in method.parameters if parameter.key == "factor_model_order")
        assert method.min_fixed_factors == 4
        assert method.max_fixed_factors == 8
        assert order.default == "4"
        assert [value for value, _ in order.options] == ["4", "5", "6", "7", "8"]


def test_four_factor_anova_fits_full_factorial_model():
    frame = _four_factor_frame()
    result = multiway_anova(frame, "y1", ["F1", "F2", "F3", "F4"], diagnostic_plots=False)
    assert result.method.name == "multifactor_anova"
    assert result.data_snapshot["factor_count"] == 4
    assert result.data_snapshot["observed_cells"] == 16
    assert len(result.omnibus_tests) == 15
    assert any(item.effect == "F1 × F2 × F3 × F4" for item in result.omnibus_tests)
    assert result.data_snapshot["model_rank"] == result.data_snapshot["model_columns"]


def test_four_factor_manova_fits_full_factorial_joint_response():
    frame = _four_factor_frame()
    result = manova(
        frame, ["y1", "y2"], ["F1", "F2", "F3", "F4"],
        parameters={
            "multivariate_test": "pillai",
            "primary_multivariate_test": "pillai",
            "follow_up_mode": "none",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        },
    )
    assert result is not None
    assert result.method.name == "manova"
    assert result.data_snapshot["factor_count"] == 4
    assert len(result.omnibus_tests) == 15
    assert any(item.effect == "F1 × F2 × F3 × F4" for item in result.omnibus_tests)


def test_preflight_requires_factor_count_to_match_selected_order():
    frame = _four_factor_frame()
    report = PreflightService().inspect(frame, {
        "dependent_variables": ["y1"],
        "fixed_factors": ["F1", "F2", "F3", "F4"],
        "method": "multifactor_anova",
        "method_parameters": {"factor_model_order": 5},
        "alpha": 0.05,
        "ss_type": 3,
    })
    assert report.ready is False
    issue = next(item for item in report.issues if item.code == "factor_order_mismatch")
    assert "必须恰好选择 5 个" in issue.message
