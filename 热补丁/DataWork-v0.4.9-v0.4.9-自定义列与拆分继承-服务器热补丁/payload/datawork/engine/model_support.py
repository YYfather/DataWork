"""第三阶段模型后处理：球形性、模型边际均值、对比与结构化诊断图。"""
from __future__ import annotations

from itertools import combinations, product
from typing import Any, Iterable

import numpy as np
import pandas as pd
from patsy import build_design_matrices
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .result import (
    AdjustedTestResult,
    ContrastResult,
    DiagnosticPlot,
    EMMeans,
    SignificanceLetterGroup,
    SphericityResult,
)
from .letters import cld_from_emm_contrasts
from .posthoc import normalize_posthoc_methods
from .common import safe_standardized_statistic


def sphericity_result(wide: pd.DataFrame, alpha: float = 0.05) -> SphericityResult | None:
    """对完整宽表执行 Mauchly 检验并计算 GG/HF epsilon。

    两个重复水平时球形性恒成立，因此返回 None。
    """
    matrix = wide.to_numpy(dtype=float)
    n_subjects, n_levels = matrix.shape
    if n_levels <= 2 or n_subjects < 3:
        return None
    covariance = np.cov(matrix, rowvar=False, ddof=1)
    centering = np.eye(n_levels) - np.ones((n_levels, n_levels)) / n_levels
    centered_cov = centering @ covariance @ centering
    eigenvalues = np.linalg.eigvalsh(centered_cov)
    eigenvalues = eigenvalues[eigenvalues > max(1e-12, np.max(np.abs(eigenvalues)) * 1e-10)]
    rank = n_levels - 1
    if len(eigenvalues) < rank:
        eigenvalues = np.pad(eigenvalues, (0, rank - len(eigenvalues)), constant_values=1e-12)
    eigenvalues = eigenvalues[-rank:]
    mean_eigen = float(np.mean(eigenvalues))
    if mean_eigen <= 0:
        return None
    w = float(np.prod(eigenvalues) / (mean_eigen ** rank))
    w = float(np.clip(w, 1e-15, 1.0))
    correction = n_subjects - 1 - (2 * n_levels**2 - n_levels + 2) / (6 * (n_levels - 1))
    chi_square = float(max(0.0, -correction * np.log(w)))
    df = float(n_levels * (n_levels - 1) / 2 - 1)
    p_value = float(stats.chi2.sf(chi_square, df)) if df > 0 else 1.0
    epsilon_gg = float((np.sum(eigenvalues) ** 2) / ((n_levels - 1) * np.sum(eigenvalues**2)))
    epsilon_gg = float(np.clip(epsilon_gg, 1 / (n_levels - 1), 1.0))
    denominator = (n_levels - 1) * (n_subjects - 1 - (n_levels - 1) * epsilon_gg)
    if denominator <= 0:
        epsilon_hf = 1.0
    else:
        epsilon_hf = float((n_subjects * (n_levels - 1) * epsilon_gg - 2) / denominator)
    epsilon_hf = float(np.clip(epsilon_hf, epsilon_gg, 1.0))
    passed = bool(p_value >= alpha)
    detail = (
        "球形性未见显著违背。" if passed else
        "球形性可能不满足，应优先报告 Greenhouse–Geisser 或 Huynh–Feldt 校正结果。"
    )
    return SphericityResult(
        statistic=w,
        chi_square=chi_square,
        df=df,
        p_value=p_value,
        epsilon_gg=epsilon_gg,
        epsilon_hf=epsilon_hf,
        passed=passed,
        detail=detail,
    )


def sphericity_adjustments(
    f_value: float,
    df_num: float,
    df_den: float,
    sphericity: SphericityResult | None,
    alpha: float,
) -> list[AdjustedTestResult]:
    if sphericity is None or df_num <= 1:
        return []
    results: list[AdjustedTestResult] = []
    for label, epsilon in (
        ("Greenhouse–Geisser", sphericity.epsilon_gg),
        ("Huynh–Feldt", sphericity.epsilon_hf),
    ):
        adjusted_num = float(df_num * epsilon)
        adjusted_den = float(df_den * epsilon)
        p_value = float(stats.f.sf(f_value, adjusted_num, adjusted_den))
        results.append(AdjustedTestResult(
            correction=label,
            df_num=adjusted_num,
            df_den=adjusted_den,
            p_value=p_value,
            is_significant=bool(p_value < alpha),
        ))
    return results


