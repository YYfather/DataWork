from __future__ import annotations

from pathlib import Path

from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from scripts.compare_r_reference import _agronomy_plan, _load_agronomy_source, _prepare_agronomy_frame


REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "r" / "agronomy_example_2.csv"


def test_agronomy_reference_dataset_runs_split_anova_and_manova() -> None:
    source = _load_agronomy_source(REFERENCE)
    frame = _prepare_agronomy_frame(REFERENCE)
    outcomes = [f"{kind}{day}" for day in ("7", "14", "21") for kind in ("NDR", "Delta")]

    assert len(frame) == 108
    assert frame.groupby("year").size().to_dict() == {"2024": 54, "2025": 54}
    assert frame[outcomes].notna().all().all()

    anova = AnalysisService().execute(
        source, _agronomy_plan("twoway_anova"),
    ).result
    assert len(anova.results) == 12
    assert all(not item.error and item.result is not None for item in anova.results)
    assert sum(len(item.result.omnibus_tests) for item in anova.results if item.result) == 36

    execution = AnalysisService().execute(
        source, _agronomy_plan("twoway_manova"),
    )
    manova = execution.result
    serialized = AnalysisService.serialize_execution(execution)
    assert serialized["plan"]["pairing"]["group_column"] == "spray"
    assert [item["name"] for item in serialized["plan"]["dependent_variable_groups"]] == ["7d", "14d", "21d"]
    pairing_logs = [item for item in serialized["provenance"]["cleaning_log"] if item.get("operation") == "pairing"]
    assert len(pairing_logs) == 1
    assert pairing_logs[0]["input_rows"] == 216
    assert pairing_logs[0]["successful_pairs"] == 108
    assert pairing_logs[0]["pairing_group_count"] == 36
    assert len(manova.results) == 6
    assert all(not item.error and item.result is not None for item in manova.results)
    tests = [test for item in manova.results if item.result for test in item.result.omnibus_tests]
    assert len(tests) == 18
    assert {test.statistic_name for test in tests} == {"Wilks' Lambda"}

    preflight = PreflightService().inspect(
        source, _agronomy_plan("twoway_manova").model_dump(mode="json")
    )
    assert preflight.ready
    assert preflight.pairing_summary["input_rows"] == 216
    assert preflight.pairing_summary["pairing_group_count"] == 36
    assert preflight.pairing_summary["successful_pairs"] == 108
    assert preflight.task_hierarchy["task_count"] == 6
    assert [item["name"] for item in preflight.task_hierarchy["outcome_groups"]] == ["7d", "14d", "21d"]
    assert {item["rows"] for item in preflight.batch_summary["groups"]} == {54}
