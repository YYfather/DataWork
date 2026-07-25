"""分类数据与比例分析方法。

该模块仅处理名义/有序分类结局、比例和列联表，不对列名或业务语义作任何假设。
所有可选参数都由 AnalysisPlan.method_parameters 显式传入，并保留稳定默认值。
"""
from __future__ import annotations

import math
import warnings as pywarnings
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.contingency_tables import (
    SquareTable,
    StratifiedTable,
    Table2x2,
    cochrans_q,
    mcnemar,
)
from statsmodels.stats.inter_rater import aggregate_raters, cohens_kappa, fleiss_kappa
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_chisquare, proportions_ztest
from statsmodels.tools.sm_exceptions import SingularMatrixWarning

from .common import design_info, significance
from .regression_methods import predictor_terms
from .result import (
    CoefficientResult,
    EffectSize,
    FitStatistic,
    MethodInfo,
    PrimaryTestResult,
    StatisticalResult,
)


def _param(parameters: dict[str, Any] | None, key: str, default: Any) -> Any:
    if not parameters:
        return default
    value = parameters.get(key, default)
    return default if value is None else value


def _levels(series: pd.Series) -> list[Any]:
    return list(pd.unique(series.dropna()))


def _statsmodels_alternative(alternative: str) -> str:
    """Map DataWork/SciPy alternative names to statsmodels proportion-test names."""
    mapping = {
        "two-sided": "two-sided",
        "less": "smaller",
        "greater": "larger",
        # Accept statsmodels-native spellings for API/backward compatibility.
        "smaller": "smaller",
        "larger": "larger",
    }
    try:
        return mapping[str(alternative)]
    except KeyError as exc:
        raise ValueError(f"不支持的备择假设: {alternative!r}") from exc


def _ordered_link_distribution(link: str):
    """Return a scipy distribution accepted by statsmodels OrderedModel."""
    mapping = {
        "logit": stats.logistic,
        "probit": stats.norm,
        "cloglog": stats.gumbel_l,
        "loglog": stats.gumbel_r,
        "cauchit": stats.cauchy,
    }
    try:
        return mapping[str(link)]
    except KeyError as exc:
        raise ValueError(f"不支持的有序回归链接函数: {link!r}") from exc


def _choose_level(levels: list[Any], requested: str | None, *, label: str) -> Any:
    if not levels:
        raise ValueError(f"{label}没有有效水平")
    if requested not in {None, ""}:
        for level in levels:
            if str(level) == str(requested):
                return level
        raise ValueError(f"指定的{label} {requested!r} 不在当前数据水平中: {[str(item) for item in levels]}")
    return levels[-1]


def _contingency(df: pd.DataFrame, first: str, second: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean = df[[first, second]].dropna()
    table = pd.crosstab(clean[first], clean[second], dropna=False)
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError("列联分析要求两个分类变量都至少具有 2 个有效水平")
    return clean, table


def _table_rows(table: pd.DataFrame, expected: np.ndarray | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index, (level, values) in enumerate(table.iterrows()):
        for col_index, value in enumerate(values):
            item: dict[str, Any] = {
                "row_level": str(level),
                "column_level": str(table.columns[col_index]),
                "observed": int(value),
            }
            if expected is not None:
                exp = float(expected[row_index, col_index])
                item["expected"] = exp
                item["pearson_residual"] = float((value - exp) / math.sqrt(exp)) if exp > 0 else None
            rows.append(item)
    return rows


def _association_effects(table: np.ndarray, chi2: float) -> tuple[float, float, float]:
    n = float(table.sum())
    rows, cols = table.shape
    minimum_dimension = min(rows - 1, cols - 1)
    cramer_v = math.sqrt(chi2 / (n * minimum_dimension)) if n > 0 and minimum_dimension > 0 else 0.0
    tschuprow_den = math.sqrt((rows - 1) * (cols - 1))
    tschuprow_t = math.sqrt(chi2 / (n * tschuprow_den)) if n > 0 and tschuprow_den > 0 else 0.0
    contingency = math.sqrt(chi2 / (chi2 + n)) if chi2 + n > 0 else 0.0
    return cramer_v, tschuprow_t, contingency


def chi_square_independence(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, table = _contingency(df, first, second)
    correction_mode = str(_param(parameters, "continuity_correction", "auto"))
    correction = table.shape == (2, 2) if correction_mode == "auto" else correction_mode == "on"
    lambda_name = str(_param(parameters, "power_divergence", "pearson"))
    lambda_map: dict[str, str | float | None] = {
        "pearson": None,
        "log-likelihood": "log-likelihood",
        "freeman-tukey": "freeman-tukey",
        "mod-log-likelihood": "mod-log-likelihood",
        "neyman": "neyman",
        "cressie-read": "cressie-read",
    }
    if lambda_name not in lambda_map:
        raise ValueError(f"未知的幂散度统计量: {lambda_name}")
    p_value_method = str(_param(parameters, "p_value_method", "asymptotic"))
    n_resamples = int(_param(parameters, "n_resamples", 9999))
    random_seed = int(_param(parameters, "random_seed", 2026))
    sampling_method = None
    if p_value_method != "asymptotic":
        if lambda_name != "pearson":
            raise ValueError("置换/Monte Carlo p 值仅支持 Pearson χ²；请将统计量类型改为 Pearson。")
        correction = False
        rng = np.random.default_rng(random_seed)
        sampling_method = stats.PermutationMethod(n_resamples=n_resamples, rng=rng) if p_value_method == "permutation" else stats.MonteCarloMethod(n_resamples=n_resamples, rng=rng)
    chi2, p_value, dof, expected = stats.chi2_contingency(
        table.to_numpy(), correction=correction, lambda_=lambda_map[lambda_name], method=sampling_method
    )
    cramer_v, tschuprow_t, contingency = _association_effects(table.to_numpy(), float(chi2))
    expected_lt5 = int((expected < 5).sum())
    expected_lt1 = int((expected < 1).sum())
    ratio_lt5 = expected_lt5 / expected.size
    warnings: list[str] = []
    if expected_lt1:
        warnings.append(f"有 {expected_lt1} 个单元格期望频数小于 1，渐近卡方近似不可靠。")
    if ratio_lt5 > 0.2:
        warnings.append(f"{ratio_lt5:.1%} 的单元格期望频数小于 5；建议合并稀疏类别或改用精确/置换方法。")
    statistic_label = "χ²" if lambda_name == "pearson" else f"幂散度({lambda_name})"
    return StatisticalResult(
        analysis_id=f"chi_square_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(
            name="chi_square_independence",
            label_zh="卡方独立性/幂散度检验",
            formula=f"{first} × {second}",
            assumptions=["观测相互独立", "类别互斥", "渐近期望频数条件"],
        ),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="chi-square" if lambda_name == "pearson" else statistic_label,
            statistic_value=float(chi2), p_value=float(p_value), df_num=float(dof),
            effect_size_name="Cramer's V", effect_size_value=cramer_v,
            is_significant=significance(float(p_value), alpha), significance_level=alpha,
            detail=f"p值方法={p_value_method}；连续性校正={'是' if correction else '否'}；期望频数<5: {expected_lt5}/{expected.size}",
        )],
        effect_sizes=[
            EffectSize(measure="Cramer's V", value=cramer_v),
            EffectSize(measure="Tschuprow's T", value=tschuprow_t),
            EffectSize(measure="Contingency coefficient", value=contingency),
        ],
        fit_statistics=[
            FitStatistic(name="Minimum expected frequency", value=float(expected.min())),
            FitStatistic(name="Cells expected < 5", value=float(expected_lt5)),
            FitStatistic(name="Cells expected < 1", value=float(expected_lt1)),
        ],
        descriptive_stats=_table_rows(table, expected),
        warnings=warnings,
        data_snapshot={
            "row_levels": [str(item) for item in table.index],
            "column_levels": [str(item) for item in table.columns],
            "continuity_correction": correction,
            "power_divergence": lambda_name,
            "p_value_method": p_value_method,
            "n_resamples": n_resamples if p_value_method != "asymptotic" else None,
            "random_seed": random_seed if p_value_method != "asymptotic" else None,
        },
    )


