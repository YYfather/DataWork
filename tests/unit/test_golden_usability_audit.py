from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from datawork.core.method_registry import get_method, list_methods
from datawork.engine.advanced_methods import mixed_anova
from datawork.engine.categorical_methods import fleiss_kappa_test
from datawork.engine.oneway_anova import oneway_anova
from datawork.engine.ttest import independent_ttest, paired_ttest


ROOT = Path(__file__).resolve().parents[2]


def test_golden_manifest_covers_every_visible_runnable_method():
    manifest = json.loads((ROOT / "golden_datasets/manifest.json").read_text(encoding="utf-8"))
    covered = {case["method"] for case in manifest["cases"] if case["case_id"].endswith("_default")}
    runnable = {item.name for item in list_methods() if item.visible and item.is_runnable}
    assert covered == runnable


def test_common_parameters_are_few_explained_and_advanced_parameters_remain_available():
    for method in list_methods():
        common = [item for item in method.parameters if not item.advanced]
        assert len(common) <= 2, f"{method.name} exposes too many common parameters: {[item.key for item in common]}"
        for parameter in common:
            assert parameter.simple_description or parameter.description
            if parameter.kind in {"select", "multi_select"} and parameter.options:
                assert parameter.recommended_options
                assert parameter.option_help
        assert all(item.description for item in method.parameters)
    oneway = get_method("oneway_anova")
    posthoc = next(item for item in oneway.parameters if item.key == "posthoc_methods")
    assert posthoc.default == ["auto"]
    assert posthoc.recommended_options
    assert next(item for item in oneway.parameters if item.key == "random_seed").advanced is True
    manova = get_method("oneway_manova")
    assert next(item for item in manova.parameters if item.key == "multivariate_test").default == "pillai"


def test_ttests_report_directional_t_with_full_precision_and_effect_sizes():
    frame = pd.DataFrame({"group": ["A"] * 5 + ["B"] * 6, "y": [1, 2, 3, 4, 5, 3, 4, 5, 6, 7, 8]})
    result = independent_ttest(frame.y, frame.group, "y", "group", equal_var=False)
    reference = stats.ttest_ind(frame.loc[frame.group == "A", "y"], frame.loc[frame.group == "B", "y"], equal_var=False)
    test = result.primary_tests[0]
    assert test.statistic_name == "t"
    assert test.statistic_value == reference.statistic
    assert test.p_value == reference.pvalue
    assert not result.omnibus_tests
    assert {item.measure for item in result.effect_sizes} >= {"Cohen's d", "Hedges' g", "eta squared"}

    paired = paired_ttest(pd.Series([1, 2, 4, 7, 8]), pd.Series([1, 1, 3, 5, 7]), "score")
    assert paired.primary_tests[0].statistic_name == "t"
    assert not paired.omnibus_tests


def test_fleiss_kappa_does_not_fabricate_a_p_value():
    frame = pd.DataFrame({
        "r1": ["A", "A", "B", "B", "C", "C"],
        "r2": ["A", "B", "B", "B", "C", "A"],
        "r3": ["A", "A", "B", "C", "C", "A"],
    })
    result = fleiss_kappa_test(frame, ["r1", "r2", "r3"], 0.05)
    test = result.primary_tests[0]
    assert test.p_value is None
    assert test.is_significant is None


def test_mixed_anova_pairwise_intervals_are_real_not_zero_placeholders():
    frame = pd.read_csv(ROOT / "golden_datasets/data/mixed_anova.csv")
    result = mixed_anova(
        frame, "y", "subject", "time", ["group"], 0.05,
        parameters={"analysis_mode": "classical", "pairwise_correction": "holm"},
        estimate_emm=True,
    )
    assert result.contrasts
    assert all(item.ci_lower is not None and item.ci_upper is not None for item in result.contrasts)
    assert any(abs(item.ci_upper - item.ci_lower) > 0 for item in result.contrasts)


def test_inferential_core_does_not_round_small_anova_p_values_to_zero():
    frame = pd.read_csv(ROOT / "golden_datasets/data/three_groups.csv")
    result = oneway_anova(frame, "y", "group", welch=True, posthoc_methods=["games_howell"])
    assert 0 < result.omnibus_tests[0].p_value < 1e-6
