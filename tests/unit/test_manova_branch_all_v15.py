from __future__ import annotations

import pandas as pd

from datawork.core.method_registry import get_method
from datawork.engine.manova import manova


def _null_two_factor_frame() -> pd.DataFrame:
    response_1 = [1.0, 2.0, 4.0, 7.0, 11.0, 16.0]
    response_2 = [2.0, 5.0, 3.0, 9.0, 6.0, 12.0]
    rows = []
    for factor_a in ("a1", "a2"):
        for factor_b in ("b1", "b2"):
            for y1, y2 in zip(response_1, response_2):
                rows.append({"A": factor_a, "B": factor_b, "y1": y1, "y2": y2})
    return pd.DataFrame(rows)


def _run(scope: str):
    return manova(
        _null_two_factor_frame(),
        ["y1", "y2"],
        ["A", "B"],
        parameters={
            "multivariate_test": "wilks",
            "primary_multivariate_test": "wilks",
            "follow_up_mode": "all",
            "follow_up_ss_type": 3,
            "follow_up_correction": "none",
            "posthoc_methods": ["tukey"],
            "simple_effect_correction": "none",
            "posthoc_scope": scope,
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
        },
    )


def test_branch_all_compares_both_marginal_factors_when_interaction_is_not_significant() -> None:
    gated = _run("significance_gated")
    branched = _run("branch_all")

    assert gated is not None and branched is not None
    assert not gated.contrasts
    labels = [item.contrast for item in branched.contrasts]
    assert len(labels) == 4
    assert any("[y1 | A]" in item for item in labels)
    assert any("[y1 | B]" in item for item in labels)
    assert any("[y2 | A]" in item for item in labels)
    assert any("[y2 | B]" in item for item in labels)
    assert branched.data_snapshot["posthoc_scope"] == "branch_all"


def test_branch_all_compares_both_simple_effect_directions_when_interaction_is_significant() -> None:
    rows = []
    for factor_a in ("a1", "a2"):
        for factor_b in ("b1", "b2"):
            for replicate in range(12):
                interaction = 10.0 if factor_a == "a2" and factor_b == "b2" else 0.0
                rows.append({
                    "A": factor_a,
                    "B": factor_b,
                    "y1": interaction + replicate * 0.03,
                    "y2": interaction * 0.7 + (replicate % 4) * 0.07,
                })
    result = manova(
        pd.DataFrame(rows), ["y1", "y2"], ["A", "B"],
        parameters={
            "multivariate_test": "wilks", "primary_multivariate_test": "wilks",
            "follow_up_mode": "all", "follow_up_ss_type": 3,
            "follow_up_correction": "none", "posthoc_methods": ["tukey"],
            "simple_effect_correction": "none", "posthoc_scope": "branch_all",
            "covariance_test": False, "normality_test": False,
            "correlation_diagnostics": False,
        },
    )
    assert result is not None
    labels = [item.contrast for item in result.contrasts]
    assert len(labels) == 8
    assert sum(" A @ B=" in item for item in labels) == 4
    assert sum(" B @ A=" in item for item in labels) == 4


def test_manova_registry_exposes_branch_all_without_changing_default() -> None:
    for method in ("oneway_manova", "twoway_manova", "threeway_manova", "multifactor_manova"):
        parameter = next(
            item for item in get_method(method).parameters if item.key == "posthoc_scope"
        )
        assert parameter.default == "significance_gated"
        assert {value for value, _label in parameter.options} == {
            "significance_gated",
            "branch_all",
        }
