from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan
from datawork.engine.batch import BatchAnalysisResult
from datawork.engine.letters import compact_letter_sets
from datawork.engine.oneway_anova import oneway_anova
from datawork.report.generator import generate_report


def _factorial_frame(seed: int = 452, repeats: int = 14) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for a, b, c in product(["0", "1"], repeat=3):
        for _ in range(repeats):
            rows.append({
                "A": a,
                "B": b,
                "C": c,
                "y": 2.5 * (a == "1") + 1.5 * (b == "1") + 0.6 * (c == "1") + rng.normal(0, 0.45),
            })
    return pd.DataFrame(rows)


def test_compact_letter_display_handles_overlap_chain() -> None:
    letters = compact_letter_sets(
        {"A": 3.0, "B": 2.0, "C": 1.0},
        {
            frozenset({"A", "B"}): False,
            frozenset({"B", "C"}): False,
            frozenset({"A", "C"}): True,
        },
    )
    assert letters == {"A": "a", "B": "ab", "C": "b"}


def test_multiple_posthoc_methods_each_generate_separate_letters() -> None:
    rng = np.random.default_rng(18)
    frame = pd.DataFrame({
        "group": np.repeat(["A", "B", "C"], 24),
        "y": np.r_[rng.normal(10, 0.25, 24), rng.normal(7, 0.25, 24), rng.normal(4, 0.25, 24)],
    })
    result = oneway_anova(frame, "y", "group", posthoc_methods=["tukey", "duncan"])
    assert {item.correction for item in result.contrasts} == {
        "Tukey–Kramer HSD", "Duncan 多重极差（宽松)",
    } or {item.correction for item in result.contrasts} == {
        "Tukey–Kramer HSD", "Duncan 多重极差（宽松）",
    }
    grouped = {(item.method, item.group): item.letters for item in result.significance_letters}
    assert grouped[("Tukey–Kramer HSD", "A")] == "a"
    assert grouped[("Duncan 多重极差（宽松）", "A")] == "a"
    assert len(result.significance_letters) == 6


def test_fixed_twoway_method_requires_confirmation_then_expands_exact_combinations() -> None:
    with pytest.raises(ValidationError, match="最多允许 2 个固定因素"):
        AnalysisPlan(
            method="twoway_anova",
            dependent_variables=["y"],
            fixed_factors=["A", "B", "C"],
            method_parameters={"posthoc_methods": ["tukey"]},
        )

    plan = AnalysisPlan(
        method="twoway_anova",
        dependent_variables=["y"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
        method_parameters={"posthoc_methods": ["tukey", "duncan"]},
    )
    assert plan.factor_combination_min_order == 2
    assert plan.factor_combination_max_order == 2
    result = AnalysisService().run(_factorial_frame(), plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 3
    assert set(result.summary_df["factor_combination"].dropna()) == {"A × B", "A × C", "B × C"}
    assert "letter_group" in set(result.summary_df["result_type"].dropna())
    assert set(result.overview_df["result_type"].dropna()) == {"test"}
    assert result.overview_df["p_value"].notna().all()
    assert set(result.overview_df.groupby("task_id").size()) == {3}
    assert not result.overview_df["effect"].astype(str).str.contains(r"=|\[").any()


def test_fixed_oneway_method_runs_all_single_factor_models() -> None:
    plan = AnalysisPlan(
        method="oneway_anova",
        dependent_variables=["y"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
        method_parameters={"posthoc_methods": ["tukey"]},
    )
    result = AnalysisService().run(_factorial_frame(), plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 3
    assert set(result.summary_df["factor_combination"].dropna()) == {"A", "B", "C"}


def test_legacy_factorial_plan_migrates_to_fixed_method() -> None:
    plan = AnalysisPlan(
        method="factorial_anova",
        dependent_variables=["y"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
        method_parameters={"factor_model_order": "2", "posthoc_methods": ["tukey"]},
    )
    assert plan.method == "twoway_anova"
    assert "factor_model_order" not in plan.method_parameters
    assert plan.factor_combination_min_order == plan.factor_combination_max_order == 2


def test_report_exports_compact_letter_display(tmp_path: Path) -> None:
    rng = np.random.default_rng(21)
    frame = pd.DataFrame({
        "group": np.repeat(["A", "B", "C"], 20),
        "y": np.r_[rng.normal(8, 0.2, 20), rng.normal(6, 0.2, 20), rng.normal(4, 0.2, 20)],
    })
    result = oneway_anova(frame, "y", "group", posthoc_methods=["tukey", "duncan"])
    report = generate_report(result, tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "显著性字母分组（CLD）" in text
    workbook = pd.ExcelFile(tmp_path / "results.xlsx")
    assert "显著性字母分组" in workbook.sheet_names
    letters = pd.read_excel(tmp_path / "results.xlsx", sheet_name="显著性字母分组")
    assert set(letters["显著性字母"]) == {"a", "b", "c"}


def test_twoway_manova_uses_fixed_order_for_candidate_combinations() -> None:
    rng = np.random.default_rng(39)
    rows: list[dict[str, object]] = []
    for a, b, c in product(["0", "1"], repeat=3):
        for _ in range(12):
            shift = 1.8 * (a == "1") + 1.1 * (b == "1") + 0.5 * (c == "1")
            latent = rng.normal()
            rows.append({
                "A": a, "B": b, "C": c,
                "y1": shift + latent + rng.normal(0, 0.4),
                "y2": 0.7 * shift + 0.5 * latent + rng.normal(0, 0.45),
            })
    plan = AnalysisPlan(
        method="twoway_manova",
        dependent_variables=["y1", "y2"],
        fixed_factors=["A", "B", "C"],
        factor_combinations_enabled=True,
        method_parameters={
            "multivariate_test": "pillai",
            "primary_multivariate_test": "pillai",
            "covariance_test": False,
            "normality_test": False,
            "correlation_diagnostics": False,
            "follow_up_mode": "none",
            "posthoc_methods": ["none"],
        },
    )
    result = AnalysisService().run(pd.DataFrame(rows), plan)
    assert isinstance(result, BatchAnalysisResult)
    assert len(result.results) == 3
    assert set(result.summary_df["factor_combination"].dropna()) == {"A × B", "A × C", "B × C"}
