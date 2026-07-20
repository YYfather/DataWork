from __future__ import annotations

import numpy as np
import pandas as pd

from datawork.application.executors import get_executor
from datawork.core.plan import AnalysisPlan
from datawork.engine.manova import manova


def _two_factor_frame(seed: int = 20260718) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for treatment in ["CK", "T"]:
        for variety in ["V1", "V2"]:
            for _ in range(24):
                treatment_shift = 0.9 if treatment == "T" else 0.0
                variety_shift = 0.4 if variety == "V2" else 0.0
                interaction = 0.35 if treatment == "T" and variety == "V2" else 0.0
                latent = rng.normal()
                rows.append({
                    "treatment": treatment,
                    "variety": variety,
                    "height": 10 + treatment_shift + variety_shift + interaction + latent + rng.normal(scale=0.45),
                    "biomass": 5 + 0.7 * treatment_shift + 0.5 * variety_shift + 0.4 * latent + rng.normal(scale=0.55),
                })
    return pd.DataFrame(rows)


def test_two_factor_manova_outputs_all_four_statistics_for_each_effect() -> None:
    result = manova(
        _two_factor_frame(),
        ["height", "biomass"],
        ["treatment", "variety"],
        parameters={"multivariate_test": "all"},
    )

    assert result is not None
    assert result.method.label_zh == "2因素多元方差分析（MANOVA）"
    assert result.method.formula == "height + biomass ~ treatment * variety"
    assert len(result.omnibus_tests) == 12
    assert {item.effect for item in result.omnibus_tests} == {
        "treatment",
        "variety",
        "treatment × variety",
    }
    assert {item.statistic_name for item in result.omnibus_tests} == {
        "Pillai 轨迹",
        "Wilks' Lambda",
        "Hotelling–Lawley 轨迹",
        "Roy 最大根",
    }
    assert all(item.statistic_value is not None for item in result.omnibus_tests)
    assert all(np.isfinite(item.f_value) and np.isfinite(item.p_value) for item in result.omnibus_tests)
    assert all(item.effect != "Intercept" for item in result.omnibus_tests)


def test_manova_statistic_can_be_selected_through_analysis_plan() -> None:
    plan = AnalysisPlan(
        method="twoway_manova",
        dependent_variables=["height", "biomass"],
        fixed_factors=["treatment", "variety"],
        method_parameters={"multivariate_test": "pillai"},
    )
    result = get_executor("twoway_manova")(_two_factor_frame(), plan)

    assert len(result.omnibus_tests) == 3
    assert {item.statistic_name for item in result.omnibus_tests} == {"Pillai 轨迹"}
    assert result.data_snapshot["selected_multivariate_tests"] == ["pillai"]


def test_numeric_coded_factor_is_forced_to_categorical() -> None:
    rng = np.random.default_rng(19)
    frame = pd.DataFrame({
        "dose": np.repeat([1, 2, 3], 30),
        "y1": np.concatenate([rng.normal(0, 1, 30), rng.normal(0.5, 1, 30), rng.normal(1.0, 1, 30)]),
        "y2": np.concatenate([rng.normal(0, 1, 30), rng.normal(-0.3, 1, 30), rng.normal(0.4, 1, 30)]),
    })
    result = manova(frame, ["y1", "y2"], ["dose"], parameters={"multivariate_test": "wilks"})

    assert result is not None
    assert len(result.omnibus_tests) == 1
    test = result.omnibus_tests[0]
    assert test.effect == "dose"
    assert test.statistic_name == "Wilks' Lambda"
    # 3 水平分类因素 × 2 个因变量，对应多元检验分子自由度为 4；
    # 若错误地按连续变量处理，分子自由度会是 2。
    assert test.df_num == 4.0


def test_manova_rejects_true_repeated_or_over_factorized_shape_at_engine_boundary() -> None:
    result = manova(
        _two_factor_frame(),
        ["height", "biomass"],
        ["treatment", "variety", "unsupported_third_factor"],
    )
    assert result is None


def test_exact_zero_interaction_is_reported_instead_of_crashing() -> None:
    rows: list[dict[str, object]] = []
    for treatment in ["CK", "T"]:
        for variety in ["V1", "V2"]:
            for index in range(12):
                t = 1 if treatment == "T" else 0
                v = 1 if variety == "V2" else 0
                # 完全加性、各组合共享相同残差结构，因此交互效应精确为零。
                rows.append({
                    "treatment": treatment,
                    "variety": variety,
                    "y1": index + 2 * t + v + (index % 3) * 0.17,
                    "y2": (index % 5) * 0.8 + index * 0.13 + t - 0.4 * v + (index % 2) * 0.11,
                })
    result = manova(
        pd.DataFrame(rows),
        ["y1", "y2"],
        ["treatment", "variety"],
        parameters={"multivariate_test": "all"},
    )

    assert result is not None
    interaction_rows = [item for item in result.omnibus_tests if item.effect == "treatment × variety"]
    assert len(interaction_rows) == 4
    assert all(np.isclose(item.f_value, 0.0) for item in interaction_rows)
    assert all(np.isclose(item.p_value, 1.0) for item in interaction_rows)
