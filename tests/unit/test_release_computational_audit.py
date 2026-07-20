from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.multivariate.manova import MANOVA as SM_MANOVA
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.multitest import multipletests

from datawork.engine.assumptions import test_sphericity_mauchly as legacy_sphericity_mauchly
from datawork.engine.basic_methods import kruskal_wallis, mann_whitney_u
from datawork.engine.common import rank_biserial_from_u
from datawork.engine.effect_size import cohens_d
from datawork.engine.letters import compact_letter_sets
from datawork.engine.manova import manova
from datawork.engine.model_support import sphericity_result
from datawork.engine.oneway_anova import oneway_anova
from datawork.engine.regression_methods import logistic_regression
from datawork.engine.ttest import independent_ttest, paired_ttest
from datawork.engine.twoway_anova import twoway_anova


def test_ttest_eta_squared_uses_t_and_df() -> None:
    frame = pd.DataFrame({
        "group": ["A"] * 6 + ["B"] * 7,
        "y": [1.0, 2.0, 2.5, 3.0, 4.0, 5.5, 2.0, 3.0, 4.5, 5.0, 7.0, 8.0, 9.0],
    })
    result = independent_ttest(frame["y"], frame["group"], "y", "group", equal_var=False)
    row = result.primary_tests[0]
    expected = row.statistic_value**2 / (row.statistic_value**2 + row.df_num)
    eta = next(item.value for item in result.effect_sizes if item.measure == "eta squared")
    assert eta == pytest_approx(expected, abs=1e-12)
    assert not result.omnibus_tests

    first = pd.Series([10.0, 11.0, 13.0, 12.0, 15.0, 16.0])
    second = pd.Series([9.0, 10.0, 11.0, 12.0, 13.0, 14.0])
    paired = paired_ttest(first, second, "score")
    paired_row = paired.primary_tests[0]
    paired_expected = paired_row.statistic_value**2 / (paired_row.statistic_value**2 + paired_row.df_num)
    paired_eta = next(item.value for item in paired.effect_sizes if item.measure == "eta squared")
    assert paired_eta == pytest_approx(paired_expected, abs=1e-12)
    assert not paired.omnibus_tests


def test_paired_hedges_correction_uses_paired_df() -> None:
    first = np.asarray([8.0, 10.0, 9.0, 13.0, 12.0, 15.0])
    second = np.asarray([7.0, 8.0, 8.0, 11.0, 10.0, 12.0])
    result = cohens_d(first, second, paired=True)
    df = len(first) - 1
    expected = result["d"] * (1 - 3 / (4 * df - 1))
    assert result["hedges_g"] == pytest_approx(expected, abs=2e-4)
    assert result["df_correction"] == float(df)


def test_mann_whitney_rank_biserial_direction_is_first_minus_second() -> None:
    frame = pd.DataFrame({
        "group": ["high"] * 5 + ["low"] * 5,
        "y": [8, 9, 10, 11, 12, 1, 2, 3, 4, 5],
    })
    result = mann_whitney_u(frame, "y", "group", 0.05)
    effect = result.primary_tests[0].effect_size_value
    assert effect is not None and effect > 0.99
    u = stats.mannwhitneyu(frame.loc[:4, "y"], frame.loc[5:, "y"]).statistic
    assert rank_biserial_from_u(float(u), 5, 5) > 0.99


def test_zero_within_variance_different_means_is_significant_and_gets_letters() -> None:
    frame = pd.DataFrame({"group": ["A"] * 4 + ["B"] * 4, "y": [1.0] * 4 + [2.0] * 4})
    result = oneway_anova(
        frame, "y", "group", posthoc_methods=["tukey", "duncan"], estimate_emm=True,
    )
    assert np.isinf(result.omnibus_tests[0].f_value)
    assert len(result.contrasts) == 2
    assert all(item.significant and item.p_adjusted == 0 for item in result.contrasts)
    by_method = {}
    for item in result.significance_letters:
        by_method.setdefault(item.method, set()).add(item.letters)
    assert len(by_method) == 2
    assert all(len(values) == 2 for values in by_method.values())
    assert all(item.se == 0 for item in result.estimated_marginal_means)


def test_tukey_kramer_matches_statsmodels_for_unbalanced_groups() -> None:
    frame = pd.DataFrame({
        "group": ["A"] * 5 + ["B"] * 7 + ["C"] * 6,
        "y": [1.0, 1.5, 2.1, 2.4, 3.0, 2.8, 3.2, 3.9, 4.2, 4.5, 5.1, 5.5, 4.8, 5.2, 5.9, 6.2, 6.7, 7.1],
    })
    result = oneway_anova(frame, "y", "group", posthoc_methods=["tukey"])
    ours = {item.contrast: item.p_adjusted for item in result.contrasts}
    reference = pairwise_tukeyhsd(frame["y"], frame["group"], alpha=0.05)
    pairs = list(combinations(reference.groupsunique.tolist(), 2))
    for pair, p_value in zip(pairs, reference.pvalues):
        assert ours[f"{pair[0]} - {pair[1]}"] == pytest_approx(float(p_value), abs=2e-6)


