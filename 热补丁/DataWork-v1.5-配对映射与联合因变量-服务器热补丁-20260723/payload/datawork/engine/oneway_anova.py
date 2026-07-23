"""单因素 ANOVA 引擎。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.oneway import anova_oneway as sm_anova_oneway

from .result import (
    StatisticalResult, DesignInfo, MethodInfo, OmnibusTest,
    EffectSize, DiagnosticResult, DiagnosticPlot, ContrastResult, EMMeans, VariableInfo, VariableRole,
)
from .assumptions import test_normality_groups, test_homogeneity
from .effect_size import partial_eta_squared, omega_squared
from .posthoc import pairwise_all, pairwise_dunnett_raw, normalize_posthoc_methods
from .letters import cld_from_posthoc_results
from .common import safe_standardized_statistic


def oneway_anova(
    df: pd.DataFrame,
    dv_col: str,
    factor_col: str,
    welch: bool = False,
    posthoc_methods: str | list[str] | tuple[str, ...] = "auto",
    alpha: float = 0.05,
    *,
    posthoc_method: str | None = None,
    estimate_emm: bool = False,
    diagnostic_plots: bool = True,
    control_group: str | None = None,
    random_seed: int = 2026,
) -> StatisticalResult:
    """单因素 ANOVA 或真正的 Welch ANOVA。"""
    df_clean = df[[dv_col, factor_col]].copy()
    df_clean[dv_col] = pd.to_numeric(df_clean[dv_col], errors="coerce")
    df_clean = df_clean.dropna()
    groups = df_clean.groupby(factor_col, observed=True)
    group_data = {name: gdf[dv_col].to_numpy(dtype=float) for name, gdf in groups}
    group_names = list(group_data)
    if len(group_names) < 2:
        raise ValueError("单因素 ANOVA 至少需要 2 个组")
    too_small = {str(name): len(values) for name, values in group_data.items() if len(values) < 2}
    if too_small:
        raise ValueError(f"每组至少需要 2 个有效观测，样本不足: {too_small}")

    k = len(group_names)
    n_total = sum(len(group_data[g]) for g in group_names)
    grand_mean = float(df_clean[dv_col].mean())
    desc = [
        {
            "group": str(name),
            "n": len(group_data[name]),
            "mean": round(float(np.mean(group_data[name])), 4),
            "sd": round(float(np.std(group_data[name], ddof=1)), 4),
        }
        for name in group_names
    ]

    ss_between = float(sum(
        len(group_data[g]) * (np.mean(group_data[g]) - grand_mean) ** 2
        for g in group_names
    ))
    ss_within = float(sum(
        np.sum((group_data[g] - np.mean(group_data[g])) ** 2)
        for g in group_names
    ))
    ss_total = ss_between + ss_within
    classical_df_num = k - 1
    classical_df_den = n_total - k
    ms_within = ss_within / classical_df_den if classical_df_den > 0 else np.nan

    if welch:
        welch_result = sm_anova_oneway(
            tuple(group_data[g] for g in group_names),
            use_var="unequal",
            welch_correction=True,
        )
        f_val = float(welch_result.statistic)
        p_val = float(welch_result.pvalue)
        df_num = float(welch_result.df_num)
        df_den = float(welch_result.df_denom)
        method_name = "Welch 单因素方差分析"
        method_key = "welch_anova"
    else:
        ms_between = ss_between / classical_df_num
        f_val = float(ms_between / ms_within) if ms_within > 0 else np.inf
        p_val = float(stats.f.sf(f_val, classical_df_num, classical_df_den))
        df_num = float(classical_df_num)
        df_den = float(classical_df_den)
        method_name = "单因素方差分析"
        method_key = "oneway_anova"

    eta_p = partial_eta_squared(ss_between, ss_within)
    omega = omega_squared(
        ss_between, ss_within, ss_total,
        classical_df_num, classical_df_den, n_total,
    )

    omnibus = [OmnibusTest(
        effect=factor_col,
        ss_type=3,
        df_num=df_num,
        df_den=df_den,
        f_value=float(f_val),
        p_value=float(p_val),
        eta_sq=round(ss_between / ss_total, 4) if ss_total > 0 else 0,
        eta_sq_p=eta_p["value"],
        omega_sq=omega["value"] if not welch else 0.0,
        is_significant=bool(p_val < alpha),
        significance_level=alpha,
    )]

    diagnostics: list[DiagnosticResult] = []
    for item in test_normality_groups(df_clean, dv_col, [factor_col], alpha):
        diagnostics.append(DiagnosticResult(
            test_name=f"{item['test']} ({item['group']})",
            statistic=float(item["statistic"]),
            p_value=float(item["p_value"]),
            passed=bool(item["passed"]),
            detail=item["detail"],
        ))
    lev = test_homogeneity(df_clean, dv_col, factor_col, alpha=alpha)
    diagnostics.append(DiagnosticResult(
        test_name="Levene",
        statistic=float(lev.statistic),
        p_value=float(lev.p_value),
        passed=lev.passed,
        detail=lev.detail,
    ))

    contrasts: list[ContrastResult] = []
    significance_letters = []
    if posthoc_method is not None:
        posthoc_methods = posthoc_method
    selected_posthocs = normalize_posthoc_methods(posthoc_methods, default="auto")
    resolved_posthocs: list[str] = []
    if p_val < alpha and k >= 2 and selected_posthocs != ["none"]:
        if welch:
            invalid = [item for item in selected_posthocs if item not in {"auto", "games_howell", "none"}]
            if invalid:
                raise ValueError("Welch ANOVA 的事后比较仅支持 auto/games_howell/none；方差不齐时不应改用普通 Tukey 或 Duncan。")
            resolved_posthocs = ["games_howell"] if selected_posthocs != ["none"] else []
        else:
            for item in selected_posthocs:
                if item == "none":
                    continue
                resolved = ("tukey" if lev.passed else "games_howell") if item == "auto" else item
                if resolved not in resolved_posthocs:
                    resolved_posthocs.append(resolved)

        string_group_data = {str(g): np.asarray(group_data[g], dtype=float) for g in group_names}
        group_means = {name: float(np.mean(values)) for name, values in string_group_data.items()}
        group_n = {name: len(values) for name, values in string_group_data.items()}
        control_group = str(control_group).strip() if control_group is not None else ""
        for selected_posthoc in resolved_posthocs:
            if selected_posthoc == "games_howell":
                method_contrasts = _games_howell(group_data, alpha)
                contrasts.extend(method_contrasts)
                # Games–Howell 覆盖完整组对，可生成 CLD。
                from types import SimpleNamespace
                pseudo = []
                for item, (left, right) in zip(method_contrasts, __import__('itertools').combinations([str(name) for name in group_names], 2)):
                    pseudo.append(SimpleNamespace(group1=left, group2=right, significant=item.significant))
                significance_letters.extend(cld_from_posthoc_results(
                    group_means, pseudo, factor=factor_col, method="Games–Howell", outcome=dv_col,
                ))
                continue
            if selected_posthoc == "dunnett":
                comparisons = pairwise_dunnett_raw(
                    string_group_data, control_group, alpha, random_seed=random_seed
                )
            else:
                comparisons = pairwise_all(
                    group_means, group_n, ms_within, classical_df_den,
                    method=selected_posthoc, alpha=alpha, control_group=control_group or None,
                )
            for comparison in comparisons:
                contrasts.append(ContrastResult(
                    contrast=comparison.contrast,
                    estimate=round(comparison.diff, 4),
                    se=round(comparison.se, 4),
                    t_value=round(comparison.t_value, 4),
                    p_value=float(comparison.p_raw),
                    p_adjusted=float(comparison.p_adjusted),
                    ci_lower=round(comparison.ci_lower, 4),
                    ci_upper=round(comparison.ci_upper, 4),
                    df=comparison.df,
                    significant=comparison.significant,
                    correction=comparison.correction,
                ))
            generated = cld_from_posthoc_results(
                group_means, comparisons, factor=factor_col,
                method=comparisons[0].correction if comparisons else selected_posthoc,
                outcome=dv_col,
            )
            significance_letters.extend(generated)

    effect_sizes = [
        EffectSize(
            measure="η²", value=round(ss_between / ss_total, 4) if ss_total > 0 else 0,
            interpretation=eta_p["interpretation"],
        ),
        EffectSize(
            measure="η²p", value=eta_p["value"],
            interpretation=eta_p["interpretation"],
        ),
    ]
    if not welch:
        effect_sizes.append(EffectSize(
            measure="ω²", value=omega["value"], interpretation=omega["interpretation"]
        ))

    warnings: list[str] = []
    if not welch and not lev.passed:
        warnings.append(
            f"Levene 检验显著 (p={lev.p_value:.4f})，建议使用 Welch ANOVA。"
        )
    if welch:
        warnings.append("Welch ANOVA 的事后比较使用 Games–Howell；ω² 未报告。")
    if "duncan" in set(selected_posthocs) | set(resolved_posthocs):
        warnings.append("Duncan 多重极差检验较宽松，家族第一类错误率控制弱于 Tukey/Holm；建议仅作为探索性或行业兼容结果。")
    if "lsd" in set(selected_posthocs) | set(resolved_posthocs):
        warnings.append("Fisher protected LSD 在总体检验显著后仍不校正全部两两比较；组数较多时第一类错误率会膨胀。")
    if "games_howell" in resolved_posthocs and not welch:
        warnings.append("根据方差齐性诊断，本次事后比较包含 Games–Howell。")
    if "dunnett" in resolved_posthocs:
        warnings.append("Dunnett 仅比较处理组与对照组，比较矩阵不完整，因此不生成完整显著性字母分组。")

    design = DesignInfo(
        variables=[
            VariableInfo(name=dv_col, dtype="float64", role=VariableRole.DEPENDENT),
            VariableInfo(
                name=factor_col, dtype=str(df_clean[factor_col].dtype),
                role=VariableRole.BETWEEN,
                levels=[str(g) for g in group_names], n_unique=k,
            ),
        ],
        n_subjects=n_total,
        n_observations=n_total,
        between_factors=[factor_col],
        dependent_vars=[dv_col],
    )

    emmeans: list[EMMeans] = []
    if estimate_emm:
        for name in group_names:
            values = group_data[name]
            mean = float(np.mean(values))
            if welch:
                se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
                df_emm = float(len(values) - 1)
                source = "group mean（Welch：组内标准误）"
            else:
                se = float(np.sqrt(ms_within / len(values)))
                df_emm = float(classical_df_den)
                source = "group mean（ANOVA 合并误差均方）"
            critical = float(stats.t.ppf(1 - alpha / 2, df_emm))
            emmeans.append(EMMeans(
                group=f"{factor_col}={name}", levels={factor_col: str(name)}, mean=mean, se=se,
                ci_lower=mean-critical*se, ci_upper=mean+critical*se, df=df_emm,
                source=source,
            ))
    plots: list[DiagnosticPlot] = []
    if diagnostic_plots:
        fitted = df_clean[factor_col].map({name: float(np.mean(values)) for name, values in group_data.items()}).to_numpy(dtype=float)
        residuals = df_clean[dv_col].to_numpy(dtype=float) - fitted
        from .model_support import regression_diagnostic_plots
        plots = regression_diagnostic_plots(fitted, residuals)
        plots.append(DiagnosticPlot(
            kind="point", title=f"组均值与标准误：{factor_col}", x_label=factor_col, y_label=f"{dv_col} 均值",
            series=[{
                "name": dv_col,
                "x": [str(name) for name in group_names],
                "y": [float(np.mean(group_data[name])) for name in group_names],
                "error": [float(np.std(group_data[name], ddof=1)/np.sqrt(len(group_data[name]))) for name in group_names],
            }],
        ))

    return StatisticalResult(
        analysis_id=f"oneway_{factor_col}",
        design=design,
        method=MethodInfo(
            name=method_key,
            label_zh=method_name,
            formula=f"{dv_col} ~ {factor_col}",
            assumptions=["观测独立", "各组近似正态"] + ([] if welch else ["方差齐性"]),
        ),
        diagnostics=diagnostics,
        omnibus_tests=omnibus,
        contrasts=contrasts,
        significance_letters=significance_letters,
        estimated_marginal_means=emmeans,
        effect_sizes=effect_sizes, diagnostic_plots=plots,
        warnings=warnings,
        descriptive_stats=desc,
        data_snapshot={"n_total": n_total, "k": k, "posthoc_methods": resolved_posthocs, "control_group": control_group or ""},
    )


def _games_howell(group_data: dict[object, np.ndarray], alpha: float) -> list[ContrastResult]:
    """Games–Howell 两两比较，适用于方差与样本量不等。"""
    names = list(group_data)
    k = len(names)
    results: list[ContrastResult] = []
    for i in range(k):
        for j in range(i + 1, k):
            left_name, right_name = names[i], names[j]
            left, right = group_data[left_name], group_data[right_name]
            n1, n2 = len(left), len(right)
            m1, m2 = float(np.mean(left)), float(np.mean(right))
            v1, v2 = float(np.var(left, ddof=1)), float(np.var(right, ddof=1))
            term1, term2 = v1 / n1, v2 / n2
            se = np.sqrt(term1 + term2)
            denominator = term1**2 / (n1 - 1) + term2**2 / (n2 - 1)
            df = (term1 + term2) ** 2 / denominator if denominator > 0 else np.inf
            diff = m1 - m2
            t_value = safe_standardized_statistic(diff, se)
            q_value = abs(t_value) * np.sqrt(2)
            p_value = float(stats.studentized_range.sf(q_value, k, df))
            q_crit = float(stats.studentized_range.ppf(1 - alpha, k, df))
            half_width = q_crit * se / np.sqrt(2)
            results.append(ContrastResult(
                contrast=f"{left_name} - {right_name}",
                estimate=round(diff, 4),
                se=round(se, 4),
                t_value=round(t_value, 4),
                p_value=float(p_value),
                p_adjusted=float(p_value),
                ci_lower=round(diff - half_width, 4),
                ci_upper=round(diff + half_width, 4),
                df=round(float(df), 4),
                significant=bool(p_value < alpha),
                correction="games-howell",
            ))
    return results