def regression_diagnostic_plots(
    fitted: Iterable[float],
    residuals: Iterable[float],
    *,
    leverage: Iterable[float] | None = None,
    cooks_distance: Iterable[float] | None = None,
) -> list[DiagnosticPlot]:
    fitted_array = np.asarray(list(fitted), dtype=float)
    residual_array = np.asarray(list(residuals), dtype=float)
    valid = np.isfinite(fitted_array) & np.isfinite(residual_array)
    fitted_array = fitted_array[valid]
    residual_array = residual_array[valid]
    if len(residual_array) < 3:
        return []
    standardized = residual_array / (np.std(residual_array, ddof=1) or 1.0)
    theoretical, ordered = stats.probplot(standardized, dist="norm", fit=False)
    slope, intercept, _ = stats.probplot(standardized, dist="norm", fit=True)[1]
    plots = [
        DiagnosticPlot(
            kind="scatter",
            title="残差－拟合值图",
            x_label="拟合值",
            y_label="残差",
            series=[{"name": "观测", "x": fitted_array.tolist(), "y": residual_array.tolist()}],
            reference_lines=[{"axis": "y", "value": 0.0, "label": "零残差"}],
            notes=["用于检查非线性结构、异方差和异常残差。"],
        ),
        DiagnosticPlot(
            kind="qq",
            title="残差正态 Q–Q 图",
            x_label="理论分位数",
            y_label="标准化残差分位数",
            series=[{"name": "Q–Q", "x": np.asarray(theoretical).tolist(), "y": np.asarray(ordered).tolist()}],
            reference_lines=[{"axis": "xy", "slope": float(slope), "intercept": float(intercept), "label": "正态参考线"}],
            notes=["点明显偏离参考线时，正态近似可能不足。"],
        ),
        DiagnosticPlot(
            kind="scatter",
            title="尺度－位置图",
            x_label="拟合值",
            y_label="√|标准化残差|",
            series=[{"name": "尺度", "x": fitted_array.tolist(), "y": np.sqrt(np.abs(standardized)).tolist()}],
            notes=["纵向散布随拟合值系统变化时，可能存在异方差。"],
        ),
    ]
    if leverage is not None and cooks_distance is not None:
        leverage_array = np.asarray(list(leverage), dtype=float)[valid]
        cooks_array = np.asarray(list(cooks_distance), dtype=float)[valid]
        plots.append(DiagnosticPlot(
            kind="scatter",
            title="影响点诊断",
            x_label="杠杆值",
            y_label="Cook 距离",
            series=[{"name": "观测", "x": leverage_array.tolist(), "y": cooks_array.tolist()}],
            reference_lines=[{"axis": "y", "value": float(4 / max(len(cooks_array), 1)), "label": "4/n 参考阈值"}],
            notes=["高杠杆且 Cook 距离较大的观测应结合原始记录复核。"],
        ))
    return plots


def interaction_plot(frame: pd.DataFrame, dv: str, factor_a: str, factor_b: str) -> DiagnosticPlot:
    grouped = frame.groupby([factor_a, factor_b], observed=True)[dv].agg(["mean", "count", "std"]).reset_index()
    series: list[dict[str, Any]] = []
    for level_a, subset in grouped.groupby(factor_a, observed=True):
        series.append({
            "name": str(level_a),
            "x": [str(value) for value in subset[factor_b].tolist()],
            "y": [float(value) for value in subset["mean"].tolist()],
            "error": [float(value / np.sqrt(max(count, 1))) if np.isfinite(value) else 0.0 for value, count in zip(subset["std"], subset["count"])],
        })
    return DiagnosticPlot(
        kind="line",
        title=f"交互作用图：{factor_a} × {factor_b}",
        x_label=factor_b,
        y_label=f"{dv} 均值",
        series=series,
        notes=["线条明显不平行提示可能存在交互作用；正式结论以模型检验为准。"],
    )