def test_kruskal_followup_is_actual_dunn_holm() -> None:
    frame = pd.DataFrame({
        "group": ["A"] * 5 + ["B"] * 5 + ["C"] * 5,
        "y": [1, 2, 2, 3, 4, 3, 4, 5, 5, 6, 8, 9, 9, 10, 11],
    })
    result = kruskal_wallis(frame, "y", "group", 0.05)
    assert len(result.contrasts) == 3
    assert all("Dunn" in item.correction for item in result.contrasts)

    values = frame["y"].to_numpy(float)
    ranks = stats.rankdata(values, method="average")
    rank_frame = frame.assign(rank=ranks)
    means = rank_frame.groupby("group")["rank"].mean()
    sizes = rank_frame.groupby("group").size()
    _, counts = np.unique(values, return_counts=True)
    n = len(values)
    correction = 1 - np.sum(counts**3 - counts) / (n**3 - n)
    base = n * (n + 1) / 12 * correction
    raw = []
    z_values = []
    for left, right in combinations(["A", "B", "C"], 2):
        se = np.sqrt(base * (1 / sizes[left] + 1 / sizes[right]))
        z = (means[left] - means[right]) / se
        z_values.append(z)
        raw.append(2 * stats.norm.sf(abs(z)))
    adjusted = multipletests(raw, method="holm")[1]
    for item, z, p_adj in zip(result.contrasts, z_values, adjusted):
        assert item.t_value == pytest_approx(float(z), abs=1e-12)
        assert item.p_adjusted == pytest_approx(float(p_adj), abs=1e-12)


def test_logistic_reports_true_mcfadden_and_deviance_explained() -> None:
    x = np.linspace(-2.5, 2.5, 80)
    y = np.asarray([(index % 7) < (1 + int((value + 2.5) / 1.0)) for index, value in enumerate(x)], dtype=int)
    frame = pd.DataFrame({"y": y, "x": x})
    result = logistic_regression(frame, "y", [], ["x"], 0.05)
    direct = smf.glm("y ~ x", data=frame, family=sm.families.Binomial()).fit()
    expected_mcfadden = 1 - direct.llf / direct.llnull
    expected_deviance = 1 - direct.deviance / direct.null_deviance
    fit = {item.name: item.value for item in result.fit_statistics}
    assert result.primary_tests[0].effect_size_name == "McFadden pseudo R-squared"
    assert result.primary_tests[0].effect_size_value == pytest_approx(expected_mcfadden, abs=1e-12)
    assert fit["McFadden pseudo R-squared"] == pytest_approx(expected_mcfadden, abs=1e-12)
    assert fit["Deviance explained"] == pytest_approx(expected_deviance, abs=1e-12)


def test_type3_two_way_anova_matches_statsmodels_reference() -> None:
    rng = np.random.default_rng(20260718)
    rows = []
    counts = {("A1", "B1"): 8, ("A1", "B2"): 11, ("A2", "B1"): 9, ("A2", "B2"): 7}
    for (a, b), count in counts.items():
        for _ in range(count):
            y = 5 + (a == "A2") * 1.2 + (b == "B2") * 0.7 + (a == "A2" and b == "B2") * 0.5 + rng.normal(scale=0.8)
            rows.append((a, b, y))
    frame = pd.DataFrame(rows, columns=["A", "B", "y"])
    result = twoway_anova(frame, "y", "A", "B", posthoc_methods="none", ss_type=3, diagnostic_plots=False)
    reference_model = smf.ols("y ~ C(A, Sum) * C(B, Sum)", data=frame).fit()
    reference = anova_lm(reference_model, typ=3)
    expected = {
        "A": reference.loc["C(A, Sum)"],
        "B": reference.loc["C(B, Sum)"],
        "A × B": reference.loc["C(A, Sum):C(B, Sum)"],
    }
    for item in result.omnibus_tests:
        row = expected[item.effect]
        assert item.f_value == pytest_approx(float(row["F"]), abs=6e-5)
        assert item.p_value == pytest_approx(float(row["PR(>F)"]), abs=6e-7)


