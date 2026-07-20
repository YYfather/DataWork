import numpy as np
import pandas as pd

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan


def test_concise_mode_filters_professional_parameters_server_side():
    plan = AnalysisPlan.model_validate({
        "interface_mode": "concise",
        "dependent_variables": ["y"],
        "fixed_factors": ["group"],
        "method": "oneway_anova",
        "alpha": 0.2,
        "ss_type": 1,
        "factor_combinations_enabled": True,
        "factor_combination_order": 1,
        "cross_model_p_adjust": "fdr_bh",
        "calibration_enabled": True,
        "calibration_columns": ["y"],
        "diagnostic_plots": True,
    })
    assert plan.alpha == 0.05
    assert plan.ss_type == 3
    assert plan.factor_combinations_enabled is False
    assert plan.factor_combination_order is None
    assert plan.cross_model_p_adjust == "fdr_bh"
    assert plan.combination_p_adjust == "fdr_bh"
    assert plan.calibration_enabled is False
    assert plan.calibration_columns == []
    assert plan.diagnostic_plots is False


def test_legacy_combination_adjustment_migrates_to_cross_model_field():
    plan = AnalysisPlan.model_validate({
        "interface_mode": "concise",
        "dependent_variables": ["y"],
        "fixed_factors": ["group"],
        "method": "oneway_anova",
        "combination_p_adjust": "bonferroni",
    })
    assert plan.cross_model_p_adjust == "bonferroni"
    assert plan.combination_p_adjust == "bonferroni"


def test_professional_calibration_is_applied_and_recorded():
    frame = pd.DataFrame({
        "group": ["A"] * 4 + ["B"] * 4,
        "y": [10.0, 11.0, 12.0, 13.0, 20.0, 21.0, 22.0, 23.0],
    })
    plan = AnalysisPlan.model_validate({
        "interface_mode": "professional",
        "dependent_variables": ["y"],
        "fixed_factors": ["group"],
        "method": "oneway_anova",
        "calibration_enabled": True,
        "calibration_method": "zscore",
        "calibration_columns": ["y"],
    })
    calibrated, log = AnalysisService._apply_calibration(frame, plan)
    assert np.isclose(calibrated["y"].mean(), 0.0)
    assert np.isclose(calibrated["y"].std(ddof=1), 1.0)
    assert log[0]["operation"] == "calibration"
    assert "基准特征空间" in log[0]["purpose"]