def estimated_marginal_means(
    model: Any,
    data: pd.DataFrame,
    *,
    target_factors: list[str],
    categorical_factors: list[str],
    covariates: list[str],
    alpha: float = 0.05,
    correction: str = "holm",
    fixed_params: pd.Series | np.ndarray | None = None,
    fixed_cov: pd.DataFrame | np.ndarray | None = None,
    df_resid: float | None = None,
    normal_approximation: bool = False,
) -> tuple[list[EMMeans], list[ContrastResult]]:
    """基于模型设计矩阵计算等权参考网格 EMM 与两两对比。"""
    target_factors = list(dict.fromkeys(target_factors))
    if not target_factors:
        return [], []
    missing = [name for name in target_factors if name not in categorical_factors]
    if missing:
        raise ValueError(f"EMM 因素必须来自模型分类因素: {missing}")
    design_info = getattr(getattr(model, "model", model), "data", None)
    design_info = getattr(design_info, "design_info", None)
    if design_info is None:
        raise ValueError("当前模型不包含可复用的设计矩阵信息，无法计算 EMM")
    params = np.asarray(fixed_params if fixed_params is not None else model.params, dtype=float)
    covariance = np.asarray(fixed_cov if fixed_cov is not None else model.cov_params(), dtype=float)
    if covariance.shape[0] != len(params):
        covariance = covariance[:len(params), :len(params)]

    levels = {factor: list(pd.unique(data[factor].dropna())) for factor in categorical_factors}
    target_level_sets = [levels[factor] for factor in target_factors]
    nuisance = [factor for factor in categorical_factors if factor not in target_factors]
    nuisance_sets = [levels[factor] for factor in nuisance]
    covariate_means = {name: float(pd.to_numeric(data[name], errors="coerce").mean()) for name in covariates}
    entries: list[tuple[EMMeans, np.ndarray]] = []
    critical = float(stats.norm.ppf(1 - alpha / 2)) if normal_approximation else float(stats.t.ppf(1 - alpha / 2, df_resid or max(len(data) - len(params), 1)))

    for target_values in product(*target_level_sets):
        target_map = dict(zip(target_factors, target_values))
        nuisance_products = list(product(*nuisance_sets)) if nuisance_sets else [()]
        rows = []
        for nuisance_values in nuisance_products:
            row = {**target_map, **dict(zip(nuisance, nuisance_values)), **covariate_means}
            rows.append(row)
        grid = pd.DataFrame(rows)
        matrix = np.asarray(build_design_matrices([design_info], grid, return_type="dataframe")[0], dtype=float)
        xbar = matrix.mean(axis=0)
        mean = float(xbar @ params)
        variance = float(xbar @ covariance @ xbar)
        se = float(np.sqrt(max(variance, 0.0)))
        level_strings = {key: str(value) for key, value in target_map.items()}
        label = ", ".join(f"{key}={value}" for key, value in level_strings.items())
        entries.append((EMMeans(
            group=label,
            mean=mean,
            se=se,
            ci_lower=mean - critical * se,
            ci_upper=mean + critical * se,
            levels=level_strings,
            df=None if normal_approximation else float(df_resid or max(len(data) - len(params), 1)),
            source="model reference grid",
        ), xbar))

    contrasts: list[ContrastResult] = []
    raw_p: list[float] = []
    pairs: list[tuple[int, int, float, float, float, float, float]] = []
    use_df = float(df_resid or max(len(data) - len(params), 1))
    for left, right in combinations(range(len(entries)), 2):
        left_emm, left_x = entries[left]
        right_emm, right_x = entries[right]
        vector = left_x - right_x
        estimate = float(vector @ params)
        se = float(np.sqrt(max(float(vector @ covariance @ vector), 0.0)))
        statistic = safe_standardized_statistic(estimate, se)
        if normal_approximation:
            p_value = float(2 * stats.norm.sf(abs(statistic)))
            contrast_critical = float(stats.norm.ppf(1 - alpha / 2))
        else:
            p_value = float(2 * stats.t.sf(abs(statistic), use_df))
            contrast_critical = float(stats.t.ppf(1 - alpha / 2, use_df))
        raw_p.append(p_value)
        pairs.append((left, right, estimate, se, statistic, estimate - contrast_critical * se, estimate + contrast_critical * se))
    adjusted = np.asarray(raw_p, dtype=float)
    if len(raw_p) and correction != "none":
        adjusted = multipletests(adjusted, alpha=alpha, method=correction)[1]
    for index, (left, right, estimate, se, statistic, ci_low, ci_high) in enumerate(pairs):
        contrasts.append(ContrastResult(
            contrast=f"{entries[left][0].group} - {entries[right][0].group}",
            estimate=estimate,
            se=se,
            t_value=statistic,
            statistic_name="z" if normal_approximation else "t",
            p_value=raw_p[index],
            p_adjusted=float(adjusted[index]),
            ci_lower=ci_low,
            ci_upper=ci_high,
            df=0.0 if normal_approximation else use_df,
            significant=bool(adjusted[index] < alpha),
            correction=correction,
        ))
    return [item[0] for item in entries], contrasts


