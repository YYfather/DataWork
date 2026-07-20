from __future__ import annotations

import numpy as np
import pandas as pd

from datawork.application.preflight_service import PreflightService
from datawork.core.plan import AnalysisPlan
from datawork.core.validation import validate_plan_dataframe
from datawork.engine.advanced_methods import mixed_anova
from datawork.engine.manova import manova
from datawork.engine.oneway_anova import oneway_anova


def factorial_frame(seed: int = 19) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for a in ("A0", "A1"):
        for b in ("B0", "B1"):
            for c in ("C0", "C1"):
                for replicate in range(7):
                    shift = 0.8 * (a == "A1") + 0.35 * (b == "B1")
                    rows.append({
                        "A": a, "B": b, "C": c, "rep": replicate,
                        "y1": shift + rng.normal(scale=0.6),
                        "y2": 0.5 * shift + rng.normal(scale=0.7),
                        "y3": -0.2 * shift + rng.normal(scale=0.8),
                    })
    return pd.DataFrame(rows)


def test_manova_supports_one_two_three_factor_and_followups():
    frame = factorial_frame()
    for factors in (["A"], ["A", "B"], ["A", "B", "C"]):
        result = manova(
            frame, ["y1", "y2", "y3"], list(factors),
            parameters={
                "follow_up_mode": "all", "follow_up_ss_type": "3",
                "follow_up_correction": "holm", "posthoc_method": "holm",
                "covariance_test": True, "normality_test": True,
                "correlation_diagnostics": True,
            },
        )
        assert result.data_snapshot["factor_count"] == len(factors)
        assert result.follow_up_tests
        assert {item.statistic_name for item in result.omnibus_tests} == {
            "Pillai 轨迹", "Wilks' Lambda", "Hotelling–Lawley 轨迹", "Roy 最大根"
        }
        assert any(item.test_name.startswith("Box") for item in result.diagnostics)


def test_duncan_is_available_but_marked_liberal():
    frame = factorial_frame()
    result = oneway_anova(frame, "y1", "A", posthoc_method="duncan")
    assert any("Duncan" in warning for warning in result.warnings)


def mixed_frame(seed: int = 31) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for group in ("G0", "G1"):
        for index in range(6):
            subject = f"{group}-{index}"
            random_intercept = rng.normal(scale=0.35)
            for time_index, time in enumerate(("T0", "T1", "T2")):
                rows.append({
                    "id": subject, "group": group, "time": time,
                    "y": random_intercept + 0.5 * (group == "G1") + 0.2 * time_index + rng.normal(scale=0.4),
                })
    return pd.DataFrame(rows)


def test_mixed_anova_auto_selects_classical_then_mixedlm():
    frame = mixed_frame()
    classical = mixed_anova(
        frame, "y", "id", "time", ["group"], 0.05,
        {"analysis_mode": "auto", "posthoc_method": "holm"},
    )
    assert classical.data_snapshot["analysis_mode"] == "classical"
    incomplete = frame[~((frame["id"] == "G1-5") & (frame["time"] == "T2"))].copy()
    generalized = mixed_anova(
        incomplete, "y", "id", "time", ["group"], 0.05,
        {"analysis_mode": "auto", "posthoc_method": "holm", "emm_scope": "within"},
    )
    assert generalized.data_snapshot["analysis_mode"] == "mixedlm"
    assert generalized.primary_tests
    assert any("自动使用线性混合效应模型" in item for item in generalized.warnings)


def test_preflight_returns_structured_design_review():
    frame = factorial_frame()
    plan = AnalysisPlan(
        method="threeway_manova", dependent_variables=["y1", "y2", "y3"],
        fixed_factors=["A", "B", "C"],
        method_parameters={"follow_up_mode": "all", "posthoc_method": "holm"},
    )
    assert validate_plan_dataframe(plan, frame).valid
    report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
    assert report.ready
    assert report.design_review["status"] in {"ready", "attention"}
    assert report.design_review["engine"] == "3 因素完整析因 MANOVA"
    labels = {item["label"] for item in report.design_review["metrics"]}
    assert {"最小单元重复", "近似残差自由度", "联合因变量数"} <= labels
