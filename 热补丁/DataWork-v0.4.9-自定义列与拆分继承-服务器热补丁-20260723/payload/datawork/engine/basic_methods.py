"""描述统计、非参数、相关与分类数据检验。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

from .common import (
    describe_numeric,
    design_info,
    fisher_r_ci,
    numeric_frame,
    numeric_series,
    rank_biserial_from_u,
    safe_standardized_statistic,
    significance,
)
from .letters import cld_from_posthoc_results
from .result import (
    ContrastResult,
    EffectSize,
    MethodInfo,
    PrimaryTestResult,
    StatisticalResult,
)


def descriptive_statistics(df: pd.DataFrame, variables: list[str]) -> StatisticalResult:
    rows = []
    warnings: list[str] = []
    for variable in variables:
        raw = df[variable]
        values = numeric_series(raw)
        rows.append({**describe_numeric(values, name=variable), "missing": int(raw.isna().sum())})
        if len(values) < 2:
            warnings.append(f"变量 {variable} 的有效数值少于 2 个。")
    return StatisticalResult(
        analysis_id="descriptive_statistics",
        design=design_info(df, dependent=variables),
        method=MethodInfo(
            name="descriptive_statistics", label_zh="描述统计",
            formula="describe(selected variables)",
            research_question="概括所选变量的中心位置、离散程度和分布形态。",
            assumptions=["不进行显著性推断"],
        ),
        descriptive_stats=rows,
        warnings=warnings,
        data_snapshot={"variables": variables, "n_rows": int(len(df))},
    )


def one_sample_ttest(df: pd.DataFrame, variable: str, test_value: float, alpha: float) -> StatisticalResult:
    values = numeric_series(df[variable])
    if len(values) < 2:
        raise ValueError("单样本 t 检验至少需要 2 个有效数值")
    statistic, p_value = stats.ttest_1samp(values, popmean=test_value)
    n = len(values)
    mean = float(np.mean(values))
    sd = float(np.std(values, ddof=1))
    difference = mean - test_value
    se = sd / math.sqrt(n)
    critical = float(stats.t.ppf(1 - alpha / 2, n - 1))
    lower, upper = difference - critical * se, difference + critical * se
    d = safe_standardized_statistic(difference, sd)
    return StatisticalResult(
        analysis_id=f"one_sample_ttest_{variable}",
        design=design_info(df[[variable]].dropna(), dependent=[variable]),
        method=MethodInfo(name="one_sample_ttest", label_zh="单样本 t 检验", formula=f"mean({variable}) = {test_value}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{variable} 与参考值 {test_value}", statistic_name="t", statistic_value=float(statistic),
            p_value=float(p_value), df_num=float(n - 1), effect_size_name="Cohen's d", effect_size_value=float(d),
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(float(p_value), alpha), significance_level=alpha,
            detail=f"样本均值={mean:.6g}，均值差={difference:.6g}",
        )],
        effect_sizes=[EffectSize(measure="Cohen's d", value=float(d))],
        descriptive_stats=[describe_numeric(values, name=variable)],
        data_snapshot={"test_value": test_value, "mean_difference": difference},
    )


def mann_whitney_u(df: pd.DataFrame, dv: str, factor: str, alpha: float) -> StatisticalResult:
    clean = df[[dv, factor]].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna()
    levels = list(clean[factor].unique())
    if len(levels) != 2:
        raise ValueError("Mann–Whitney U 检验要求分组因素恰好 2 个水平")
    left = clean.loc[clean[factor] == levels[0], dv].to_numpy(dtype=float)
    right = clean.loc[clean[factor] == levels[1], dv].to_numpy(dtype=float)
    if len(left) < 2 or len(right) < 2:
        raise ValueError("每组至少需要 2 个有效观测")
    u, p = stats.mannwhitneyu(left, right, alternative="two-sided", method="auto")
    rbc = rank_biserial_from_u(float(u), len(left), len(right))
    return StatisticalResult(
        analysis_id=f"mann_whitney_{factor}",
        design=design_info(clean, dependent=[dv], fixed=[factor]),
        method=MethodInfo(name="mann_whitney_u", label_zh="Mann–Whitney U 检验", formula=f"{dv} ~ {factor}"),
        primary_tests=[PrimaryTestResult(
            effect=factor, statistic_name="U", statistic_value=float(u), p_value=float(p),
            effect_size_name="rank-biserial r", effect_size_value=rbc,
            is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="秩双列相关", value=rbc)],
        descriptive_stats=[
            {"group": str(levels[0]), **describe_numeric(left, name=dv)},
            {"group": str(levels[1]), **describe_numeric(right, name=dv)},
        ],
    )


def wilcoxon_signed_rank(df: pd.DataFrame, first: str, second: str, alpha: float) -> StatisticalResult:
    clean = numeric_frame(df, [first, second])
    if len(clean) < 2:
        raise ValueError("Wilcoxon 符号秩检验至少需要 2 对完整观测")
    diff = clean[first].to_numpy() - clean[second].to_numpy()
    if np.allclose(diff, 0):
        raise ValueError("所有配对差值均为 0，无法执行 Wilcoxon 检验")
    w, p = stats.wilcoxon(clean[first], clean[second], alternative="two-sided", zero_method="wilcox")
    nonzero = diff[diff != 0]
    ranks = stats.rankdata(abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    rbc = (positive - negative) / (positive + negative) if positive + negative else 0.0
    return StatisticalResult(
        analysis_id="wilcoxon_signed_rank",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="wilcoxon_signed_rank", label_zh="Wilcoxon 符号秩检验", formula=f"{first} paired with {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} vs {second}", statistic_name="W", statistic_value=float(w), p_value=float(p),
            effect_size_name="rank-biserial r", effect_size_value=float(rbc),
            is_significant=significance(float(p), alpha), significance_level=alpha,
            detail=f"配对差值中位数={float(np.median(diff)):.6g}",
        )],
        effect_sizes=[EffectSize(measure="秩双列相关", value=float(rbc))],
        descriptive_stats=[describe_numeric(clean[first].to_numpy(), name=first), describe_numeric(clean[second].to_numpy(), name=second)],
    )


def kruskal_wallis(df: pd.DataFrame, dv: str, factor: str, alpha: float) -> StatisticalResult:
    """Kruskal–Wallis 检验及显著后的 Dunn–Holm 两两比较。"""
    clean = df[[dv, factor]].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna()
    grouped = [(name, group[dv].to_numpy(dtype=float)) for name, group in clean.groupby(factor, observed=True)]
    if len(grouped) < 2:
        raise ValueError("Kruskal–Wallis 检验至少需要 2 个组")
    if any(len(values) < 2 for _, values in grouped):
        raise ValueError("每组至少需要 2 个有效观测")
    h, p = stats.kruskal(*(values for _, values in grouped))
    n, k = len(clean), len(grouped)
    epsilon_sq = max(0.0, float((h - k + 1) / (n - k))) if n > k else 0.0
    contrasts: list[ContrastResult] = []
    significance_letters = []
    warnings: list[str] = []
    if p < alpha:
        all_values = clean[dv].to_numpy(dtype=float)
        ranks = stats.rankdata(all_values, method="average")
        ranked = clean.assign(_rank=ranks)
        rank_means = ranked.groupby(factor, observed=True)["_rank"].mean().to_dict()
        sizes = ranked.groupby(factor, observed=True).size().to_dict()
        _unique, tie_counts = np.unique(all_values, return_counts=True)
        tie_sum = float(np.sum(tie_counts**3 - tie_counts))
        tie_correction = 1.0 - tie_sum / (n**3 - n) if n > 1 else 1.0
        base_variance = n * (n + 1) / 12.0 * tie_correction
        raw_p: list[float] = []
        pair_rows: list[tuple[object, object, float, float, float]] = []
        names = [name for name, _values in grouped]
        for i in range(k):
            for j in range(i + 1, k):
                left_name, right_name = names[i], names[j]
                estimate = float(rank_means[left_name] - rank_means[right_name])
                se = float(np.sqrt(max(base_variance * (1 / sizes[left_name] + 1 / sizes[right_name]), 0.0)))
                z_value = safe_standardized_statistic(estimate, se)
                pair_p = float(2 * stats.norm.sf(abs(z_value)))
                raw_p.append(pair_p)
                pair_rows.append((left_name, right_name, estimate, se, z_value))
        adjusted = multipletests(raw_p, alpha=alpha, method="holm")[1] if raw_p else np.asarray([])
        for index, ((left_name, right_name, estimate, se, z_value), raw_value, adj_p) in enumerate(zip(pair_rows, raw_p, adjusted)):
            contrasts.append(ContrastResult(
                contrast=f"{left_name} - {right_name}", estimate=estimate, se=se,
                t_value=z_value, statistic_name="z", p_value=raw_value,
                p_adjusted=float(adj_p), significant=bool(adj_p < alpha),
                correction="Dunn–Holm（全局秩与并列校正）",
            ))
        from types import SimpleNamespace
        pseudo = [SimpleNamespace(
            group1=str(row[0]), group2=str(row[1]), significant=bool(adjusted[index] < alpha)
        ) for index, row in enumerate(pair_rows)]
        group_locations = {str(name): float(np.median(values)) for name, values in grouped}
        significance_letters = cld_from_posthoc_results(
            group_locations, pseudo, factor=factor, method="Dunn–Holm", outcome=dv,
        )
        warnings.append("Dunn 跟进比较使用全体观测的平均秩、并列值修正和 Holm 家族错误率校正。")
    return StatisticalResult(
        analysis_id=f"kruskal_{factor}",
        design=design_info(clean, dependent=[dv], fixed=[factor]),
        method=MethodInfo(name="kruskal_wallis", label_zh="Kruskal–Wallis H 检验", formula=f"rank({dv}) ~ {factor}"),
        primary_tests=[PrimaryTestResult(
            effect=factor, statistic_name="H", statistic_value=float(h), p_value=float(p), df_num=float(k - 1),
            effect_size_name="epsilon squared", effect_size_value=epsilon_sq,
            is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        contrasts=contrasts, significance_letters=significance_letters,
        effect_sizes=[EffectSize(measure="ε²", value=epsilon_sq)],
        descriptive_stats=[{"group": str(name), **describe_numeric(values, name=dv)} for name, values in grouped],
        warnings=warnings,
        data_snapshot={"n": n, "k": k, "posthoc": "Dunn–Holm" if contrasts else "none"},
    )


def correlation(df: pd.DataFrame, first: str, second: str, method: str, alpha: float) -> StatisticalResult:
    clean = numeric_frame(df, [first, second])
    if len(clean) < 3:
        raise ValueError("相关分析至少需要 3 对完整观测")
    x, y = clean[first].to_numpy(), clean[second].to_numpy()
    if np.std(x) == 0 or np.std(y) == 0:
        raise ValueError("相关分析不能使用常数列")
    if method == "pearson_correlation":
        statistic, p = stats.pearsonr(x, y)
        stat_name, label = "r", "Pearson 相关"
        lower, upper = fisher_r_ci(float(statistic), len(clean), alpha)
    elif method == "spearman_correlation":
        statistic, p = stats.spearmanr(x, y)
        stat_name, label, lower, upper = "rho", "Spearman 秩相关", None, None
    else:
        statistic, p = stats.kendalltau(x, y)
        stat_name, label, lower, upper = "tau", "Kendall τ 相关", None, None
    return StatisticalResult(
        analysis_id=f"{method}_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name=method, label_zh=label, formula=f"association({first}, {second})", report_constraints=["相关不代表因果"]),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} ↔ {second}", statistic_name=stat_name, statistic_value=float(statistic), p_value=float(p),
            effect_size_name=stat_name, effect_size_value=float(statistic), ci_lower=lower, ci_upper=upper,
            is_significant=significance(float(p), alpha), significance_level=alpha, detail=f"n={len(clean)}",
        )],
        effect_sizes=[EffectSize(measure=stat_name, value=float(statistic), ci_lower=lower, ci_upper=upper)],
        descriptive_stats=[describe_numeric(x, name=first), describe_numeric(y, name=second)],
        report_constraints=["不得将统计相关解释为因果关系。"],
    )


def chi_square_independence(df: pd.DataFrame, first: str, second: str, alpha: float) -> StatisticalResult:
    clean = df[[first, second]].dropna()
    table = pd.crosstab(clean[first], clean[second])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError("卡方独立性检验要求两个分类变量都至少有 2 个水平")
    chi2, p, dof, expected = stats.chi2_contingency(table.to_numpy())
    n = int(table.to_numpy().sum())
    minimum_dimension = min(table.shape[0] - 1, table.shape[1] - 1)
    cramer_v = math.sqrt(float(chi2) / (n * minimum_dimension)) if n and minimum_dimension else 0.0
    low_expected = int((expected < 5).sum())
    warnings = []
    if low_expected:
        warnings.append(f"有 {low_expected} 个单元格期望频数小于 5；小样本结果需谨慎。")
    return StatisticalResult(
        analysis_id=f"chi_square_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(name="chi_square_independence", label_zh="卡方独立性检验", formula=f"{first} × {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="chi-square", statistic_value=float(chi2), p_value=float(p), df_num=float(dof),
            effect_size_name="Cramer's V", effect_size_value=cramer_v,
            is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Cramer's V", value=cramer_v)],
        warnings=warnings,
        descriptive_stats=[{"row": str(index), **{str(column): int(value) for column, value in row.items()}} for index, row in table.iterrows()],
        data_snapshot={"observed": table.to_dict(), "expected": expected.tolist()},
    )


def fisher_exact_test(df: pd.DataFrame, first: str, second: str, alpha: float) -> StatisticalResult:
    clean = df[[first, second]].dropna()
    table = pd.crosstab(clean[first], clean[second])
    if table.shape != (2, 2):
        raise ValueError(f"Fisher 精确检验要求 2×2 列联表，当前为 {table.shape[0]}×{table.shape[1]}")
    odds_ratio, p = stats.fisher_exact(table.to_numpy(), alternative="two-sided")
    return StatisticalResult(
        analysis_id=f"fisher_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(name="fisher_exact", label_zh="Fisher 精确检验", formula=f"{first} × {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="odds ratio", statistic_value=float(odds_ratio), p_value=float(p),
            effect_size_name="odds ratio", effect_size_value=float(odds_ratio),
            is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Odds ratio", value=float(odds_ratio))],
        descriptive_stats=[{"row": str(index), **{str(column): int(value) for column, value in row.items()}} for index, row in table.iterrows()],
    )


def chi_square_goodness_of_fit(df: pd.DataFrame, factor: str, expected_proportions: list[float], alpha: float) -> StatisticalResult:
    counts = df[factor].dropna().value_counts(sort=False)
    if len(counts) < 2:
        raise ValueError("拟合优度检验至少需要 2 个类别")
    if expected_proportions:
        if len(expected_proportions) != len(counts):
            raise ValueError("期望比例数量必须与类别数量一致")
        proportions = np.asarray(expected_proportions, dtype=float)
        if np.any(proportions <= 0) or not np.isclose(proportions.sum(), 1.0, atol=1e-6):
            raise ValueError("期望比例必须全部大于 0 且总和为 1")
    else:
        proportions = np.repeat(1 / len(counts), len(counts))
    expected = proportions * counts.sum()
    statistic, p = stats.chisquare(counts.to_numpy(), f_exp=expected)
    w = math.sqrt(float(statistic) / float(counts.sum()))
    warnings = ["部分期望频数小于 5，卡方近似可能不稳定。"] if np.any(expected < 5) else []
    return StatisticalResult(
        analysis_id=f"goodness_of_fit_{factor}",
        design=design_info(df[[factor]].dropna(), fixed=[factor]),
        method=MethodInfo(name="chi_square_goodness_of_fit", label_zh="卡方拟合优度检验", formula=f"frequency({factor}) ~ expected proportions"),
        primary_tests=[PrimaryTestResult(
            effect=factor, statistic_name="chi-square", statistic_value=float(statistic), p_value=float(p), df_num=float(len(counts) - 1),
            effect_size_name="Cohen's w", effect_size_value=w, is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Cohen's w", value=w)],
        descriptive_stats=[{"level": str(level), "observed": int(observed), "expected": float(exp)} for level, observed, exp in zip(counts.index, counts.values, expected)],
        warnings=warnings,
        data_snapshot={"expected_proportions": proportions.tolist()},
    )


def mcnemar_test(df: pd.DataFrame, first: str, second: str, alpha: float) -> StatisticalResult:
    clean = df[[first, second]].dropna()
    first_levels = list(clean[first].unique())
    second_levels = list(clean[second].unique())
    if len(first_levels) != 2 or len(second_levels) != 2:
        raise ValueError("McNemar 检验要求两个变量都恰好有 2 个水平")
    table = pd.crosstab(clean[first], clean[second]).reindex(index=first_levels, columns=second_levels, fill_value=0)
    discordant = int(table.iloc[0, 1] + table.iloc[1, 0])
    exact = discordant < 25
    result = mcnemar(table.to_numpy(), exact=exact, correction=not exact)
    return StatisticalResult(
        analysis_id=f"mcnemar_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="mcnemar_test", label_zh="McNemar 配对分类检验", formula=f"paired({first}, {second})"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} vs {second}", statistic_name="McNemar", statistic_value=float(result.statistic), p_value=float(result.pvalue),
            is_significant=significance(float(result.pvalue), alpha), significance_level=alpha,
            detail=f"不一致对={discordant}；{'精确二项检验' if exact else '连续性校正卡方近似'}",
        )],
        descriptive_stats=[{"row": str(index), **{str(column): int(value) for column, value in row.items()}} for index, row in table.iterrows()],
    )
