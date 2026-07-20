import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.oneway import anova_oneway

from datawork.engine.oneway_anova import oneway_anova
from datawork.engine.ttest import paired_ttest
from datawork.engine.twoway_anova import twoway_anova


def test_welch_anova_matches_statsmodels_reference():
    df = pd.DataFrame({
        "value": [1, 2, 3, 4, 8, 10, 12, 20, 21, 22, 23, 24],
        "group": ["a"] * 4 + ["b"] * 3 + ["c"] * 5,
    })
    result = oneway_anova(df, "value", "group", welch=True)
    groups = tuple(group["value"].to_numpy() for _, group in df.groupby("group"))
    reference = anova_oneway(groups, use_var="unequal", welch_correction=True)
    test = result.omnibus_tests[0]
    assert test.f_value == pytest.approx(float(reference.statistic), abs=1e-12)
    assert test.p_value == pytest.approx(float(reference.pvalue), abs=1e-12)
    assert test.df_den == float(reference.df_denom)
    assert result.method.name == "welch_anova"


def test_paired_ttest_preserves_row_pairs_when_dropping_missing_values():
    first = pd.Series([1.0, np.nan, 3.0, 4.0])
    second = pd.Series([1.5, 2.0, np.nan, 5.0])
    result = paired_ttest(first, second, "before_after")
    assert result.data_snapshot["n_pairs"] == 2
    assert result.data_snapshot["dropped_incomplete_pairs"] == 2


def test_twoway_type_three_uses_sum_contrasts_and_reports_requested_ss():
    rng = np.random.default_rng(7)
    rows = []
    for a, n_a in [("A1", 8), ("A2", 11)]:
        for b, n_b in [("B1", n_a), ("B2", n_a + 2)]:
            for value in rng.normal(loc=(a == "A2") + 0.5 * (b == "B2"), scale=1, size=n_b):
                rows.append({"y": value, "A": a, "B": b})
    result = twoway_anova(pd.DataFrame(rows), "y", "A", "B", ss_type=3)
    assert result.provenance["ss_type"] == 3
    assert result.provenance["contrast"] == "Sum"
    assert all(test.ss_type == 3 for test in result.omnibus_tests)
    assert all(test.effect != "截距" for test in result.omnibus_tests)
