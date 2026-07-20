"""端到端回归测试。"""

from pathlib import Path

import numpy as np
import pandas as pd

from datawork.application.analysis_service import AnalysisService
from datawork.core.plan import AnalysisPlan
from datawork.report.generator import generate_report
from datawork.rules.constraints import get_hard_rules


def test_full_pipeline(tmp_path: Path):
    rng = np.random.default_rng(21)
    rows = []
    for spray in ["T1", "T2"]:
        for mode in ["M1", "M2"]:
            for value in rng.normal(loc=(spray == "T2") * 2 + (mode == "M2"), size=10):
                rows.append({"14d脱叶率": value, "脱叶剂喷施时间": spray, "种植模式": mode})
    frame = pd.DataFrame(rows)
    plan = AnalysisPlan(
        dependent_variables=["14d脱叶率"],
        fixed_factors=["脱叶剂喷施时间", "种植模式"],
        method="twoway_anova",
        ss_type=3,
    )
    result = AnalysisService().run(frame, plan)

    assert len(result.omnibus_tests) == 3
    assert all(test.ss_type == 3 for test in result.omnibus_tests)
    assert len(get_hard_rules()) == 10

    out = tmp_path / "report"
    report_path = generate_report(result, out, title="V")
    assert report_path.exists()
    assert (out / "canonical_result.json").exists()
    assert (out / "results.xlsx").exists()


def test_all_imports():
    from datawork.io.profiler import profile_dataframe
    from datawork.engine.result import StatisticalResult
    from datawork.engine.assumptions import test_normality, test_homogeneity
    from datawork.engine.effect_size import cohens_d, partial_eta_squared
    from datawork.engine.ttest import independent_ttest, paired_ttest
    from datawork.engine.oneway_anova import oneway_anova
    from datawork.engine.twoway_anova import threeway_anova
    from datawork.engine.posthoc import pairwise_tukey, pairwise_holm
    from datawork.rules.decision_tree import recommend_methods, DesignSignature, ResearchGoal
    from datawork.ai.provider import create_provider
    from datawork.ai.prompts import variable_inference_prompt, report_generation_prompt, analysis_preview_prompt
    from datawork.ai.guard import guard_ai_output
    from datawork.design.infer import ai_enhance_roles, merge_roles
    assert StatisticalResult and profile_dataframe and create_provider