def _exact_2x2_common(df: pd.DataFrame, first: str, second: str) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    clean, table = _contingency(df, first, second)
    if table.shape != (2, 2):
        raise ValueError(f"该精确检验要求 2×2 列联表，当前为 {table.shape[0]}×{table.shape[1]}")
    return clean, table, table.to_numpy(dtype=int)


def fisher_exact_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, table, observed = _exact_2x2_common(df, first, second)
    alternative = str(_param(parameters, "alternative", "two-sided"))
    odds_ratio, p_value = stats.fisher_exact(observed, alternative=alternative)
    table_model = Table2x2(observed, shift_zeros=True)
    lower, upper = table_model.oddsratio_confint(alpha=alpha)
    return StatisticalResult(
        analysis_id=f"fisher_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(name="fisher_exact", label_zh="Fisher 精确检验", formula=f"{first} × {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="odds ratio", statistic_value=float(odds_ratio),
            p_value=float(p_value), effect_size_name="odds ratio", effect_size_value=float(odds_ratio),
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(float(p_value), alpha),
            significance_level=alpha, detail=f"alternative={alternative}",
        )],
        effect_sizes=[EffectSize(measure="Odds ratio", value=float(odds_ratio), ci_lower=float(lower), ci_upper=float(upper))],
        descriptive_stats=_table_rows(table),
        data_snapshot={"alternative": alternative},
    )


def barnard_exact_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, table, observed = _exact_2x2_common(df, first, second)
    alternative = str(_param(parameters, "alternative", "two-sided"))
    pooled = bool(_param(parameters, "pooled", True))
    grid_points = int(_param(parameters, "grid_points", 32))
    result = stats.barnard_exact(observed, alternative=alternative, pooled=pooled, n=grid_points)
    table_model = Table2x2(observed, shift_zeros=True)
    odds_ratio = float(table_model.oddsratio)
    lower, upper = table_model.oddsratio_confint(alpha=alpha)
    return StatisticalResult(
        analysis_id=f"barnard_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(name="barnard_exact", label_zh="Barnard 无条件精确检验", formula=f"{first} × {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="Barnard Wald", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), effect_size_name="odds ratio", effect_size_value=odds_ratio,
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"alternative={alternative}; pooled={pooled}; grid={grid_points}",
        )],
        effect_sizes=[EffectSize(measure="Odds ratio", value=odds_ratio, ci_lower=float(lower), ci_upper=float(upper))],
        descriptive_stats=_table_rows(table),
    )


def boschloo_exact_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, table, observed = _exact_2x2_common(df, first, second)
    alternative = str(_param(parameters, "alternative", "two-sided"))
    grid_points = int(_param(parameters, "grid_points", 32))
    result = stats.boschloo_exact(observed, alternative=alternative, n=grid_points)
    table_model = Table2x2(observed, shift_zeros=True)
    odds_ratio = float(table_model.oddsratio)
    lower, upper = table_model.oddsratio_confint(alpha=alpha)
    return StatisticalResult(
        analysis_id=f"boschloo_{first}_{second}",
        design=design_info(clean, fixed=[first, second]),
        method=MethodInfo(name="boschloo_exact", label_zh="Boschloo 精确检验", formula=f"{first} × {second}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second}", statistic_name="Fisher p statistic", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), effect_size_name="odds ratio", effect_size_value=odds_ratio,
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"alternative={alternative}; grid={grid_points}",
        )],
        effect_sizes=[EffectSize(measure="Odds ratio", value=odds_ratio, ci_lower=float(lower), ci_upper=float(upper))],
        descriptive_stats=_table_rows(table),
    )


