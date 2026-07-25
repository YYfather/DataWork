"""事后多重比较方法。

实现原则：
- 默认优先控制家族错误率（Tukey/Holm/Bonferroni/Sidak/Scheffé）；
- Duncan 与 Fisher LSD 作为农业研究中的兼容选项保留，但明确标注为宽松方法；
- Dunnett 在原始样本可用时调用 SciPy 的单步精确实现，否则仅提供保守近似。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .common import safe_standardized_statistic


@dataclass
class PostHocResult:
    """一次成对比较。"""

    contrast: str
    group1: str
    group2: str
    mean1: float
    mean2: float
    diff: float
    se: float
    t_value: float
    df: float
    p_raw: float
    p_adjusted: float
    ci_lower: float
    ci_upper: float
    significant: bool
    correction: str


def _validate_summary_inputs(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
) -> None:
    if len(group_means) < 2:
        raise ValueError("事后比较至少需要两个组")
    if set(group_means) != set(group_n):
        raise ValueError("group_means 与 group_n 的组名不一致")
    if any(int(group_n[name]) < 1 for name in group_means):
        raise ValueError("每组样本量必须至少为 1")
    if not np.isfinite(mse) or mse < 0:
        raise ValueError("误差均方 mse 必须为非负有限数")
    if not np.isfinite(df_error) or df_error <= 0:
        raise ValueError("误差自由度必须大于 0")


def _pairwise_stats(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[dict[str, float | str]]:
    """为各种校正方法计算基础成对比较。"""
    del alpha
    _validate_summary_inputs(group_means, group_n, mse, df_error)
    group_names = list(group_means.keys())
    results: list[dict[str, float | str]] = []
    for g1, g2 in combinations(group_names, 2):
        n1, n2 = int(group_n[g1]), int(group_n[g2])
        mean1, mean2 = float(group_means[g1]), float(group_means[g2])
        diff = mean1 - mean2
        se = float(np.sqrt(mse * (1 / n1 + 1 / n2)))
        t_val = safe_standardized_statistic(diff, se)
        p_raw = float(2 * stats.t.sf(abs(t_val), df_error))
        results.append({
            "contrast": f"{g1} - {g2}",
            "group1": g1,
            "group2": g2,
            "mean1": mean1,
            "mean2": mean2,
            "diff": diff,
            "se": se,
            "t_value": float(t_val),
            "df": float(df_error),
            "p_raw": p_raw,
        })
    return results


def _build_results(
    raw: list[dict[str, float | str]],
    adjusted: np.ndarray,
    critical_values: list[float],
    alpha: float,
    correction: str,
) -> list[PostHocResult]:
    results: list[PostHocResult] = []
    for index, row in enumerate(raw):
        se = float(row["se"])
        half_width = float(critical_values[index] * se)
        p_adj = float(np.clip(adjusted[index], 0.0, 1.0))
        results.append(PostHocResult(
            **row,
            p_adjusted=p_adj,
            ci_lower=float(row["diff"]) - half_width,
            ci_upper=float(row["diff"]) + half_width,
            significant=bool(p_adj < alpha),
            correction=correction,
        ))
    return results


def _tukey_q_critical(k: int, df: float, alpha: float = 0.05) -> float:
    try:
        return float(stats.studentized_range.ppf(1 - alpha, k, df))
    except (AttributeError, ValueError):
        return float(stats.t.ppf(1 - alpha / (2 * k), df) * np.sqrt(2))


def pairwise_tukey(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    """Tukey–Kramer HSD，允许样本量不等。"""
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    k = len(group_means)
    q_crit = _tukey_q_critical(k, df_error, alpha)
    adjusted = np.asarray([
        float(stats.studentized_range.sf(abs(float(row["t_value"])) * np.sqrt(2), k, df_error))
        for row in raw
    ])
    critical = [q_crit / np.sqrt(2)] * len(raw)
    return _build_results(raw, adjusted, critical, alpha, "Tukey–Kramer HSD")


def pairwise_bonferroni(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    m = len(raw)
    adjusted = np.asarray([min(float(row["p_raw"]) * m, 1.0) for row in raw])
    critical = [float(stats.t.ppf(1 - alpha / (2 * m), df_error))] * m
    return _build_results(raw, adjusted, critical, alpha, "Bonferroni")


def pairwise_holm(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    p_raw = np.asarray([float(row["p_raw"]) for row in raw])
    adjusted = multipletests(p_raw, alpha=alpha, method="holm")[1]
    # Holm 同时置信区间没有单一闭式表达；使用 Bonferroni 区间作为保守同步区间。
    critical = [float(stats.t.ppf(1 - alpha / (2 * len(raw)), df_error))] * len(raw)
    return _build_results(raw, adjusted, critical, alpha, "Holm（CI 使用 Bonferroni 同步区间）")


def pairwise_sidak(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    m = len(raw)
    adjusted = np.asarray([1 - (1 - float(row["p_raw"])) ** m for row in raw])
    per_alpha = 1 - (1 - alpha) ** (1 / m)
    critical = [float(stats.t.ppf(1 - per_alpha / 2, df_error))] * m
    return _build_results(raw, adjusted, critical, alpha, "Šidák")


def pairwise_fdr_bh(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    p_raw = np.asarray([float(row["p_raw"]) for row in raw])
    adjusted = multipletests(p_raw, alpha=alpha, method="fdr_bh")[1]
    critical = [float(stats.t.ppf(1 - alpha / 2, df_error))] * len(raw)
    return _build_results(raw, adjusted, critical, alpha, "Benjamini–Hochberg FDR（CI 未作同步校正）")


def pairwise_lsd(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    """Fisher protected LSD；调用方应只在总体检验显著后执行。"""
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    adjusted = np.asarray([float(row["p_raw"]) for row in raw])
    critical = [float(stats.t.ppf(1 - alpha / 2, df_error))] * len(raw)
    return _build_results(raw, adjusted, critical, alpha, "Fisher protected LSD（未校正，宽松）")


def pairwise_scheffe(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    """Scheffé 同时推断，适用于任意线性对比，通常较保守。"""
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    k = len(group_means)
    adjusted = []
    for row in raw:
        f_pair = float(row["t_value"]) ** 2
        adjusted.append(float(stats.f.sf(f_pair / (k - 1), k - 1, df_error)))
    multiplier = float(np.sqrt((k - 1) * stats.f.ppf(1 - alpha, k - 1, df_error)))
    return _build_results(raw, np.asarray(adjusted), [multiplier] * len(raw), alpha, "Scheffé")


def pairwise_duncan(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    """Duncan 多重极差检验。

    采用均值排序后的步进极差数 ``r``。不等样本量时使用每一对实际标准误，
    属于常见推广形式；结果比 Tukey/Holm 更宽松，应作为探索性输出。
    """
    raw = _pairwise_stats(group_means, group_n, mse, df_error, alpha)
    ordered = sorted(group_means, key=lambda name: float(group_means[name]))
    ranks = {name: index for index, name in enumerate(ordered)}
    adjusted: list[float] = []
    critical: list[float] = []
    for row in raw:
        r = abs(ranks[str(row["group1"])] - ranks[str(row["group2"])]) + 1
        q_value = abs(float(row["t_value"])) * np.sqrt(2)
        p_range = float(stats.studentized_range.sf(q_value, r, df_error))
        # 将 Duncan 的分步显著性 alpha_r=1-(1-alpha)^(r-1) 映射回总体 alpha 尺度。
        p_duncan = 1 - (1 - p_range) ** (1 / max(r - 1, 1))
        alpha_r = 1 - (1 - alpha) ** max(r - 1, 1)
        q_crit = float(stats.studentized_range.ppf(1 - alpha_r, r, df_error))
        adjusted.append(p_duncan)
        critical.append(q_crit / np.sqrt(2))
    return _build_results(raw, np.asarray(adjusted), critical, alpha, "Duncan 多重极差（宽松）")


def pairwise_dunnett(
    group_means: dict[str, float],
    group_n: dict[str, int],
    control_group: str,
    mse: float,
    df_error: float,
    alpha: float = 0.05,
) -> list[PostHocResult]:
    """仅有汇总统计时的 Dunnett 保守近似（Bonferroni）。"""
    _validate_summary_inputs(group_means, group_n, mse, df_error)
    if control_group not in group_means:
        raise ValueError(f"对照组 {control_group!r} 不在分组中")
    groups = [name for name in group_means if name != control_group]
    m = len(groups)
    raw: list[dict[str, float | str]] = []
    for name in groups:
        diff = float(group_means[name] - group_means[control_group])
        se = float(np.sqrt(mse * (1 / group_n[name] + 1 / group_n[control_group])))
        t_value = safe_standardized_statistic(diff, se)
        p_raw = float(2 * stats.t.sf(abs(t_value), df_error))
        raw.append({
            "contrast": f"{name} - {control_group}", "group1": name, "group2": control_group,
            "mean1": float(group_means[name]), "mean2": float(group_means[control_group]),
            "diff": diff, "se": se, "t_value": t_value, "df": float(df_error), "p_raw": p_raw,
        })
    adjusted = np.asarray([min(float(row["p_raw"]) * m, 1.0) for row in raw])
    critical = [float(stats.t.ppf(1 - alpha / (2 * m), df_error))] * m
    return _build_results(raw, adjusted, critical, alpha, "Dunnett（Bonferroni 保守近似）")


def pairwise_dunnett_raw(
    group_data: dict[str, np.ndarray],
    control_group: str,
    alpha: float = 0.05,
    *,
    random_seed: int = 2026,
) -> list[PostHocResult]:
    """基于原始样本调用 SciPy Dunnett 单步检验。"""
    if control_group not in group_data:
        raise ValueError(f"对照组 {control_group!r} 不在分组中")
    names = [name for name in group_data if name != control_group]
    if not names:
        return []
    control = np.asarray(group_data[control_group], dtype=float)
    samples = [np.asarray(group_data[name], dtype=float) for name in names]
    if any(len(values) < 2 for values in [control, *samples]):
        raise ValueError("Dunnett 检验要求对照组和各处理组至少有 2 个有效观测")
    result = stats.dunnett(*samples, control=control, alternative="two-sided", rng=np.random.default_rng(random_seed))
    ci = result.confidence_interval(confidence_level=1 - alpha)
    pvalues = np.atleast_1d(np.asarray(result.pvalue, dtype=float))
    statistics = np.atleast_1d(np.asarray(result.statistic, dtype=float))
    lows = np.atleast_1d(np.asarray(ci.low, dtype=float))
    highs = np.atleast_1d(np.asarray(ci.high, dtype=float))
    df_error = float(sum(len(values) for values in [control, *samples]) - len(samples) - 1)
    pooled_ss = sum(float(np.sum((values - values.mean()) ** 2)) for values in [control, *samples])
    mse = pooled_ss / df_error
    outputs: list[PostHocResult] = []
    for index, name in enumerate(names):
        values = np.asarray(group_data[name], dtype=float)
        diff = float(values.mean() - control.mean())
        se = float(np.sqrt(mse * (1 / len(values) + 1 / len(control))))
        t_value = safe_standardized_statistic(diff, se)
        p_raw = float(2 * stats.t.sf(abs(t_value), df_error))
        outputs.append(PostHocResult(
            contrast=f"{name} - {control_group}", group1=name, group2=control_group,
            mean1=float(values.mean()), mean2=float(control.mean()), diff=diff, se=se,
            t_value=float(statistics[index]), df=df_error, p_raw=p_raw,
            p_adjusted=float(pvalues[index]), ci_lower=float(lows[index]), ci_upper=float(highs[index]),
            significant=bool(pvalues[index] < alpha), correction="Dunnett 单步检验（SciPy）",
        ))
    return outputs



def normalize_posthoc_methods(value: str | list[str] | tuple[str, ...] | None, default: str = "tukey") -> list[str]:
    """规范化单选/多选事后检验参数，并处理 auto/none 的互斥关系。"""
    if value is None:
        values = [default]
    elif isinstance(value, str):
        values = [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    else:
        values = [str(item).strip() for item in value if str(item).strip()]
    aliases = {
        "hsd": "tukey", "tukey_hsd": "tukey", "tukey_kramer": "tukey",
        "fisher_lsd": "lsd", "protected_lsd": "lsd", "fdr": "fdr_bh",
        "benjamini_hochberg": "fdr_bh", "duncan_mrt": "duncan",
    }
    values = [aliases.get(item.lower().replace("-", "_"), item.lower().replace("-", "_")) for item in values]
    values = list(dict.fromkeys(values))
    if "none" in values and len(values) > 1:
        values.remove("none")
    if "auto" in values and len(values) > 1:
        values.remove("auto")
    return values or [default]

def pairwise_all(
    group_means: dict[str, float],
    group_n: dict[str, int],
    mse: float,
    df_error: float,
    method: str = "tukey",
    alpha: float = 0.05,
    control_group: Optional[str] = None,
) -> list[PostHocResult]:
    """统一事后比较入口。"""
    normalized = method.strip().lower().replace("-", "_")
    aliases = {
        "hsd": "tukey", "tukey_hsd": "tukey", "tukey_kramer": "tukey",
        "fisher_lsd": "lsd", "protected_lsd": "lsd", "fdr": "fdr_bh",
        "benjamini_hochberg": "fdr_bh", "sidak": "sidak", "šidák": "sidak",
        "scheffe_test": "scheffe", "duncan_mrt": "duncan",
    }
    normalized = aliases.get(normalized, normalized)
    dispatch = {
        "tukey": pairwise_tukey,
        "bonferroni": pairwise_bonferroni,
        "holm": pairwise_holm,
        "sidak": pairwise_sidak,
        "fdr_bh": pairwise_fdr_bh,
        "lsd": pairwise_lsd,
        "scheffe": pairwise_scheffe,
        "duncan": pairwise_duncan,
    }
    if normalized == "none":
        return []
    if normalized == "dunnett":
        if not control_group:
            raise ValueError("Dunnett 需要指定 control_group")
        return pairwise_dunnett(group_means, group_n, control_group, mse, df_error, alpha)
    try:
        function = dispatch[normalized]
    except KeyError as exc:
        raise ValueError(
            "未知事后比较方法: " + method +
            "。支持: tukey, holm, bonferroni, sidak, fdr_bh, scheffe, duncan, lsd, dunnett, none"
        ) from exc
    return function(group_means, group_n, mse, df_error, alpha)
