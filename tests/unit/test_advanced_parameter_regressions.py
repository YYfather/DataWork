from __future__ import annotations

import pandas as pd
import pytest

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan


@pytest.mark.parametrize("alternative", ["two-sided", "less", "greater"])
def test_one_sample_proportion_ztest_supports_all_alternatives(alternative: str) -> None:
    frame = pd.DataFrame({"outcome": ["yes"] * 14 + ["no"] * 6})
    result = AnalysisService().run(
        frame,
        AnalysisPlan(
            method="one_sample_proportion_ztest",
            fixed_factors=["outcome"],
            method_parameters={
                "success_level": "yes",
                "null_proportion": 0.5,
                "alternative": alternative,
            },
        ),
    )
    assert result.primary_tests
    assert 0.0 <= result.primary_tests[0].p_value <= 1.0


@pytest.mark.parametrize("alternative", ["two-sided", "less", "greater"])
def test_two_proportion_ztest_supports_all_alternatives(alternative: str) -> None:
    frame = pd.DataFrame(
        {
            "outcome": ["yes"] * 12 + ["no"] * 8 + ["yes"] * 7 + ["no"] * 13,
            "group": ["A"] * 20 + ["B"] * 20,
        }
    )
    result = AnalysisService().run(
        frame,
        AnalysisPlan(
            method="two_proportion_ztest",
            dependent_variables=["outcome"],
            fixed_factors=["group"],
            method_parameters={"success_level": "yes", "alternative": alternative},
        ),
    )
    assert result.primary_tests
    assert 0.0 <= result.primary_tests[0].p_value <= 1.0


@pytest.mark.parametrize("link", ["logit", "probit", "cloglog", "loglog", "cauchit"])
def test_ordinal_regression_supports_all_registered_links(link: str) -> None:
    rows: list[dict[str, object]] = []
    for index in range(90):
        x = (index - 45) / 12
        if x < -0.7:
            outcome = "low"
        elif x < 0.7:
            outcome = "medium"
        else:
            outcome = "high"
        # Add deterministic overlap so every link can be fitted without separation.
        if index % 11 == 0:
            outcome = "medium"
        rows.append({"outcome": outcome, "x": x, "group": "A" if index % 2 == 0 else "B"})
    frame = pd.DataFrame(rows)
    result = AnalysisService().run(
        frame,
        AnalysisPlan(
            method="ordinal_logistic_regression",
            dependent_variables=["outcome"],
            fixed_factors=["group"],
            covariates=["x"],
            method_parameters={
                "level_order": "low,medium,high",
                "link": link,
                "max_iterations": 300,
            },
        ),
    )
    assert result.primary_tests
    assert result.data_snapshot["link"] == link