def exact_binomial_test(
    df: pd.DataFrame,
    factor: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    values = df[factor].dropna()
    levels = _levels(values)
    if len(levels) != 2:
        raise ValueError(f"精确二项检验要求分类变量恰好 2 个水平，当前为 {len(levels)}")
    success = _choose_level(levels, str(_param(parameters, "success_level", "")), label="成功水平")
    p0 = float(_param(parameters, "null_proportion", 0.5))
    alternative = str(_param(parameters, "alternative", "two-sided"))
    ci_method = str(_param(parameters, "ci_method", "exact"))
    count = int((values == success).sum())
    n = int(len(values))
    result = stats.binomtest(count, n, p=p0, alternative=alternative)
    ci = result.proportion_ci(confidence_level=1 - alpha, method=ci_method)
    observed = count / n
    return StatisticalResult(
        analysis_id=f"binomial_{factor}",
        design=design_info(df[[factor]].dropna(), fixed=[factor]),
        method=MethodInfo(name="exact_binomial_test", label_zh="精确二项检验", formula=f"P({factor}={success}) = {p0}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{factor}={success}", statistic_name="success proportion", statistic_value=observed,
            p_value=float(result.pvalue), effect_size_name="proportion difference", effect_size_value=float(observed - p0),
            ci_lower=float(ci.low), ci_upper=float(ci.high), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"success={count}/{n}; alternative={alternative}; CI={ci_method}",
        )],
        descriptive_stats=[
            {"level": str(level), "count": int((values == level).sum()), "proportion": float((values == level).mean())}
            for level in levels
        ],
        data_snapshot={"success_level": str(success), "null_proportion": p0, "alternative": alternative},
    )


def one_sample_proportion_ztest(
    df: pd.DataFrame,
    factor: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    values = df[factor].dropna()
    levels = _levels(values)
    if len(levels) != 2:
        raise ValueError("单样本比例 z 检验要求变量恰好 2 个水平")
    success = _choose_level(levels, str(_param(parameters, "success_level", "")), label="成功水平")
    p0 = float(_param(parameters, "null_proportion", 0.5))
    alternative = str(_param(parameters, "alternative", "two-sided"))
    count, n = int((values == success).sum()), int(len(values))
    statistic, p_value = proportions_ztest(count, n, value=p0, alternative=_statsmodels_alternative(alternative))
    observed = count / n
    se = math.sqrt(observed * (1 - observed) / n) if n else 0.0
    critical = float(stats.norm.ppf(1 - alpha / 2))
    lower, upper = max(0.0, observed - critical * se), min(1.0, observed + critical * se)
    return StatisticalResult(
        analysis_id=f"one_prop_z_{factor}",
        design=design_info(df[[factor]].dropna(), fixed=[factor]),
        method=MethodInfo(name="one_sample_proportion_ztest", label_zh="单样本比例 z 检验", formula=f"P({factor}={success}) = {p0}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{factor}={success}", statistic_name="z", statistic_value=float(statistic), p_value=float(p_value),
            effect_size_name="proportion difference", effect_size_value=float(observed - p0),
            ci_lower=lower, ci_upper=upper, is_significant=significance(float(p_value), alpha), significance_level=alpha,
            detail=f"success={count}/{n}; alternative={alternative}",
        )],
        descriptive_stats=[{"success_level": str(success), "count": count, "n": n, "proportion": observed}],
        warnings=["样本量或期望成功/失败数较小时，优先使用精确二项检验。"] if min(count, n - count) < 5 else [],
    )


