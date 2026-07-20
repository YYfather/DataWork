from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
import pytest
from statsmodels.multivariate.manova import MANOVA as StatsmodelsMANOVA

from datawork.engine.manova import _safe_multivariate_results, manova


def _reference_frame(order: int, seed: int = 20260719) -> pd.DataFrame:
    rng = np.random.default_rng(seed + order)
    rows: list[dict[str, object]] = []
    for levels in product(["低", "高"], repeat=order):
        for _ in range(22):
            shift = sum((index + 1) * (level == "高") for index, level in enumerate(levels))
            latent = rng.normal()
            rows.append({
                **{f"F{index + 1}": level for index, level in enumerate(levels)},
                "Y1": 2.0 + shift + latent + rng.normal(scale=0.7),
                "Y2": 1.0 + 0.6 * shift + 0.4 * latent + rng.normal(scale=0.8),
                "Y3": 4.0 - 0.2 * shift + 0.2 * latent + rng.normal(scale=0.9),
            })
    return pd.DataFrame(rows)


@pytest.mark.parametrize("order", [1, 2, 3])
def test_safe_manova_matches_statsmodels_reference_values(order: int) -> None:
    frame = _reference_frame(order)
    rhs = " * ".join(f"C(F{index + 1}, Sum)" for index in range(order))
    model = StatsmodelsMANOVA.from_formula(f"Y1 + Y2 + Y3 ~ {rhs}", data=frame)

    expected = model.mv_test().results
    actual = _safe_multivariate_results(model)

    assert set(actual) == {name for name in expected if name != "Intercept"}
    for effect, payload in actual.items():
        actual_table = payload["stat"].astype(float).sort_index()
        expected_table = expected[effect]["stat"].astype(float).sort_index()
        pd.testing.assert_frame_equal(actual_table, expected_table, rtol=1e-11, atol=1e-12)


@pytest.mark.parametrize("order", [1, 2, 3])
def test_public_manova_returns_every_factorial_effect_with_finite_values(order: int) -> None:
    frame = _reference_frame(order)
    factors = [f"F{index + 1}" for index in range(order)]

    result = manova(
        frame,
        ["Y1", "Y2", "Y3"],
        factors,
        parameters={
            "multivariate_test": "all",
            "follow_up_mode": "none",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        },
    )

    assert result is not None
    assert len(result.omnibus_tests) == (2**order - 1) * 4
    for test in result.omnibus_tests:
        assert np.isfinite(test.statistic_value)
        assert np.isfinite(test.df_num) and test.df_num > 0
        assert np.isfinite(test.df_den) and test.df_den > 0
        assert np.isfinite(test.f_value) and test.f_value >= 0
        assert 0 <= test.p_value <= 1