def test_manova_statistics_match_statsmodels_mv_test() -> None:
    rng = np.random.default_rng(20260718)
    rows = []
    for a in ["A1", "A2"]:
        for b in ["B1", "B2"]:
            for _ in range(12):
                latent = rng.normal()
                y1 = 2 + (a == "A2") * 0.8 + (b == "B2") * 0.4 + latent + rng.normal(scale=0.5)
                y2 = 1 + (a == "A2") * 0.5 - (b == "B2") * 0.3 + 0.5 * latent + rng.normal(scale=0.6)
                rows.append((a, b, y1, y2))
    frame = pd.DataFrame(rows, columns=["A", "B", "y1", "y2"])
    result = manova(
        frame, ["y1", "y2"], ["A", "B"], parameters={
            "multivariate_test": "all", "follow_up_mode": "none",
            "covariance_test": False, "normality_test": False, "correlation_diagnostics": False,
        }, diagnostic_plots=False,
    )
    assert result is not None
    reference = SM_MANOVA.from_formula("y1 + y2 ~ C(A, Sum) * C(B, Sum)", data=frame).mv_test().results
    effect_map = {"A": "C(A, Sum)", "B": "C(B, Sum)", "A × B": "C(A, Sum):C(B, Sum)"}
    statistic_map = {
        "Pillai 轨迹": "Pillai's trace",
        "Wilks' Lambda": "Wilks' lambda",
        "Hotelling–Lawley 轨迹": "Hotelling-Lawley trace",
        "Roy 最大根": "Roy's greatest root",
    }
    for item in result.omnibus_tests:
        row = reference[effect_map[item.effect]]["stat"].loc[statistic_map[item.statistic_name]]
        assert item.statistic_value == pytest_approx(float(row["Value"]), abs=1e-10)
        assert item.f_value == pytest_approx(float(row["F Value"]), abs=1e-10)
        assert item.p_value == pytest_approx(float(row["Pr > F"]), abs=1e-10)


def test_cld_invariants_hold_for_all_five_group_significance_graphs() -> None:
    groups = ["A", "B", "C", "D", "E"]
    pairs = [frozenset(pair) for pair in combinations(groups, 2)]
    means = {group: float(len(groups) - index) for index, group in enumerate(groups)}
    for mask in range(1 << len(pairs)):
        matrix = {pair: bool(mask & (1 << index)) for index, pair in enumerate(pairs)}
        letters = compact_letter_sets(means, matrix)
        token_sets = {group: _split_letter_tokens(value) for group, value in letters.items()}
        for pair, significant in matrix.items():
            left, right = tuple(pair)
            shared = bool(token_sets[left] & token_sets[right])
            assert shared is not significant


def test_legacy_sphericity_entry_matches_canonical_core() -> None:
    wide = pd.DataFrame({
        "T1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "T2": [1.2, 2.1, 3.4, 4.2, 5.6, 6.1],
        "T3": [0.9, 2.4, 2.8, 4.6, 5.1, 6.8],
    })
    canonical = sphericity_result(wide)
    legacy = legacy_sphericity_mauchly(wide, list(wide.columns))
    assert canonical is not None
    assert legacy["W"] == pytest_approx(canonical.statistic, abs=1e-6)
    assert legacy["p_value"] == pytest_approx(canonical.p_value, abs=1e-6)
    assert legacy["GG_epsilon"] == pytest_approx(canonical.epsilon_gg, abs=1e-6)


def _split_letter_tokens(value: str) -> set[str]:
    # 当前 CLD 字母按照 a..z, aa.. 顺序生成。测试仅有 5 组，因此均为单字符。
    return set(value)


def pytest_approx(value: float, *, abs: float):
    import pytest
    return pytest.approx(value, abs=abs)


def test_manova_preflight_handles_read_only_numpy_views(monkeypatch) -> None:
    """Pandas 3 may return read-only arrays from to_numpy(copy=False)."""
    from datawork.application.preflight_service import PreflightService

    original = pd.DataFrame.to_numpy

    def guarded_to_numpy(self, *args, copy=False, **kwargs):
        array = original(self, *args, copy=copy, **kwargs)
        if not copy:
            try:
                array.setflags(write=False)
            except ValueError:
                pass
        return array

    monkeypatch.setattr(pd.DataFrame, "to_numpy", guarded_to_numpy)
    rng = np.random.default_rng(20260718)
    frame = pd.DataFrame({
        "A": np.repeat(["A1", "A2"], 12),
        "y1": rng.normal(size=24),
        "y2": rng.normal(size=24),
    })
    report = PreflightService().inspect(frame, {
        "dependent_variables": ["y1", "y2"],
        "fixed_factors": ["A"],
        "method": "oneway_manova",
    })
    assert report.ready is True
