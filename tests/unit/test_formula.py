import pandas as pd
import pytest

from datawork.core.formula import UnsafeFormulaError, evaluate_formula
from datawork.engine.batch import derive_variable


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


def test_derive_variable_does_not_overwrite_existing_column():
    df = pd.DataFrame({"x": [1, 2]})
    with pytest.raises(ValueError, match="已存在"):
        derive_variable(df, "x", "x + 1")
