from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from datawork.core.plan import AnalysisPlan
from datawork.core.validation import validate_plan_dataframe
from datawork.engine.categorical_methods import cochran_q_test
from datawork.engine.common import describe_numeric


def test_describe_nearly_constant_values_without_runtime_warning() -> None:
    values = np.array([1.0, 1.0 + 1e-16, 1.0, 1.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = describe_numeric(values)
    assert result["skewness"] == 0.0
    assert result["kurtosis"] == 0.0


def test_cochran_q_preflight_blocks_no_within_subject_variation() -> None:
    frame = pd.DataFrame({
        "c1": ["是", "否", "是", "否"],
        "c2": ["是", "否", "是", "否"],
        "c3": ["是", "否", "是", "否"],
    })
    plan = AnalysisPlan(method="cochran_q_test", dependent_variables=["c1", "c2", "c3"])
    report = validate_plan_dataframe(plan, frame)
    assert not report.valid
    assert any(issue.code == "no_cochran_q_variation" for issue in report.issues)


def test_cochran_q_engine_raises_actionable_error_for_degenerate_data() -> None:
    frame = pd.DataFrame({
        "c1": [0, 1, 0, 1],
        "c2": [0, 1, 0, 1],
        "c3": [0, 1, 0, 1],
    })
    with pytest.raises(ValueError, match="完全一致"):
        cochran_q_test(frame, ["c1", "c2", "c3"], 0.05)
