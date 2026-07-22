"""t 检验引擎 — 独立样本 / Welch / 配对。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .common import safe_paired_ttest
from .result import (
    StatisticalResult, DesignInfo, MethodInfo, PrimaryTestResult,
    EffectSize, DiagnosticResult, VariableInfo, VariableRole,
)
from .assumptions import test_normality, test_homogeneity
from .effect_size import cohens_d


def independent_ttest(
    data: pd.Series,
    group: pd.Series,
    dv_name: str,
    factor_name: str,
    equal_var: bool = False,
    alpha: float = 0.05,
) -> StatisticalResult:
    """独立样本 t 检验。

    默认执行 Welch t 检验。只有调用方明确传入 ``equal_var=True`` 时，
    才执行 Student t 检验。
    """
    aligned = pd.DataFrame({dv_name: data, factor_name: group}).dropna()
    aligned[dv_name] = pd.to_numeric(aligned[dv_name], errors="coerce")
    aligned = aligned.dropna(subset=[dv_name])

    groups = aligned[factor_name].unique()
    if len(groups) != 2:
        raise ValueError(f"t 检验需要恰好 2 个水平，当前有 {len(groups)} 个: {groups}")

    g1, g2 = groups
    d1 = aligned.loc[aligned[factor_name] == g1, dv_name].to_numpy(dtype=float)
    d2 = aligned.loc[aligned[factor_name] == g2, dv_name].to_numpy(dtype=float)
    n1, n2 = len(d1), len(d2)
    if n1 < 2 or n2 < 2:
        raise ValueError(f"每组至少需要 2 个有效观测，当前为 {n1} 和 {n2}")

    m1, m2 = float(np.mean(d1)), float(np.mean(d2))
    sd1, sd2 = float(np.std(d1, ddof=1)), float(np.std(d2, ddof=1))

    t_stat, p_val = stats.ttest_ind(d1, d2, equal_var=equal_var)
    if equal_var:
        df = float(n1 + n2 - 2)
        method_name = "Student 独立样本 t 检验"
        method_key = "independent_ttest"
        pooled_var = ((n1 - 1) * sd1**2 + (n2 - 1) * sd2**2) / df
        se_diff = np.sqrt(pooled_var * (1 / n1 + 1 / n2))
    else:
        v1, v2 = sd1**2, sd2**2
        se1, se2 = v1 / n1, v2 / n2
        denominator = se1**2 / (n1 - 1) + se2**2 / (n2 - 1)
        df = float((se1 + se2) ** 2 / denominator) if denominator > 0 else 1.0
        method_name = "Welch t 检验"
        method_key = "welch_ttest"
        se_diff = np.sqrt(se1 + se2)

    mean_diff = m1 - m2
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    es = cohens_d(d1, d2, paired=False)

    norm1 = test_normality(d1, alpha)
    norm2 = test_normality(d2, alpha)
    lev = test_homogeneity(aligned, dv_name, factor_name, alpha=alpha)
    diagnostics = [
        DiagnosticResult(
            test_name=f"{norm1.test_name} ({g1})", statistic=float(norm1.statistic),
            p_value=float(norm1.p_value), passed=norm1.passed, detail=norm1.detail,
        ),
        DiagnosticResult(
            test_name=f"{norm2.test_name} ({g2})", statistic=float(norm2.statistic),
            p_value=float(norm2.p_value), passed=norm2.passed, detail=norm2.detail,
        ),
        DiagnosticResult(
            test_name="Levene", statistic=float(lev.statistic),
            p_value=float(lev.p_value), passed=lev.passed, detail=lev.detail,
        ),
    ]

    t_squared = float(t_stat) ** 2
    eta = float(t_squared / (t_squared + df)) if np.isfinite(t_squared) else 1.0
    primary = [PrimaryTestResult(
        effect=f"{g1} vs {g2}",
        statistic_name="t",
        statistic_value=float(t_stat),
        p_value=float(p_val),
        df_num=df,
        effect_size_name="Cohen's d",
        effect_size_value=float(es["d"]),
        ci_lower=float(ci_lower),
        ci_upper=float(ci_upper),
        is_significant=bool(p_val < alpha),
        significance_level=alpha,
        detail=(
            f"mean difference ({g1} - {g2})={mean_diff:.6g}; "
            f"eta squared={eta:.6g}; equal_var={equal_var}"
        ),
    )]

    effect_sizes = [
        EffectSize(
            measure="Cohen's d", value=es["d"],
            ci_lower=es["ci_lower"], ci_upper=es["ci_upper"],
            interpretation=es["interpretation"],
        ),
        EffectSize(
            measure="Hedges' g", value=es["hedges_g"],
            interpretation=es["interpretation"],
        ),
        EffectSize(measure="eta squared", value=eta),
    ]

    design = DesignInfo(
        variables=[
            VariableInfo(name=dv_name, dtype="float64", role=VariableRole.DEPENDENT),
            VariableInfo(
                name=factor_name, dtype=str(aligned[factor_name].dtype),
                role=VariableRole.BETWEEN, levels=[str(g1), str(g2)], n_unique=2,
            ),
        ],
        n_subjects=n1 + n2,
        n_observations=n1 + n2,
        between_factors=[factor_name],
        dependent_vars=[dv_name],
    )

    warnings: list[str] = []
    if equal_var and not lev.passed:
        warnings.append(
            f"Levene 检验提示方差不齐 (p={lev.p_value:.4f})；建议改用 Welch t 检验。"
        )

    return StatisticalResult(
        analysis_id=f"ttest_{factor_name}",
        design=design,
        method=MethodInfo(
            name=method_key,
            label_zh=method_name,
            formula=f"{dv_name} ~ {factor_name}",
            assumptions=["观测独立", "组内近似正态"],
        ),
        diagnostics=diagnostics,
        primary_tests=primary,
        effect_sizes=effect_sizes,
        warnings=warnings,
        descriptive_stats=[
            {"group": str(g1), "n": n1, "mean": round(m1, 4), "sd": round(sd1, 4)},
            {"group": str(g2), "n": n2, "mean": round(m2, 4), "sd": round(sd2, 4)},
        ],
        data_snapshot={
            "n_total": n1 + n2,
            "groups": {str(g1): n1, str(g2): n2},
            "mean_difference": round(mean_diff, 6),
            "mean_difference_ci": [round(ci_lower, 6), round(ci_upper, 6)],
        },
    )


def paired_ttest(
    data1: pd.Series,
    data2: pd.Series,
    dv_name: str,
    time_labels: tuple[str, str] = ("pre", "post"),
    alpha: float = 0.05,
) -> StatisticalResult:
    """配对样本 t 检验；按照原始索引共同删除缺失值。"""
    paired = pd.concat(
        [pd.Series(data1, name="_first"), pd.Series(data2, name="_second")], axis=1
    )
    n_original = len(paired)
    paired = paired.apply(pd.to_numeric, errors="coerce").dropna()
    if len(paired) < 2:
        raise ValueError("配对 t 检验至少需要 2 对完整观测")

    d1 = paired["_first"].to_numpy(dtype=float)
    d2 = paired["_second"].to_numpy(dtype=float)
    n_pairs = len(paired)
    m1, m2 = float(np.mean(d1)), float(np.mean(d2))
    sd1, sd2 = float(np.std(d1, ddof=1)), float(np.std(d2, ddof=1))
    diff = d1 - d2

    t_stat, p_val = safe_paired_ttest(d1, d2)
    df = float(n_pairs - 1)
    es = cohens_d(d1, d2, paired=True)
    normality = test_normality(diff, alpha)

    diagnostics = [DiagnosticResult(
        test_name=f"{normality.test_name}（差值）",
        statistic=float(normality.statistic),
        p_value=float(normality.p_value),
        passed=normality.passed,
        detail=normality.detail,
    )]

    t_squared = float(t_stat) ** 2
    eta = float(t_squared / (t_squared + df)) if np.isfinite(t_squared) else 1.0
    warnings: list[str] = []
    dropped = n_original - n_pairs
    if dropped:
        warnings.append(f"按配对关系共同删除了 {dropped} 行缺失观测。")

    return StatisticalResult(
        analysis_id="paired_ttest",
        design=DesignInfo(
            variables=[VariableInfo(name=dv_name, dtype="float64", role=VariableRole.DEPENDENT)],
            n_subjects=n_pairs,
            n_observations=n_pairs * 2,
            within_factors=["time"],
            dependent_vars=[dv_name],
        ),
        method=MethodInfo(
            name="paired_ttest",
            label_zh="配对样本 t 检验",
            formula=f"{dv_name} ~ time",
            assumptions=["配对差值近似正态"],
        ),
        diagnostics=diagnostics,
        primary_tests=[PrimaryTestResult(
            effect=f"{time_labels[0]} vs {time_labels[1]}",
            statistic_name="t",
            statistic_value=float(t_stat),
            p_value=float(p_val),
            df_num=df,
            effect_size_name="Cohen's d（配对）",
            effect_size_value=float(es["d"]),
            ci_lower=float(np.mean(diff) - stats.t.ppf(1 - alpha / 2, df) * stats.sem(diff)),
            ci_upper=float(np.mean(diff) + stats.t.ppf(1 - alpha / 2, df) * stats.sem(diff)),
            is_significant=bool(p_val < alpha),
            significance_level=alpha,
            detail=f"mean paired difference ({time_labels[0]} - {time_labels[1]})={np.mean(diff):.6g}; eta squared={eta:.6g}",
        )],
        effect_sizes=[
            EffectSize(
                measure="Cohen's d（配对）", value=es["d"],
                ci_lower=es["ci_lower"], ci_upper=es["ci_upper"],
                interpretation=es["interpretation"],
            ),
            EffectSize(measure="eta squared", value=eta),
        ],
        warnings=warnings,
        descriptive_stats=[
            {"time": time_labels[0], "n": n_pairs, "mean": round(m1, 4), "sd": round(sd1, 4)},
            {"time": time_labels[1], "n": n_pairs, "mean": round(m2, 4), "sd": round(sd2, 4)},
        ],
        data_snapshot={"n_pairs": n_pairs, "dropped_incomplete_pairs": dropped},
    )