def two_proportion_ztest(
    df: pd.DataFrame,
    outcome: str,
    group: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[[outcome, group]].dropna()
    outcome_levels, group_levels = _levels(clean[outcome]), _levels(clean[group])
    if len(outcome_levels) != 2 or len(group_levels) != 2:
        raise ValueError("两独立比例 z 检验要求二元结局和二水平分组因素")
    success = _choose_level(outcome_levels, str(_param(parameters, "success_level", "")), label="成功水平")
    alternative = str(_param(parameters, "alternative", "two-sided"))
    counts = np.asarray([int(((clean[group] == level) & (clean[outcome] == success)).sum()) for level in group_levels])
    nobs = np.asarray([int((clean[group] == level).sum()) for level in group_levels])
    statistic, p_value = proportions_ztest(counts, nobs, alternative=_statsmodels_alternative(alternative))
    proportions = counts / nobs
    risk_difference = float(proportions[0] - proportions[1])
    risk_ratio = float(proportions[0] / proportions[1]) if proportions[1] > 0 else math.inf
    table = pd.DataFrame(
        [[counts[0], nobs[0] - counts[0]], [counts[1], nobs[1] - counts[1]]],
        index=[str(item) for item in group_levels], columns=[str(success), f"非{success}"],
    )
    table_model = Table2x2(table.to_numpy(), shift_zeros=True)
    odds_ratio = float(table_model.oddsratio)
    return StatisticalResult(
        analysis_id=f"two_prop_z_{outcome}_{group}",
        design=design_info(clean, dependent=[outcome], fixed=[group]),
        method=MethodInfo(name="two_proportion_ztest", label_zh="两独立比例 z 检验", formula=f"P({outcome}={success}) ~ {group}"),
        primary_tests=[PrimaryTestResult(
            effect=group, statistic_name="z", statistic_value=float(statistic), p_value=float(p_value),
            effect_size_name="risk difference", effect_size_value=risk_difference,
            is_significant=significance(float(p_value), alpha), significance_level=alpha,
            detail=f"{group_levels[0]}={proportions[0]:.4f}; {group_levels[1]}={proportions[1]:.4f}; alternative={alternative}",
        )],
        effect_sizes=[
            EffectSize(measure="Risk difference", value=risk_difference),
            EffectSize(measure="Risk ratio", value=risk_ratio),
            EffectSize(measure="Odds ratio", value=odds_ratio),
        ],
        descriptive_stats=_table_rows(table),
        warnings=["至少一组成功或失败计数小于 5，建议改用 Fisher/Barnard/Boschloo 精确检验。"] if np.min(np.r_[counts, nobs-counts]) < 5 else [],
        data_snapshot={"success_level": str(success), "group_order": [str(item) for item in group_levels]},
    )


def k_proportion_chi_square(
    df: pd.DataFrame,
    outcome: str,
    group: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[[outcome, group]].dropna()
    outcome_levels, group_levels = _levels(clean[outcome]), _levels(clean[group])
    if len(outcome_levels) != 2 or len(group_levels) < 2:
        raise ValueError("多组比例卡方检验要求二元结局和至少二水平分组因素")
    success = _choose_level(outcome_levels, str(_param(parameters, "success_level", "")), label="成功水平")
    counts = np.asarray([int(((clean[group] == level) & (clean[outcome] == success)).sum()) for level in group_levels])
    nobs = np.asarray([int((clean[group] == level).sum()) for level in group_levels])
    statistic, p_value, table = proportions_chisquare(counts, nobs)
    proportions = counts / nobs
    effect_w = math.sqrt(float(statistic) / float(nobs.sum()))
    contrasts = []
    if bool(_param(parameters, "pairwise_posthoc", True)) and len(group_levels) > 2:
        raw_rows: list[tuple[int, int, float, float]] = []
        for left in range(len(group_levels) - 1):
            for right in range(left + 1, len(group_levels)):
                z_value, pair_p = proportions_ztest(counts[[left, right]], nobs[[left, right]])
                raw_rows.append((left, right, float(z_value), float(pair_p)))
        correction = str(_param(parameters, "pairwise_p_adjust", "holm"))
        adjusted = np.asarray([row[3] for row in raw_rows], dtype=float)
        if correction != "none":
            adjusted = multipletests(adjusted, alpha=alpha, method=correction)[1]
        from .result import ContrastResult
        for row, adjusted_p in zip(raw_rows, adjusted):
            left, right, z_value, pair_p = row
            difference = float(proportions[left] - proportions[right])
            contrasts.append(ContrastResult(
                contrast=f"{group_levels[left]} - {group_levels[right]}", estimate=difference,
                t_value=z_value, p_value=pair_p, p_adjusted=float(adjusted_p),
                significant=float(adjusted_p) < alpha, correction=correction,
            ))
    return StatisticalResult(
        analysis_id=f"k_prop_chi_{outcome}_{group}",
        design=design_info(clean, dependent=[outcome], fixed=[group]),
        method=MethodInfo(name="k_proportion_chi_square", label_zh="多组比例卡方检验", formula=f"P({outcome}={success}) ~ {group}"),
        primary_tests=[PrimaryTestResult(
            effect=group, statistic_name="chi-square", statistic_value=float(statistic), p_value=float(p_value),
            df_num=float(len(group_levels)-1), effect_size_name="Cohen's w", effect_size_value=effect_w,
            is_significant=significance(float(p_value), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Cohen's w", value=effect_w)],
        descriptive_stats=[{"group": str(level), "success": int(count), "n": int(n), "proportion": float(prop)} for level, count, n, prop in zip(group_levels, counts, nobs, proportions)],
        contrasts=contrasts,
        data_snapshot={"success_level": str(success), "observed_table": np.asarray(table).tolist()},
    )


def mcnemar_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[[first, second]].dropna()
    first_levels, second_levels = _levels(clean[first]), _levels(clean[second])
    if len(first_levels) != 2 or len(second_levels) != 2:
        raise ValueError("McNemar 检验要求两个配对变量都恰好有 2 个水平")
    all_levels = list(dict.fromkeys(first_levels + second_levels))
    if len(all_levels) != 2:
        raise ValueError("两个配对变量应使用相同的两个分类水平")
    table = pd.crosstab(clean[first], clean[second]).reindex(index=all_levels, columns=all_levels, fill_value=0)
    discordant = int(table.iloc[0, 1] + table.iloc[1, 0])
    mode = str(_param(parameters, "mcnemar_mode", "auto"))
    exact_threshold = int(_param(parameters, "exact_threshold", 25))
    exact = discordant < exact_threshold if mode == "auto" else mode == "exact"
    correction = bool(_param(parameters, "continuity_correction", True)) and not exact
    result = mcnemar(table.to_numpy(), exact=exact, correction=correction)
    odds_ratio = float(table.iloc[0, 1] / table.iloc[1, 0]) if table.iloc[1, 0] else math.inf
    return StatisticalResult(
        analysis_id=f"mcnemar_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="mcnemar_test", label_zh="McNemar 配对分类检验", formula=f"paired({first}, {second})"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} vs {second}", statistic_name="McNemar", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), effect_size_name="discordant odds ratio", effect_size_value=odds_ratio,
            is_significant=significance(float(result.pvalue), alpha), significance_level=alpha,
            detail=f"不一致对={discordant}；mode={'exact' if exact else 'asymptotic'}；correction={correction}",
        )],
        effect_sizes=[EffectSize(measure="Discordant odds ratio", value=odds_ratio)],
        descriptive_stats=_table_rows(table),
    )


def cochran_q_test(
    df: pd.DataFrame,
    variables: list[str],
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[variables].dropna()
    if len(variables) < 3:
        raise ValueError("Cochran Q 检验至少需要 3 个配对二元变量")
    mappings: dict[str, dict[Any, int]] = {}
    matrix = np.empty((len(clean), len(variables)), dtype=int)
    requested_success = str(_param(parameters, "success_level", ""))
    if clean.empty:
        raise ValueError("Cochran Q 检验没有完整的配对观测")
    shared_levels: set[str] | None = None
    for index, variable in enumerate(variables):
        levels = _levels(clean[variable])
        if len(levels) != 2:
            raise ValueError(f"变量 {variable!r} 不是二元变量")
        text_levels = {str(level) for level in levels}
        if shared_levels is None:
            shared_levels = text_levels
        elif text_levels != shared_levels:
            raise ValueError("Cochran Q 的所有配对变量必须使用相同的两个分类水平")
        success = _choose_level(levels, requested_success, label=f"{variable} 成功水平")
        mappings[variable] = {level: int(level == success) for level in levels}
        matrix[:, index] = clean[variable].map(mappings[variable]).to_numpy(dtype=int)
    # 至少一名对象必须在不同条件下出现不同二元结果；否则 Q 统计量分母为 0。
    discordant_rows = np.any(matrix != matrix[:, [0]], axis=1)
    if not bool(np.any(discordant_rows)):
        raise ValueError("所有对象在各条件下的二元结果完全一致，Cochran Q 统计量无法定义")
    result = cochrans_q(matrix, return_object=True)
    n, k = matrix.shape
    kendall_w = float(result.statistic / (n * (k - 1))) if n * (k - 1) else 0.0
    return StatisticalResult(
        analysis_id="cochran_q",
        design=design_info(clean, dependent=variables),
        method=MethodInfo(name="cochran_q_test", label_zh="Cochran Q 配对比例检验", formula="paired binary outcomes across conditions"),
        primary_tests=[PrimaryTestResult(
            effect="配对二元条件", statistic_name="Q", statistic_value=float(result.statistic), p_value=float(result.pvalue),
            df_num=float(k-1), effect_size_name="Kendall's W (binary block)", effect_size_value=kendall_w,
            is_significant=significance(float(result.pvalue), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Kendall's W", value=kendall_w)],
        descriptive_stats=[{"variable": variable, "success_count": int(matrix[:, index].sum()), "n": n, "success_rate": float(matrix[:, index].mean())} for index, variable in enumerate(variables)],
        data_snapshot={"outcome_mappings": {key: {str(k): v for k, v in value.items()} for key, value in mappings.items()}},
    )


def _square_paired_table(df: pd.DataFrame, first: str, second: str, shift_zeros: bool) -> tuple[pd.DataFrame, pd.DataFrame, SquareTable]:
    clean = df[[first, second]].dropna()
    categories = list(dict.fromkeys(_levels(clean[first]) + _levels(clean[second])))
    if len(categories) < 3:
        raise ValueError("多分类配对检验至少需要 3 个共同类别；二分类请使用 McNemar 检验")
    table = pd.crosstab(clean[first], clean[second]).reindex(index=categories, columns=categories, fill_value=0)
    return clean, table, SquareTable(table.to_numpy(), shift_zeros=shift_zeros)


def bowker_symmetry_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    shift_zeros = bool(_param(parameters, "shift_zeros", False))
    clean, table, square = _square_paired_table(df, first, second, shift_zeros)
    result = square.symmetry(method="bowker")
    return StatisticalResult(
        analysis_id=f"bowker_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="bowker_symmetry", label_zh="Bowker 对称性检验", formula=f"paired({first}, {second})"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} vs {second}", statistic_name="chi-square", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), df_num=float(result.df), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"shift_zeros={shift_zeros}",
        )],
        descriptive_stats=_table_rows(table),
    )


def stuart_maxwell_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    shift_zeros = bool(_param(parameters, "shift_zeros", False))
    method = str(_param(parameters, "homogeneity_method", "stuart_maxwell"))
    clean, table, square = _square_paired_table(df, first, second, shift_zeros)
    with pywarnings.catch_warnings():
        pywarnings.simplefilter("ignore", SingularMatrixWarning)
        result = square.homogeneity(method=method)
    if not np.all(np.isfinite([result.statistic, result.pvalue, result.df])):
        raise ValueError(
            "Stuart–Maxwell/Bhapkar 检验的边际差协方差矩阵不可逆，无法计算有限统计结果"
        )
    return StatisticalResult(
        analysis_id=f"marginal_homogeneity_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="stuart_maxwell", label_zh="Stuart–Maxwell/Bhapkar 边际同质性检验", formula=f"paired margins({first}, {second})"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} vs {second}", statistic_name="chi-square", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), df_num=float(result.df), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"method={method}; shift_zeros={shift_zeros}",
        )],
        descriptive_stats=_table_rows(table),
    )