def adjust_emm_pairwise_contrasts(
    emmeans: list[EMMeans],
    contrasts: list[ContrastResult],
    *,
    method: str,
    alpha: float = 0.05,
    control_group: str | None = None,
) -> list[ContrastResult]:
    """对模型 EMM 成对对比应用统一的多重比较规则。

    ``estimated_marginal_means`` 先生成未经多重校正的模型对比，本函数再根据
    Tukey、Scheffé、Duncan、Holm 等规则重算校正 p 值与同步区间。Dunnett
    在模型 EMM 场景下使用 Bonferroni 保守近似；原始单因素数据可使用 SciPy
    的精确单步 Dunnett 实现。
    """
    if not contrasts:
        return []
    normalized = method.strip().lower().replace("-", "_")
    aliases = {
        "hsd": "tukey", "tukey_hsd": "tukey", "tukey_kramer": "tukey",
        "fisher_lsd": "lsd", "protected_lsd": "lsd", "fdr": "fdr_bh",
        "benjamini_hochberg": "fdr_bh", "duncan_mrt": "duncan",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized == "none":
        return []

    pairs = list(combinations(range(len(emmeans)), 2))
    if len(pairs) != len(contrasts):
        raise ValueError("EMM 数量与成对对比数量不一致")
    df = float(next((item.df for item in contrasts if item.df and item.df > 0), 1.0))
    raw_p = np.asarray([float(item.p_value) for item in contrasts], dtype=float)
    estimates = np.asarray([float(item.estimate) for item in contrasts], dtype=float)
    ses = np.asarray([float(item.se) for item in contrasts], dtype=float)
    statistics = np.asarray([float(item.t_value) for item in contrasts], dtype=float)
    k = len(emmeans)
    m = len(contrasts)
    adjusted = raw_p.copy()
    critical = np.repeat(float(stats.t.ppf(1 - alpha / 2, df)), m)
    correction_label = normalized

    if normalized in {"holm", "bonferroni", "sidak", "fdr_bh"}:
        adjusted = multipletests(raw_p, alpha=alpha, method=normalized)[1]
        correction_label = {
            "holm": "Holm（CI 使用 Bonferroni 同步区间）",
            "bonferroni": "Bonferroni",
            "sidak": "Šidák",
            "fdr_bh": "Benjamini–Hochberg FDR（CI 未作同步校正）",
        }[normalized]
        if normalized in {"holm", "bonferroni"}:
            critical = np.repeat(float(stats.t.ppf(1 - alpha / (2 * m), df)), m)
        elif normalized == "sidak":
            per_alpha = 1 - (1 - alpha) ** (1 / m)
            critical = np.repeat(float(stats.t.ppf(1 - per_alpha / 2, df)), m)
    elif normalized == "tukey":
        q_values = np.abs(statistics) * np.sqrt(2)
        adjusted = np.asarray([float(stats.studentized_range.sf(value, k, df)) for value in q_values])
        q_critical = float(stats.studentized_range.ppf(1 - alpha, k, df))
        critical = np.repeat(q_critical / np.sqrt(2), m)
        correction_label = "Tukey HSD（模型 EMM）"
    elif normalized == "scheffe":
        adjusted = np.asarray([float(stats.f.sf(value**2 / (k - 1), k - 1, df)) for value in statistics])
        critical = np.repeat(float(np.sqrt((k - 1) * stats.f.ppf(1 - alpha, k - 1, df))), m)
        correction_label = "Scheffé（模型 EMM）"
    elif normalized == "duncan":
        order = sorted(range(k), key=lambda index: float(emmeans[index].mean))
        ranks = {index: rank for rank, index in enumerate(order)}
        values: list[float] = []
        multipliers: list[float] = []
        for contrast_index, (left, right) in enumerate(pairs):
            range_size = abs(ranks[left] - ranks[right]) + 1
            q_value = abs(statistics[contrast_index]) * np.sqrt(2)
            p_range = float(stats.studentized_range.sf(q_value, range_size, df))
            values.append(1 - (1 - p_range) ** (1 / max(range_size - 1, 1)))
            alpha_range = 1 - (1 - alpha) ** max(range_size - 1, 1)
            multipliers.append(float(stats.studentized_range.ppf(1 - alpha_range, range_size, df) / np.sqrt(2)))
        adjusted = np.asarray(values)
        critical = np.asarray(multipliers)
        correction_label = "Duncan 多重极差（模型 EMM，宽松）"
    elif normalized == "lsd":
        correction_label = "Fisher protected LSD（未校正，宽松）"
    elif normalized == "dunnett":
        if not control_group:
            raise ValueError("Dunnett 需要指定 control_group")
        selected: list[int] = []
        control_matches = [index for index, item in enumerate(emmeans) if item.group == control_group or control_group in item.levels.values()]
        if len(control_matches) != 1:
            raise ValueError(f"无法从 EMM 中唯一识别对照水平 {control_group!r}")
        control_index = control_matches[0]
        for index, (left, right) in enumerate(pairs):
            if control_index in {left, right}:
                selected.append(index)
        bonf_alpha = alpha / max(len(selected), 1)
        output: list[ContrastResult] = []
        for index in selected:
            item = contrasts[index].model_copy(deep=True)
            item.p_adjusted = float(min(item.p_value * len(selected), 1.0))
            multiplier = float(stats.t.ppf(1 - bonf_alpha / 2, df))
            item.ci_lower = float(item.estimate - multiplier * item.se)
            item.ci_upper = float(item.estimate + multiplier * item.se)
            item.significant = bool(item.p_adjusted < alpha)
            item.correction = "Dunnett（模型 EMM，Bonferroni 保守近似）"
            output.append(item)
        return output
    else:
        raise ValueError(
            f"未知 EMM 事后比较方法: {method}。支持 tukey, holm, bonferroni, sidak, "
            "fdr_bh, scheffe, duncan, lsd, dunnett, none"
        )

    output: list[ContrastResult] = []
    for index, item in enumerate(contrasts):
        updated = item.model_copy(deep=True)
        updated.p_adjusted = float(np.clip(adjusted[index], 0.0, 1.0))
        updated.ci_lower = float(estimates[index] - critical[index] * ses[index])
        updated.ci_upper = float(estimates[index] + critical[index] * ses[index])
        updated.significant = bool(updated.p_adjusted < alpha)
        updated.correction = correction_label
        output.append(updated)
    return output


def resolve_control_group(control_spec: str | None, factor: str) -> str | None:
    """解析按因素指定的 Dunnett 对照水平。

    支持两种写法：

    * ``CK``：对所有因素使用同一个候选对照水平；
    * ``处理=CK; 品种=对照品种``：为不同因素分别指定水平。

    当输入包含映射但没有当前因素时返回 ``None``，由调用方给出明确的缺失
    对照提示，避免把另一个因素的水平误当作当前因素的对照。
    """
    raw = str(control_spec or "").strip()
    if not raw:
        return None
    normalized = raw.replace("；", ";").replace("，", ",").replace("\n", ";")
    parts = [item.strip() for chunk in normalized.split(";") for item in chunk.split(",") if item.strip()]
    mappings: dict[str, str] = {}
    for item in parts:
        separator = "=" if "=" in item else (":" if ":" in item else ("：" if "：" in item else ""))
        if not separator:
            continue
        key, value = (piece.strip() for piece in item.split(separator, 1))
        if key and value:
            mappings[key] = value
    if mappings:
        return mappings.get(factor)
    return raw


def apply_posthoc_methods_to_emm(
    emmeans: list[EMMeans],
    raw_contrasts: list[ContrastResult],
    *,
    methods: str | list[str] | tuple[str, ...],
    alpha: float,
    factor: str,
    outcome: str = "",
    context: str = "",
    control_group: str | None = None,
    contrast_prefix: str = "",
) -> tuple[list[ContrastResult], list[SignificanceLetterGroup], list[str]]:
    """对同一套模型 EMM 同时应用一种或多种事后检验。"""
    outputs: list[ContrastResult] = []
    letters: list[SignificanceLetterGroup] = []
    warnings: list[str] = []
    selected = normalize_posthoc_methods(methods, default="tukey")
    for method in selected:
        if method == "none":
            continue
        adjusted = adjust_emm_pairwise_contrasts(
            emmeans, raw_contrasts, method=method, alpha=alpha, control_group=control_group
        )
        method_label = adjusted[0].correction if adjusted else method
        for item in adjusted:
            updated = item.model_copy(deep=True)
            if contrast_prefix:
                updated.contrast = f"{contrast_prefix}{updated.contrast}"
            outputs.append(updated)
        generated = cld_from_emm_contrasts(
            emmeans, adjusted, factor=factor, method=method_label, outcome=outcome, context=context
        )
        letters.extend(generated)
        if method == "dunnett" and adjusted:
            warnings.append(
                f"{context or factor} 的 Dunnett 仅覆盖对照比较，未生成完整显著性字母分组；"
                "字母分组需要全部组对的比较关系。"
            )
    return outputs, letters, warnings
