import pandas as pd
import pytest

from datawork.core.formula import UnsafeFormulaError, apply_derived_columns, evaluate_formula
from datawork.core.plan import DerivedColumn


def test_formula_supports_non_identifier_column_names():
    df = pd.DataFrame({"7d脱叶率": [10, 20], "14d 脱叶率": [30, 50]})
    result = evaluate_formula(df, "(7d脱叶率 + 14d 脱叶率) / 2")
    assert result.tolist() == [20, 35]


def test_formula_rejects_function_calls_and_attribute_access():
    df = pd.DataFrame({"x": [1, 2]})
    with pytest.raises(UnsafeFormulaError):
        evaluate_formula(df, "__import__('os').system('echo unsafe')")
    with pytest.raises(UnsafeFormulaError):
        evaluate_formula(df, "x.__class__")


def test_plan_derived_column_does_not_overwrite_existing_column():
    df = pd.DataFrame({"x": [1, 2]})
    with pytest.raises(ValueError, match="不能覆盖原始列"):
        apply_derived_columns(df, [DerivedColumn(name="x", formula="[x] + 1", source_columns=["x"])])


def test_plan_derived_column_uses_bracketed_original_numeric_columns():
    frame = pd.DataFrame({"初期 值": [1.0, 2.0, None], "末期值": [3.0, 6.0, 8.0]})
    definitions = [DerivedColumn(
        name="增长量",
        formula="([末期值] - [初期 值]) * 2",
        source_columns=["末期值", "初期 值"],
    )]
    result, log, warnings = apply_derived_columns(frame, definitions)
    assert result["增长量"].tolist()[:2] == [4.0, 8.0]
    assert pd.isna(result["增长量"].iloc[2])
    assert log[0]["missing_result_count"] == 1
    assert warnings == []


def test_plan_derived_column_turns_division_by_zero_into_missing():
    frame = pd.DataFrame({"x": [1.0, 2.0], "denominator": [0.0, 2.0]})
    result, log, warnings = apply_derived_columns(frame, [DerivedColumn(
        name="ratio", formula="[x] / [denominator]", source_columns=["x", "denominator"],
    )])
    assert pd.isna(result["ratio"].iloc[0])
    assert result["ratio"].iloc[1] == 1.0
    assert log[0]["invalid_operation_count"] == 1
    assert "除零" in warnings[0]


def test_plan_derived_column_rounds_actual_values_to_eight_decimals():
    frame = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 3.0]})
    result, log, warnings = apply_derived_columns(frame, [DerivedColumn(
        name="ratio", formula="[x] / [y]", source_columns=["x", "y"],
    )])
    assert result["ratio"].tolist() == [0.33333333, 0.66666667]
    assert log[0]["decimal_places"] == 8
    assert warnings == []


@pytest.mark.parametrize("formula", ["[x] ** 2", "[x] % 2"])
def test_plan_derived_column_rejects_non_basic_arithmetic(formula: str):
    frame = pd.DataFrame({"x": [1.0, 2.0]})
    with pytest.raises(UnsafeFormulaError, match="基础四则运算"):
        apply_derived_columns(frame, [DerivedColumn(
            name="bad", formula=formula, source_columns=["x"],
        )])


def test_plan_derived_column_rejects_non_numeric_and_chained_sources():
    frame = pd.DataFrame({"group": ["A", "B"], "x": [1.0, 2.0]})
    with pytest.raises(ValueError, match="数值型"):
        apply_derived_columns(frame, [DerivedColumn(
            name="bad", formula="[group] + 1", source_columns=["group"],
        )])