def _stratified_2x2(df: pd.DataFrame, outcome: str, exposure: str, strata: str, parameters: dict[str, Any] | None) -> tuple[pd.DataFrame, list[Any], np.ndarray, Any, Any]:
    clean = df[[outcome, exposure, strata]].dropna()
    outcome_levels, exposure_levels = _levels(clean[outcome]), _levels(clean[exposure])
    if len(outcome_levels) != 2 or len(exposure_levels) != 2:
        raise ValueError("分层 2×2 分析要求二元结局与二元暴露因素")
    success = _choose_level(outcome_levels, str(_param(parameters, "success_level", "")), label="成功水平")
    exposed = _choose_level(exposure_levels, str(_param(parameters, "exposed_level", "")), label="暴露水平")
    strata_levels = _levels(clean[strata])
    if len(strata_levels) < 2:
        raise ValueError("分层分析至少需要 2 个分层水平")
    tables = []
    for level in strata_levels:
        subset = clean[clean[strata] == level]
        table = np.asarray([
            [int(((subset[exposure] == exposed) & (subset[outcome] == success)).sum()), int(((subset[exposure] == exposed) & (subset[outcome] != success)).sum())],
            [int(((subset[exposure] != exposed) & (subset[outcome] == success)).sum()), int(((subset[exposure] != exposed) & (subset[outcome] != success)).sum())],
        ], dtype=float)
        if table.sum() == 0:
            continue
        tables.append(table)
    if len(tables) < 2:
        raise ValueError("有效分层 2×2 表少于 2 个")
    stacked = np.stack(tables, axis=2)
    return clean, strata_levels, stacked, success, exposed


