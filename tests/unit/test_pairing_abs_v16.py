from __future__ import annotations

import pandas as pd
import pytest

from datawork.application.analysis_service import AnalysisService
from datawork.core.formula import (
    UnsafeFormulaError,
    evaluate_formula,
    normalize_absolute_value_syntax,
)
from datawork.core.plan import AnalysisPlan
from test_pairing_workflow_v15 import _frame, _plan


def test_abs_is_available_only_when_explicitly_whitelisted() -> None:
    frame = pd.DataFrame({"x": [-3.0, 2.0], "y": [1.0, 5.0]})
    result = evaluate_formula(
        frame,
        "|[x] - [y]|",
        allowed_columns=["x", "y"],
        require_brackets=True,
        basic_arithmetic_only=True,
        allow_abs=True,
    )
    assert result.tolist() == [4.0, 3.0]
    with pytest.raises(UnsafeFormulaError, match="abs"):
        evaluate_formula(
            frame,
            "abs([x])",
            allowed_columns=["x"],
            require_brackets=True,
            basic_arithmetic_only=True,
        )


@pytest.mark.parametrize(
    "formula",
    [
        "abs()",
        "abs([x], [y])",
        "abs(x=[x])",
        "max([x])",
        "__import__('os')",
        "abs([x].values)",
        "abs([x][0])",
        "abs([x]) ** 2",
        "abs([x]) % 2",
    ],
)
def test_abs_whitelist_rejects_other_functions_and_invalid_calls(formula: str) -> None:
    frame = pd.DataFrame({"x": [-1.0], "y": [2.0]})
    with pytest.raises(UnsafeFormulaError):
        evaluate_formula(
            frame,
            formula,
            allowed_columns=["x", "y"],
            require_brackets=True,
            basic_arithmetic_only=True,
            allow_abs=True,
        )


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("abs([x])", [3.0, 2.0, float("nan")]),
        ("abs([y])", [1.0, 5.0, 4.0]),
        ("abs([x] - [y])", [4.0, 3.0, float("nan")]),
        ("abs(([x] - [y]) / 2)", [2.0, 1.5, float("nan")]),
        ("|[x] - [y]|", [4.0, 3.0, float("nan")]),
    ],
)
def test_abs_variants_preserve_missing_values(
    formula: str,
    expected: list[float],
) -> None:
    frame = pd.DataFrame({"x": [-3.0, 2.0, None], "y": [1.0, 5.0, -4.0]})
    result = evaluate_formula(
        frame,
        formula,
        allowed_columns=["x", "y"],
        require_brackets=True,
        basic_arithmetic_only=True,
        allow_abs=True,
    )
    pd.testing.assert_series_equal(
        result.reset_index(drop=True),
        pd.Series(expected, dtype="float64"),
        check_names=False,
    )


def test_multiple_non_nested_absolute_bars_are_normalized() -> None:
    assert normalize_absolute_value_syntax("|[x]| + |[y] - 1|") == (
        "abs([x]) + abs([y] - 1)"
    )


@pytest.mark.parametrize("formula", ["|[x]", "[x]|", "||", "|   |"])
def test_invalid_absolute_bars_are_rejected(formula: str) -> None:
    with pytest.raises(UnsafeFormulaError, match="竖线|不能为空"):
        normalize_absolute_value_syntax(formula)


def test_pair_formula_normalizes_vertical_bars_and_calculates_absolute_difference() -> None:
    payload = _plan().model_dump(mode="json")
    payload["pairing"]["derived_columns"] = [{
        "id": "absolute-difference",
        "name": "AbsoluteDelta",
        "source_column": "metric_1",
        "formula": "|[对照值] - [处理值]|",
        "unit": "绝对量（保留原始尺度）",
        "decimal_places": 8,
    }]
    payload["dependent_variables"] = ["AbsoluteDelta"]
    payload["dependent_variable_groups"] = []
    payload["method"] = "twoway_anova"
    payload["method_parameters"] = {}
    plan = AnalysisPlan.model_validate(payload)
    assert plan.pairing is not None
    assert plan.pairing.derived_columns[0].formula == "abs([对照值] - [处理值])"
    frame, logs, warnings = AnalysisService.prepare_frame(_frame(), plan)
    assert set(frame["AbsoluteDelta"]) == {10.0, 13.0}
    pairing_log = next(item for item in logs if item["operation"] == "pairing")
    assert pairing_log["generated_columns"][0]["unit"] == "绝对量（保留原始尺度）"
    assert warnings == []


def test_unbalanced_absolute_value_bars_are_rejected_by_pairing_plan() -> None:
    payload = _plan().model_dump(mode="json")
    payload["pairing"]["derived_columns"][0]["formula"] = "|[处理值] - [对照值]"
    with pytest.raises(ValueError, match="竖线必须成对"):
        AnalysisPlan.model_validate(payload)


def test_pair_abs_rounding_and_preflight_audit_are_stable() -> None:
    payload = _plan().model_dump(mode="json")
    payload["pairing"]["derived_columns"] = [{
        "id": "rounded-absolute",
        "name": "RoundedAbsolute",
        "source_column": "metric_1",
        "formula": "abs(([处理值] - [对照值]) / 3)",
        "unit": "",
        "decimal_places": 2,
    }]
    payload["dependent_variables"] = ["RoundedAbsolute"]
    payload["dependent_variable_groups"] = []
    payload["method"] = "twoway_anova"
    payload["method_parameters"] = {}
    frame, logs, _warnings = AnalysisService.prepare_frame(
        _frame(),
        AnalysisPlan.model_validate(payload),
    )
    assert set(frame["RoundedAbsolute"]) == {3.33, 4.33}
    generated = next(item for item in logs if item["operation"] == "pairing")[
        "generated_columns"
    ][0]
    assert generated == {
        "name": "RoundedAbsolute",
        "source_column": "metric_1",
        "formula": "abs(([处理值] - [对照值]) / 3)",
        "unit": "",
        "decimal_places": 2,
        "control_storage_column": "__dw_control_value_1",
        "missing_result_count": 0,
        "invalid_operation_count": 0,
    }


def test_v15_pair_formulas_remain_byte_for_byte_compatible() -> None:
    plan = _plan()
    before = [
        "[对照值]",
        "[处理值] - [对照值]",
        "([对照值])",
        "([处理值] - [对照值]) / 1",
    ]
    assert plan.pairing is not None
    assert [item.formula for item in plan.pairing.derived_columns] == before
    frame, _logs, warnings = AnalysisService.prepare_frame(_frame(), plan)
    assert set(frame["Delta1"]) == {10.0, 13.0}
    assert warnings == []
