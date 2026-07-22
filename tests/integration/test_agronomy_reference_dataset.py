from __future__ import annotations

from pathlib import Path

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan
from scripts.compare_r_reference import _prepare_agronomy_frame


REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "r" / "agronomy_example_2.csv"


def test_agronomy_reference_dataset_runs_split_anova_and_manova() -> None:
    frame = _prepare_agronomy_frame(REFERENCE)
    outcomes = [f"{kind}{day}" for day in ("7", "14", "21") for kind in ("NDR", "Delta")]

    assert len(frame) == 108
    assert frame.groupby("year").size().to_dict() == {"2024": 54, "2025": 54}
    assert frame[outcomes].notna().all().all()

    anova = AnalysisService().execute(
        frame,
        AnalysisPlan(
            interface_mode="professional", method="twoway_anova",
            dependent_variables=outcomes, fixed_factors=["variety", "spray"], split_by=["year"],
            ss_type=3, method_parameters={"posthoc_methods": ["none"]}, diagnostic_plots=False,
        ),
    ).result
    assert len(anova.results) == 12
    assert all(not item.error and item.result is not None for item in anova.results)
    assert sum(len(item.result.omnibus_tests) for item in anova.results if item.result) == 36

    manova = AnalysisService().execute(
        frame,
        AnalysisPlan(
            interface_mode="professional", method="twoway_manova",
            dependent_variables=["NDR7", "Delta7"], fixed_factors=["variety", "spray"], split_by=["year"],
            method_parameters={
                "multivariate_test": "wilks", "primary_multivariate_test": "wilks",
                "follow_up_mode": "none", "covariance_test": False,
                "normality_test": False, "correlation_diagnostics": False,
            },
            diagnostic_plots=False,
        ),
    ).result
    assert len(manova.results) == 2
    assert all(not item.error and item.result is not None for item in manova.results)
    tests = [test for item in manova.results if item.result for test in item.result.omnibus_tests]
    assert len(tests) == 6
    assert {test.statistic_name for test in tests} == {"Wilks' Lambda"}