def cochran_mantel_haenszel(
    df: pd.DataFrame,
    outcome: str,
    exposure: str,
    strata: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, strata_levels, tables, success, exposed = _stratified_2x2(df, outcome, exposure, strata, parameters)
    shift_zeros = bool(_param(parameters, "shift_zeros", False))
    correction = bool(_param(parameters, "continuity_correction", False))
    model = StratifiedTable(tables, shift_zeros=shift_zeros)
    result = model.test_null_odds(correction=correction)
    lower, upper = model.oddsratio_pooled_confint(alpha=alpha)
    return StatisticalResult(
        analysis_id=f"cmh_{outcome}_{exposure}_{strata}",
        design=design_info(clean, dependent=[outcome], fixed=[exposure, strata]),
        method=MethodInfo(name="cochran_mantel_haenszel", label_zh="Cochran–Mantel–Haenszel 分层检验", formula=f"{outcome} ~ {exposure} | {strata}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{exposure}（控制 {strata}）", statistic_name="CMH chi-square", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), df_num=1.0, effect_size_name="pooled odds ratio", effect_size_value=float(model.oddsratio_pooled),
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"success={success}; exposed={exposed}; strata={tables.shape[2]}; correction={correction}",
        )],
        effect_sizes=[EffectSize(measure="Pooled odds ratio", value=float(model.oddsratio_pooled), ci_lower=float(lower), ci_upper=float(upper))],
        fit_statistics=[FitStatistic(name="Pooled risk ratio", value=float(model.riskratio_pooled))],
        data_snapshot={"strata_levels": [str(item) for item in strata_levels], "tables": tables.tolist(), "shift_zeros": shift_zeros},
    )


