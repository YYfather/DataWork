from __future__ import annotations

import pandas as pd
import pytest

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan
from datawork.core.task_expansion import outcome_tasks


def _frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    source = 0
    for year in (2024, 2025):
        for variety in ("V1", "V2"):
            for mode in ("M1", "M2"):
                for treatment, control in (("T1", "CK1"), ("T2", "CK2")):
                    for rep in range(3):
                        source += 1
                        rows.append({
                            "year": year,
                            "variety": variety,
                            "mode": mode,
                            "spray": treatment,
                            "sample_id": f"{year}-{variety}-{mode}-{treatment[-1]}-{rep}",
                            "metric_1": 20 + rep + (treatment == "T2") * 3,
                            "metric_2": 40 + rep + (treatment == "T2") * 2,
                            "raw_extra": 2 + rep,
                            "source": source,
                        })
                        source += 1
                        rows.append({
                            "year": year,
                            "variety": variety,
                            "mode": mode,
                            "spray": control,
                            "sample_id": f"{year}-{variety}-{mode}-{control[-1]}-{rep}",
                            "metric_1": 10 + rep,
                            "metric_2": 30 + rep,
                            "raw_extra": 100 + rep,
                            "source": source,
                        })
    return pd.DataFrame(rows)


def _plan(**updates: object) -> AnalysisPlan:
    payload: dict[str, object] = {
        "interface_mode": "professional",
        "method": "twoway_manova",
        "dependent_variables": ["NDR1", "Delta1", "NDR2", "Delta2"],
        "dependent_variable_groups": [
            {"name": "time-1", "dependent_variables": ["NDR1", "Delta1"]},
            {"name": "time-2", "dependent_variables": ["NDR2", "Delta2"]},
        ],
        "fixed_factors": ["variety", "spray"],
        "split_by": ["year"],
        "pairing": {
            "group_column": "spray",
            "mappings": [
                {"treatment": "T1", "control": "CK1"},
                {"treatment": "T2", "control": "CK2"},
            ],
            "match_columns": ["year", "variety", "mode"],
            "pair_id_column": None,
            "derived_columns": [
                {"id": "ndr1", "name": "NDR1", "source_column": "metric_1", "formula": "[对照值]", "unit": "百分点"},
                {"id": "delta1", "name": "Delta1", "source_column": "metric_1", "formula": "[处理值] - [对照值]", "unit": "百分点"},
                {"id": "ndr2", "name": "NDR2", "source_column": "metric_2", "formula": "([对照值])", "unit": "百分点"},
                {"id": "delta2", "name": "Delta2", "source_column": "metric_2", "formula": "([处理值] - [对照值]) / 1", "unit": "百分点"},
            ],
        },
        "method_parameters": {"follow_up_mode": "none"},
    }
    payload.update(updates)
    return AnalysisPlan.model_validate(payload)


def test_pairing_uses_import_order_and_builds_treatment_centric_frame() -> None:
    frame, logs, warnings = AnalysisService.prepare_frame(_frame(), _plan())

    assert len(frame) == 48
    assert not warnings
    assert frame["spray"].isin(["T1", "T2"]).all()
    assert (frame["NDR1"] == frame["metric_1"] - frame["Delta1"]).all()
    assert set(frame["Delta1"]) == {10.0, 13.0}
    audit = next(item for item in logs if item["operation"] == "pairing")
    assert audit["input_rows"] == 96
    assert audit["pairing_group_count"] == 16
    assert audit["successful_pairs"] == 48
    assert audit["pairing_order"] == "按匹配组内原始导入行顺序"


def test_pairing_allows_ordinary_custom_column_to_use_pair_output() -> None:
    plan = _plan(
        dependent_variables=["NDR1", "DeltaPlusRaw"],
        dependent_variable_groups=[
            {"name": "combined", "dependent_variables": ["NDR1", "DeltaPlusRaw"]}
        ],
        derived_columns=[{
            "name": "DeltaPlusRaw",
            "formula": "[Delta1] + [raw_extra]",
            "source_columns": ["Delta1", "raw_extra"],
        }],
    )
    frame, _, _ = AnalysisService.prepare_frame(_frame(), plan)
    assert (frame["DeltaPlusRaw"] == frame["Delta1"] + frame["raw_extra"]).all()


def test_pairing_can_use_explicit_sample_id_independent_of_control_row_order() -> None:
    frame = _frame()
    treatments = frame.loc[frame["spray"].str.startswith("T")]
    controls = frame.loc[frame["spray"].str.startswith("CK")].sort_values(
        ["year", "variety", "mode", "spray", "sample_id"],
        ascending=[True, True, True, True, False],
    )
    reordered = pd.concat([treatments, controls], ignore_index=True)
    payload = _plan().model_dump(mode="json")
    payload["pairing"]["pair_id_column"] = "sample_id"
    paired, logs, _warnings = AnalysisService.prepare_frame(
        reordered, AnalysisPlan.model_validate(payload)
    )
    for _, row in paired.iterrows():
        control_row = reordered.iloc[int(row["__dw_control_source_row"])]
        assert row["sample_id"] == control_row["sample_id"]
    audit = next(item for item in logs if item["operation"] == "pairing")
    assert audit["pairing_order"] == "显式样本 ID：sample_id"


def test_pairing_mismatch_stops_the_whole_analysis() -> None:
    broken = _frame().drop(index=[1]).reset_index(drop=True)
    with pytest.raises(ValueError, match="样本数不一致"):
        AnalysisService.prepare_frame(broken, _plan())


def test_unassigned_split_levels_are_excluded_before_pair_validation() -> None:
    frame = _frame()
    broken_2025 = frame.drop(index=frame[(frame["year"] == 2025) & (frame["spray"] == "CK1")].index[:1])
    plan = _plan(
        split_rules=[{
            "column": "year",
            "kind": "categorical",
            "groups": [{"label": "only-2024", "values": ["2024"]}],
        }],
    )
    paired, logs, _ = AnalysisService.prepare_frame(broken_2025, plan)
    assert len(paired) == 24
    audit = next(item for item in logs if item["operation"] == "pairing")
    assert audit["split_scope_excluded_treatment_rows"] == 24


def test_joint_outcome_groups_expand_in_stable_order() -> None:
    tasks = outcome_tasks(_plan())
    assert [(item.name, item.variables) for item in tasks] == [
        ("time-1", ("NDR1", "Delta1")),
        ("time-2", ("NDR2", "Delta2")),
    ]


def test_pair_output_is_rejected_from_non_dependent_roles() -> None:
    with pytest.raises(ValueError, match="只能作为因变量"):
        _plan(covariates=["Delta1"])


def test_pair_formula_rejects_power_operator() -> None:
    plan = _plan()
    payload = plan.model_dump(mode="json")
    payload["pairing"]["derived_columns"][1]["formula"] = "[处理值] ** 2 - [对照值]"
    plan_with_power = AnalysisPlan.model_validate(payload)
    with pytest.raises(ValueError, match="基础四则运算"):
        AnalysisService.prepare_frame(_frame(), plan_with_power)
