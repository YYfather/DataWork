from pathlib import Path

import pandas as pd

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan
from datawork.report.generator import generate_report


def test_report_exports_generic_tests_and_coefficients(tmp_path: Path):
    frame = pd.DataFrame({"y": [3, 5, 7, 9, 11, 13, 15, 17, 19, 21], "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    result = AnalysisService().run(
        frame,
        AnalysisPlan(dependent_variables=["y"], covariates=["x"], method="linear_regression"),
    )
    report = generate_report(result, tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "模型系数" in text
    assert "R-squared" in text
    workbook = pd.ExcelFile(tmp_path / "results.xlsx")
    assert "模型系数" in workbook.sheet_names
    assert "拟合统计" in workbook.sheet_names