def breslow_day_test(
    df: pd.DataFrame,
    outcome: str,
    exposure: str,
    strata: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean, strata_levels, tables, success, exposed = _stratified_2x2(df, outcome, exposure, strata, parameters)
    shift_zeros = bool(_param(parameters, "shift_zeros", False))
    tarone_adjust = bool(_param(parameters, "tarone_adjust", False))
    model = StratifiedTable(tables, shift_zeros=shift_zeros)
    result = model.test_equal_odds(adjust=tarone_adjust)
    return StatisticalResult(
        analysis_id=f"breslow_day_{outcome}_{exposure}_{strata}",
        design=design_info(clean, dependent=[outcome], fixed=[exposure, strata]),
        method=MethodInfo(name="breslow_day", label_zh="Breslow–Day 比值比同质性检验", formula=f"OR({outcome},{exposure}) homogeneous across {strata}"),
        primary_tests=[PrimaryTestResult(
            effect=f"{exposure}×{strata} 比值比同质性", statistic_name="chi-square", statistic_value=float(result.statistic),
            p_value=float(result.pvalue), df_num=float(tables.shape[2]-1), is_significant=significance(float(result.pvalue), alpha),
            significance_level=alpha, detail=f"success={success}; exposed={exposed}; Tarone={tarone_adjust}",
        )],
        data_snapshot={"strata_levels": [str(item) for item in strata_levels], "tables": tables.tolist(), "shift_zeros": shift_zeros},
        report_constraints=["显著结果说明各分层比值比不齐，不应只报告单一合并比值比。"],
    )



def cohen_kappa_test(
    df: pd.DataFrame,
    first: str,
    second: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[[first, second]].dropna()
    levels = list(dict.fromkeys([str(item) for item in clean[first].tolist() + clean[second].tolist()]))
    if len(levels) < 2:
        raise ValueError("Cohen's kappa 至少需要 2 个共同类别")
    table = pd.crosstab(
        pd.Categorical(clean[first].astype(str), categories=levels),
        pd.Categorical(clean[second].astype(str), categories=levels),
        dropna=False,
    )
    weight_mode = str(_param(parameters, "weights", "none"))
    weights = None
    if weight_mode in {"linear", "quadratic"}:
        indices = np.arange(len(levels), dtype=float)
        distance = np.abs(indices[:, None] - indices[None, :])
        if weight_mode == "linear":
            weights = distance
        else:
            weights = distance ** 2
    result = cohens_kappa(table.to_numpy(), weights=weights, wt="linear" if weight_mode == "linear" else None)
    kappa = float(result.kappa)
    se = float(result.std_kappa)
    z_value = float(result.z_value)
    p_value = float(result.pvalue_two_sided)
    lower, upper = float(result.kappa_low), float(result.kappa_upp)
    observed_agreement = float(np.trace(table.to_numpy()) / table.to_numpy().sum())
    return StatisticalResult(
        analysis_id=f"cohen_kappa_{first}_{second}",
        design=design_info(clean, dependent=[first, second]),
        method=MethodInfo(name="cohen_kappa", label_zh="Cohen's kappa 一致性检验", formula=f"agreement({first}, {second})"),
        primary_tests=[PrimaryTestResult(
            effect=f"{first} 与 {second} 一致性", statistic_name="kappa", statistic_value=kappa,
            p_value=p_value, effect_size_name="Cohen's kappa", effect_size_value=kappa,
            ci_lower=float(lower), ci_upper=float(upper), is_significant=significance(p_value, alpha),
            significance_level=alpha, detail=f"weights={weight_mode}; observed agreement={observed_agreement:.4f}",
        )],
        effect_sizes=[EffectSize(measure="Cohen's kappa", value=kappa, ci_lower=float(lower), ci_upper=float(upper))],
        descriptive_stats=_table_rows(table),
        data_snapshot={"levels": levels, "weights": weight_mode},
        report_constraints=["kappa 衡量超出偶然一致性的程度，不等同于准确率或因果一致性。"],
    )


def fleiss_kappa_test(
    df: pd.DataFrame,
    rating_columns: list[str],
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    if len(rating_columns) < 3:
        raise ValueError("Fleiss kappa 至少需要 3 个评分者/分类变量")
    clean = df[rating_columns].dropna()
    encoded, categories = aggregate_raters(clean.astype(str).to_numpy())
    method = str(_param(parameters, "kappa_method", "fleiss"))
    with pywarnings.catch_warnings():
        pywarnings.simplefilter("ignore", RuntimeWarning)
        value = float(fleiss_kappa(encoded, method=method))
    if not np.isfinite(value):
        raise ValueError("评分类别缺少有效变异，Fleiss/Randolph kappa 无法计算有限结果")
    return StatisticalResult(
        analysis_id="fleiss_kappa_" + "_".join(rating_columns),
        design=design_info(clean, dependent=rating_columns),
        method=MethodInfo(name="fleiss_kappa", label_zh="Fleiss/Randolph 多评分者 kappa", formula="agreement(" + ", ".join(rating_columns) + ")"),
        primary_tests=[PrimaryTestResult(
            effect="多评分者一致性", statistic_name="kappa", statistic_value=value, p_value=None,
            effect_size_name="kappa", effect_size_value=value, is_significant=None,
            significance_level=alpha, detail=f"method={method}; raters={len(rating_columns)}; subjects={len(clean)}",
        )],
        effect_sizes=[EffectSize(measure=f"{method.title()} kappa", value=value)],
        data_snapshot={"categories": [str(item) for item in categories], "method": method},
        report_constraints=["当前输出 kappa 点估计；不以伪造的 p 值判断显著性。"],
    )


def cochran_armitage_trend_test(
    df: pd.DataFrame,
    outcome: str,
    ordered_factor: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    clean = df[[outcome, ordered_factor]].dropna()
    outcome_levels = _levels(clean[outcome])
    factor_levels = [str(item) for item in _levels(clean[ordered_factor])]
    if len(outcome_levels) != 2 or len(factor_levels) < 3:
        raise ValueError("Cochran–Armitage 趋势检验要求二元结局和至少 3 个有序因素水平")
    success = _choose_level(outcome_levels, str(_param(parameters, "success_level", "")), label="成功水平")
    level_order_text = str(_param(parameters, "level_order", "")).strip()
    level_order = [item.strip() for item in level_order_text.split(",") if item.strip()] if level_order_text else factor_levels
    if set(level_order) != set(factor_levels) or len(level_order) != len(factor_levels):
        raise ValueError(f"有序水平必须完整覆盖当前类别: {factor_levels}")
    scores_text = str(_param(parameters, "scores", "")).strip()
    scores = np.asarray([float(item.strip()) for item in scores_text.split(",") if item.strip()], dtype=float) if scores_text else np.arange(len(level_order), dtype=float)
    if len(scores) != len(level_order) or np.unique(scores).size < 2:
        raise ValueError("趋势得分数量必须与有序水平数量一致，且至少有两个不同得分")
    successes = np.asarray([int(((clean[ordered_factor].astype(str) == level) & (clean[outcome] == success)).sum()) for level in level_order], dtype=float)
    totals = np.asarray([int((clean[ordered_factor].astype(str) == level).sum()) for level in level_order], dtype=float)
    if np.any(totals == 0):
        raise ValueError("至少一个有序水平没有有效观测")
    n_total = totals.sum()
    success_total = successes.sum()
    p_pool = success_total / n_total
    centered = scores - np.average(scores, weights=totals)
    numerator = float(np.sum(centered * successes))
    variance = float(p_pool * (1 - p_pool) * np.sum(totals * centered ** 2))
    if variance <= 0:
        raise ValueError("总体成功比例为 0 或 1，无法执行趋势检验")
    z_value = numerator / math.sqrt(variance)
    alternative = str(_param(parameters, "alternative", "two-sided"))
    if alternative == "greater":
        p_value = float(stats.norm.sf(z_value))
    elif alternative == "less":
        p_value = float(stats.norm.cdf(z_value))
    else:
        p_value = float(2 * stats.norm.sf(abs(z_value)))
    proportions = successes / totals
    return StatisticalResult(
        analysis_id=f"cochran_armitage_{outcome}_{ordered_factor}",
        design=design_info(clean, dependent=[outcome], fixed=[ordered_factor]),
        method=MethodInfo(name="cochran_armitage_trend", label_zh="Cochran–Armitage 比例趋势检验", formula=f"trend P({outcome}={success}) ~ ordered({ordered_factor})"),
        primary_tests=[PrimaryTestResult(
            effect=ordered_factor, statistic_name="z", statistic_value=float(z_value), p_value=p_value,
            effect_size_name="proportion range", effect_size_value=float(proportions[-1] - proportions[0]),
            is_significant=significance(p_value, alpha), significance_level=alpha,
            detail=f"alternative={alternative}; scores={scores.tolist()}",
        )],
        descriptive_stats=[{"level": level, "score": float(score), "success": int(count), "n": int(n), "proportion": float(prop)} for level, score, count, n, prop in zip(level_order, scores, successes, totals, proportions)],
        data_snapshot={"success_level": str(success), "level_order": level_order, "scores": scores.tolist()},
        report_constraints=["水平顺序与趋势得分必须在查看结果前确定；事后调整得分会使 p 值失去预设检验含义。"],
    )

def multinomial_logistic_regression(
    df: pd.DataFrame,
    outcome: str,
    fixed_factors: list[str],
    covariates: list[str],
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    required = [outcome] + fixed_factors + covariates
    clean = df[required].copy()
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    levels = _levels(clean[outcome])
    if len(levels) < 3:
        raise ValueError("多项 Logistic 回归要求因变量至少 3 个无序水平")
    reference_text = str(_param(parameters, "reference_level", "")).strip()
    if reference_text:
        reference = _choose_level(levels, reference_text, label="参考类别")
        levels = [reference] + [level for level in levels if level != reference]
    terms = predictor_terms(fixed_factors, covariates)
    if not terms:
        raise ValueError("多项 Logistic 回归至少需要一个预测变量")
    maxiter = int(_param(parameters, "max_iterations", 200))
    clean = clean.assign(_multinomial_outcome=pd.Categorical(clean[outcome], categories=levels).codes)
    formula = "_multinomial_outcome ~ " + " + ".join(terms)
    with pywarnings.catch_warnings(record=True) as caught:
        pywarnings.simplefilter("always")
        fit = smf.mnlogit(formula, data=clean).fit(method="newton", maxiter=maxiter, disp=False)
    ci = fit.conf_int(alpha=alpha)
    coefficients: list[CoefficientResult] = []
    for class_index in fit.params.columns:
        class_label = str(levels[int(class_index) + 1]) if int(class_index) + 1 < len(levels) else str(class_index)
        for term in fit.params.index:
            estimate = float(fit.params.loc[term, class_index])
            ci_key = str(int(class_index) + 1)
            ci_row = ci.loc[(ci_key, term)] if isinstance(ci.index, pd.MultiIndex) else None
            coefficients.append(CoefficientResult(
                term=f"{class_label} vs {levels[0]} · {term}", estimate=estimate,
                se=float(fit.bse.loc[term, class_index]), statistic_name="z",
                statistic_value=float(fit.tvalues.loc[term, class_index]), p_value=float(fit.pvalues.loc[term, class_index]),
                ci_lower=float(ci_row.iloc[0]) if ci_row is not None else None,
                ci_upper=float(ci_row.iloc[1]) if ci_row is not None else None,
                transformed_name="relative risk ratio", transformed_value=float(math.exp(estimate)),
                significant=significance(float(fit.pvalues.loc[term, class_index]), alpha),
            ))
    llr_p = float(fit.llr_pvalue)
    return StatisticalResult(
        analysis_id=f"multinomial_logit_{outcome}",
        design=design_info(clean, dependent=[outcome], fixed=fixed_factors, covariates=covariates),
        method=MethodInfo(name="multinomial_logistic_regression", label_zh="多项 Logistic 回归", formula=f"{outcome} ~ " + " + ".join(terms)),
        primary_tests=[PrimaryTestResult(
            effect="整体多项 Logistic 模型", statistic_name="likelihood-ratio chi-square", statistic_value=float(fit.llr),
            p_value=llr_p, df_num=float(fit.df_model), effect_size_name="McFadden pseudo R-squared", effect_size_value=float(fit.prsquared),
            is_significant=significance(llr_p, alpha), significance_level=alpha,
        )],
        coefficients=coefficients,
        fit_statistics=[FitStatistic(name="AIC", value=float(fit.aic)), FitStatistic(name="BIC", value=float(fit.bic)), FitStatistic(name="Pseudo R-squared", value=float(fit.prsquared))],
        warnings=[str(item.message) for item in caught] + ([] if fit.mle_retvals.get("converged", False) else ["多项 Logistic 模型未收敛。"]),
        data_snapshot={"outcome_levels": [str(item) for item in levels], "reference_level": str(levels[0]), "n": int(fit.nobs)},
    )


def ordinal_logistic_regression(
    df: pd.DataFrame,
    outcome: str,
    fixed_factors: list[str],
    covariates: list[str],
    alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    required = [outcome] + fixed_factors + covariates
    clean = df[required].copy()
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    level_order_text = str(_param(parameters, "level_order", "")).strip()
    observed_levels = [str(item) for item in _levels(clean[outcome])]
    level_order = [item.strip() for item in level_order_text.split(",") if item.strip()] if level_order_text else observed_levels
    if len(level_order) < 3 or set(level_order) != set(observed_levels):
        raise ValueError(f"有序 Logistic 回归需要提供覆盖全部水平的顺序；当前水平: {observed_levels}")
    link = str(_param(parameters, "link", "logit"))
    distribution = _ordered_link_distribution(link)
    maxiter = int(_param(parameters, "max_iterations", 200))
    ordered = pd.Categorical(clean[outcome].astype(str), categories=level_order, ordered=True)
    exog_parts = []
    if fixed_factors:
        exog_parts.append(pd.get_dummies(clean[fixed_factors].astype("category"), drop_first=True, dtype=float))
    if covariates:
        exog_parts.append(clean[covariates].astype(float))
    if not exog_parts:
        raise ValueError("有序 Logistic 回归至少需要一个预测变量")
    exog = pd.concat(exog_parts, axis=1)
    if exog.shape[1] == 0:
        raise ValueError("分类预测变量哑编码后没有可用列")
    with pywarnings.catch_warnings(record=True) as caught:
        pywarnings.simplefilter("always")
        model = OrderedModel(ordered.codes, exog, distr=distribution)
        fit = model.fit(method="bfgs", maxiter=maxiter, disp=False)
    ci = fit.conf_int(alpha=alpha)
    coefficients: list[CoefficientResult] = []
    for term in exog.columns:
        estimate = float(fit.params[term])
        coefficients.append(CoefficientResult(
            term=str(term), estimate=estimate, se=float(fit.bse[term]), statistic_name="z",
            statistic_value=float(fit.tvalues[term]), p_value=float(fit.pvalues[term]),
            ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]),
            transformed_name="proportional odds ratio", transformed_value=float(math.exp(estimate)),
            significant=significance(float(fit.pvalues[term]), alpha),
        ))
    null_model = OrderedModel(ordered.codes, None, distr=distribution).fit(method="bfgs", maxiter=maxiter, disp=False)
    lr = max(0.0, 2 * (float(fit.llf) - float(null_model.llf)))
    lr_df = max(1, exog.shape[1])
    lr_p = float(stats.chi2.sf(lr, lr_df))
    pseudo_r2 = 1 - float(fit.llf) / float(null_model.llf) if null_model.llf else 0.0
    return StatisticalResult(
        analysis_id=f"ordinal_logit_{outcome}",
        design=design_info(clean, dependent=[outcome], fixed=fixed_factors, covariates=covariates),
        method=MethodInfo(name="ordinal_logistic_regression", label_zh="有序 Logistic/Probit 回归", formula=f"ordered({outcome}) ~ predictors", report_constraints=["比例优势假设需要结合专业诊断复核。"]),
        primary_tests=[PrimaryTestResult(
            effect="整体有序回归模型", statistic_name="likelihood-ratio chi-square", statistic_value=lr,
            p_value=lr_p, df_num=float(lr_df), effect_size_name="McFadden pseudo R-squared", effect_size_value=pseudo_r2,
            is_significant=significance(lr_p, alpha), significance_level=alpha,
        )],
        coefficients=coefficients,
        fit_statistics=[FitStatistic(name="AIC", value=float(fit.aic)), FitStatistic(name="BIC", value=float(fit.bic)), FitStatistic(name="Pseudo R-squared", value=pseudo_r2)],
        warnings=[str(item.message) for item in caught] + ([] if fit.mle_retvals.get("converged", False) else ["有序回归模型未收敛。"]),
        data_snapshot={"level_order": level_order, "link": link, "n": int(fit.nobs)},
        report_constraints=["有序回归将所给水平顺序视为真实顺序；顺序错误会改变结论。"],
    )
