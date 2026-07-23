"""双因素 ANOVA 引擎 — 支持交互、简单效应、事后比较。"""

from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from patsy.builtins import C as __dw_cat
from patsy.contrasts import Sum as __dw_sum
from statsmodels.formula.api import ols

from .result import (
    StatisticalResult, DesignInfo, MethodInfo, OmnibusTest,
    EffectSize, DiagnosticResult, ContrastResult,
    SimpleEffectResult, VariableInfo, VariableRole, EMMeans, SignificanceLetterGroup,
)
from .assumptions import test_normality_groups, test_homogeneity_two_factor
from .effect_size import partial_eta_squared, omega_squared
from .model_support import (
    apply_posthoc_methods_to_emm, estimated_marginal_means, interaction_plot,
    regression_diagnostic_plots, resolve_control_group,
)
from .factorial_followup import conditional_simple_effects


def twoway_anova(
    df: pd.DataFrame,
    dv_col: str,
    factor_a: str,
    factor_b: str,
    posthoc_methods: str | list[str] | tuple[str, ...] = "tukey",
    control_group: str | None = None,
    alpha: float = 0.05,
    ss_type: int = 3,
    *,
    posthoc_method: str | None = None,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
    simple_effect_correction: str = "holm",
) -> StatisticalResult:
    """
    双因素 ANOVA（between-subjects）。

    Args:
        df: 数据框
        dv_col: 因变量
        factor_a: 因素 A
        factor_b: 因素 B
        posthoc_methods: 可单选或多选的事后比较方法
        alpha: 显著性水平
        ss_type: 平方和类型 (1/2/3)，Type III 使用 Sum 对比编码
    """
    df_clean = df[[dv_col, factor_a, factor_b]].dropna().copy()

    # 确保因素是类别型
    for col in [factor_a, factor_b]:
        if not isinstance(df_clean[col].dtype, pd.CategoricalDtype):
            df_clean[col] = df_clean[col].astype("category")

    if posthoc_method is not None:
        posthoc_methods = posthoc_method
    if ss_type not in (1, 2, 3):
        raise ValueError("ss_type 必须为 1、2 或 3")

    # Type III 必须配合 Sum 对比编码，避免 treatment coding 下结果依赖参考水平。
    if ss_type == 3:
        formula = (
            f"Q('{dv_col}') ~ __dw_cat(Q('{factor_a}'), __dw_sum) "
            f"* __dw_cat(Q('{factor_b}'), __dw_sum)"
        )
    else:
        formula = f"Q('{dv_col}') ~ __dw_cat(Q('{factor_a}')) * __dw_cat(Q('{factor_b}'))"
    model = ols(formula, data=df_clean).fit()
    try:
        anova_table = sm.stats.anova_lm(model, typ=ss_type)
    except Exception as exc:
        raise RuntimeError(f"Type {ss_type} ANOVA 拟合失败；未切换为其他平方和类型: {exc}") from exc

    n_total = len(df_clean)
    grand_mean = df_clean[dv_col].mean()
    ss_residual = anova_table.loc["Residual", "sum_sq"] if "Residual" in anova_table.index else 0
    df_residual = anova_table.loc["Residual", "df"] if "Residual" in anova_table.index else 0
    ms_residual = ss_residual / df_residual if df_residual > 0 else 0
    ss_total = np.sum((df_clean[dv_col] - grand_mean) ** 2)

    # 解析 Omnibus
    omnibus_tests = []
    for effect in anova_table.index:
        if effect == "Residual" or "Intercept" in effect:
            continue
        row = anova_table.loc[effect]
        f_val = row["F"] if not np.isnan(row["F"]) else 0
        p_val = row["PR(>F)"] if not np.isnan(row["PR(>F)"]) else 1.0
        df_num = int(row["df"])
        ss_eff = row["sum_sq"]

        eta_p = partial_eta_squared(ss_eff, ss_residual)
        omega = omega_squared(ss_eff, ss_residual, ss_total, df_num, df_residual, n_total)

        # 清理效应名
        clean_effect = _clean_anova_effect(effect, factor_a, factor_b)

        omnibus_tests.append(OmnibusTest(
            effect=clean_effect,
            ss_type=ss_type,
            df_num=df_num,
            df_den=df_residual,
            f_value=float(f_val),
            p_value=float(p_val),
            eta_sq=round(ss_eff / ss_total, 4) if ss_total > 0 else 0,
            eta_sq_p=eta_p["value"],
            omega_sq=omega["value"],
            is_significant=p_val < alpha,
            significance_level=alpha,
        ))

    # 交互效应是否存在
    interaction_effect = _find_effect(omnibus_tests, "×")

    # 诊断
    diag = []
    norm_results = test_normality_groups(df_clean, dv_col, [factor_a, factor_b], alpha)
    for nr in norm_results:
        diag.append(DiagnosticResult(
            test_name=f"{nr['test']} ({nr['group']})",
            statistic=nr["statistic"], p_value=nr["p_value"],
            passed=nr["passed"], detail=nr["detail"],
        ))
    lev_result = test_homogeneity_two_factor(df_clean, dv_col, factor_a, factor_b, alpha)
    diag.append(DiagnosticResult(
        test_name="Levene", statistic=lev_result.statistic,
        p_value=lev_result.p_value, passed=lev_result.passed, detail=lev_result.detail,
    ))

    # 简单效应分析：显著交互优先，统一校正简单效应并在显著后执行条件内比较。
    simple_effects = []
    contrasts: list[ContrastResult] = []
    posthoc_emmeans: list[EMMeans] = []
    simple_warnings: list[str] = []
    significance_letters: list[SignificanceLetterGroup] = []
    interaction_significant = bool(interaction_effect and interaction_effect.is_significant)
    if interaction_significant:
        simple_effects, conditional_emmeans, conditional_contrasts, conditional_letters, simple_warnings = conditional_simple_effects(
            df_clean, dv_col, [factor_a, factor_b], [(factor_a, factor_b)],
            alpha=alpha, ss_type=ss_type, p_adjust=simple_effect_correction,
            posthoc_methods=posthoc_methods, control_group=control_group,
        )
        posthoc_emmeans.extend(conditional_emmeans)
        contrasts.extend(conditional_contrasts)
        significance_letters.extend(conditional_letters)

    # 事后比较 — 仅在交互不显著时，对显著主效应使用模型估计边际均值。
    if not (posthoc_methods == "none" or posthoc_methods == ["none"] or posthoc_methods == ("none",)) and not interaction_significant:
        for ot in omnibus_tests:
            if ot.is_significant and "×" not in ot.effect and df_clean[ot.effect].nunique() >= 2:
                factor_emm, raw = estimated_marginal_means(
                    model, df_clean, target_factors=[ot.effect],
                    categorical_factors=[factor_a, factor_b], covariates=[], alpha=alpha,
                    correction="none", df_resid=float(model.df_resid),
                )
                adjusted, letter_rows, method_warnings = apply_posthoc_methods_to_emm(
                    factor_emm, raw, methods=posthoc_methods, alpha=alpha,
                    factor=ot.effect, outcome=dv_col,
                    control_group=resolve_control_group(control_group, ot.effect),
                    contrast_prefix=f"[{ot.effect}] ",
                )
                posthoc_emmeans.extend(factor_emm)
                contrasts.extend(adjusted)
                significance_letters.extend(letter_rows)
                simple_warnings.extend(method_warnings)

    # 效应量汇总
    effect_sizes = []
    for ot in omnibus_tests:
        effect_sizes.append(EffectSize(
            measure="η²p", value=ot.eta_sq_p,
            interpretation=_interpret_eta(ot.eta_sq_p),
        ))
        effect_sizes.append(EffectSize(
            measure="ω²", value=ot.omega_sq,
            interpretation=_interpret_eta(ot.omega_sq),
        ))

    # 描述统计
    desc = _descriptive_stats_twoway(df_clean, dv_col, factor_a, factor_b)

    # 模型边际均值与对比：使用模型设计矩阵，而不是将原始组均值冒充 EMM。
    emmeans, emm_contrasts = (list(posthoc_emmeans), [])
    if emm_factors:
        requested_emm, requested_contrasts = estimated_marginal_means(
            model, df_clean, target_factors=emm_factors, categorical_factors=[factor_a, factor_b],
            covariates=[], alpha=alpha, correction=contrast_correction, df_resid=float(model.df_resid),
        )
        existing = {(item.group, item.source) for item in emmeans}
        emmeans.extend(item for item in requested_emm if (item.group, item.source) not in existing)
        # 显著交互时不自动把跨条件边际对比作为主要结论；条件内比较已由简单效应模块产生。
        if not interaction_significant:
            emm_contrasts = requested_contrasts
            contrasts.extend(emm_contrasts)
    plots = []
    if diagnostic_plots:
        influence = model.get_influence()
        plots = regression_diagnostic_plots(
            model.fittedvalues, model.resid, leverage=influence.hat_matrix_diag,
            cooks_distance=influence.cooks_distance[0],
        )
        plots.append(interaction_plot(df_clean, dv_col, factor_a, factor_b))

    # Design
    design = DesignInfo(
        variables=[
            VariableInfo(name=dv_col, dtype="float64", role=VariableRole.DEPENDENT),
            VariableInfo(name=factor_a, dtype=df_clean[factor_a].dtype.name,
                       role=VariableRole.BETWEEN,
                       levels=[str(l) for l in sorted(df_clean[factor_a].unique())],
                       n_unique=df_clean[factor_a].nunique()),
            VariableInfo(name=factor_b, dtype=df_clean[factor_b].dtype.name,
                       role=VariableRole.BETWEEN,
                       levels=[str(l) for l in sorted(df_clean[factor_b].unique())],
                       n_unique=df_clean[factor_b].nunique()),
        ],
        n_subjects=n_total,
        n_observations=n_total,
        between_factors=[factor_a, factor_b],
        dependent_vars=[dv_col],
    )

    # Report constraints
    report_constraints = []
    if interaction_effect and interaction_effect.is_significant:
        report_constraints.append(
            f"⚠ 交互作用 ({interaction_effect.effect}) 显著，主效应解读须谨慎。"
            f"请优先参考简单效应分析结果。"
        )
    else:
        report_constraints.append(
            "交互作用不显著，可直接解读主效应。"
        )

    method = MethodInfo(
        name="twoway_anova",
        label_zh=f"双因素方差分析（Type {ss_type} SS）",
        formula=f"{dv_col} ~ {factor_a} * {factor_b}",
        report_constraints=report_constraints,
    )

    warnings = list(simple_warnings)
    cell_counts = df_clean.groupby([factor_a, factor_b], observed=False).size()
    balanced = bool(len(cell_counts) and cell_counts.nunique() == 1)
    if ss_type == 1 and not balanced:
        warnings.append("当前为不平衡设计，Type I 平方和依赖因素进入公式的顺序；正式推断通常优先 Type III + Sum 对比。")
    if ss_type == 2 and interaction_significant:
        warnings.append("交互作用显著时 Type II 主效应不宜脱离交互直接解释；请优先查看校正后的简单效应。")
    if interaction_significant and emm_factors:
        warnings.append("交互作用显著：已输出所选 EMM 作为描述，但未自动执行跨条件边际对比；正式比较请使用条件简单效应结果。")
    selected_posthoc_set = set(posthoc_methods if isinstance(posthoc_methods, (list, tuple)) else [posthoc_methods])
    if selected_posthoc_set & {"duncan", "lsd"}:
        warnings.append("已选择 Duncan/LSD 宽松事后比较，可能提高第一类错误率；正式报告建议同时给出 Tukey 或 Holm 结果。")
    if "dunnett" in selected_posthoc_set:
        warnings.append("Dunnett 基于模型边际均值并使用 Bonferroni 保守近似；请确认对照水平填写唯一。")
    if lev_result.p_value < alpha:
        warnings.append(f"Levene 检验显著 (p={lev_result.p_value:.4f})，方差分析对非正态性有一定稳健性，"
                        f"但严重方差不齐可能影响结果。")

    return StatisticalResult(
        analysis_id=f"twoway_{factor_a}_{factor_b}",
        design=design,
        method=method,
        diagnostics=diag,
        omnibus_tests=omnibus_tests,
        contrasts=contrasts,
        significance_letters=significance_letters,
        simple_effects=simple_effects,
        effect_sizes=effect_sizes,
        estimated_marginal_means=emmeans,
        diagnostic_plots=plots,
        warnings=warnings,
        descriptive_stats=desc,
        data_snapshot={"n_total": n_total, "design": f"{factor_a}(×{factor_b})", "posthoc_methods": list(posthoc_methods) if isinstance(posthoc_methods, (list, tuple)) else [posthoc_methods], "control_group": control_group, "simple_effect_correction": simple_effect_correction},
        provenance={"ss_type": ss_type, "formula": formula, "contrast": "Sum" if ss_type == 3 else "Treatment", "posthoc_basis": "model EMM"},
    )


def _clean_anova_effect(raw: str, factor_a: str, factor_b: str) -> str:
    """清理 statsmodels ANOVA 效应名（兼容 Sum 对比编码）。"""
    import re

    clean = raw
    for factor in (factor_a, factor_b):
        pattern = rf"(?:C|__dw_cat)\(Q\('{re.escape(factor)}'\)(?:,\s*(?:Sum|__dw_sum))?\)"
        clean = re.sub(pattern, factor, clean)
    clean = clean.replace("Intercept", "截距")
    clean = clean.replace(":", " × ")
    return clean.strip()


def _find_effect(omnibus_tests: list[OmnibusTest], keyword: str) -> Optional[OmnibusTest]:
    """查找含关键词的效应。"""
    for ot in omnibus_tests:
        if keyword in ot.effect:
            return ot
    return None


def _descriptive_stats_twoway(
    df: pd.DataFrame,
    dv_col: str,
    factor_a: str,
    factor_b: str,
) -> list[dict]:
    """计算各组合的描述性统计。"""
    result = []
    for a in sorted(df[factor_a].unique()):
        for b in sorted(df[factor_b].unique()):
            sub = df[(df[factor_a] == a) & (df[factor_b] == b)][dv_col]
            result.append({
                factor_a: str(a),
                factor_b: str(b),
                "n": len(sub),
                "mean": round(sub.mean(), 4),
                "sd": round(sub.std(ddof=1), 4) if len(sub) > 1 else 0,
            })
    return result


def _compute_emm_twoway(
    df: pd.DataFrame,
    dv_col: str,
    factor_a: str,
    factor_b: str,
    ms_residual: float,
    df_residual: float,
) -> list[EMMeans]:
    """计算各组合的估算边际均值。"""
    # 对于 ANOVA（无协变量），EMM 就是简单的组均值
    results = []
    for a in sorted(df[factor_a].unique()):
        for b in sorted(df[factor_b].unique()):
            sub = df[(df[factor_a] == a) & (df[factor_b] == b)][dv_col]
            n = len(sub)
            m = sub.mean()
            se = np.sqrt(ms_residual / n) if ms_residual > 0 and n > 0 else 0
            t_crit = stats.t.ppf(0.975, df_residual)
            ci_half = t_crit * se
            results.append(EMMeans(
                group=f"{factor_a}={a}, {factor_b}={b}",
                mean=round(m, 4),
                se=round(se, 4),
                ci_lower=round(m - ci_half, 4),
                ci_upper=round(m + ci_half, 4),
            ))
    return results


def _interpret_eta(value: float) -> str:
    if value < 0.01: return "微小效应"
    elif value < 0.06: return "小效应"
    elif value < 0.14: return "中效应"
    else: return "大效应"


def threeway_anova(
    df: pd.DataFrame,
    dv_col: str,
    factor_a: str,
    factor_b: str,
    factor_c: str,
    posthoc_methods: str | list[str] | tuple[str, ...] = "tukey",
    control_group: str | None = None,
    alpha: float = 0.05,
    ss_type: int = 3,
    *,
    posthoc_method: str | None = None,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
    simple_effect_correction: str = "holm",
) -> StatisticalResult:
    """三因素 ANOVA（between-subjects）。"""
    df_clean = df[[dv_col, factor_a, factor_b, factor_c]].dropna().copy()

    for col in [factor_a, factor_b, factor_c]:
        df_clean[col] = df_clean[col].astype("category")

    if posthoc_method is not None:
        posthoc_methods = posthoc_method
    if ss_type not in (1, 2, 3):
        raise ValueError("ss_type 必须为 1、2 或 3")
    if ss_type == 3:
        formula = (
            f"Q('{dv_col}') ~ __dw_cat(Q('{factor_a}'), __dw_sum) "
            f"* __dw_cat(Q('{factor_b}'), __dw_sum) * __dw_cat(Q('{factor_c}'), __dw_sum)"
        )
    else:
        formula = (f"Q('{dv_col}') ~ __dw_cat(Q('{factor_a}')) * __dw_cat(Q('{factor_b}')) "
                   f"* __dw_cat(Q('{factor_c}'))")
    model = ols(formula, data=df_clean).fit()
    try:
        anova_table = sm.stats.anova_lm(model, typ=ss_type)
    except Exception as exc:
        raise RuntimeError(f"Type {ss_type} ANOVA 拟合失败；未切换为其他平方和类型: {exc}") from exc

    n_total = len(df_clean)
    ss_residual = anova_table.loc["Residual", "sum_sq"] if "Residual" in anova_table.index else 0
    df_residual = anova_table.loc["Residual", "df"] if "Residual" in anova_table.index else 0
    ss_total = np.sum((df_clean[dv_col] - df_clean[dv_col].mean()) ** 2)

    omnibus_tests = []
    for effect in anova_table.index:
        if effect == "Residual" or "Intercept" in effect:
            continue
        row = anova_table.loc[effect]
        f_val = row["F"] if not np.isnan(row["F"]) else 0
        p_val = row["PR(>F)"] if not np.isnan(row["PR(>F)"]) else 1.0
        df_num = int(row["df"])
        ss_eff = row["sum_sq"]

        eta_p = partial_eta_squared(ss_eff, ss_residual)
        clean = _clean_anova_effect_three(effect, factor_a, factor_b, factor_c)

        omnibus_tests.append(OmnibusTest(
            effect=clean,
            ss_type=ss_type,
            df_num=df_num, df_den=df_residual,
            f_value=float(f_val),
            p_value=float(p_val),
            eta_sq=round(ss_eff / ss_total, 4) if ss_total > 0 else 0,
            eta_sq_p=eta_p["value"],
            omega_sq=0,
            is_significant=p_val < alpha,
            significance_level=alpha,
        ))

    # 找三阶交互
    threeway_eff = _find_effect_threeway(omnibus_tests, "×")
    report_constraints = []
    if threeway_eff:
        # 项含两个 "×" → 三阶交互
        if threeway_eff.effect.count("×") >= 2 and threeway_eff.is_significant:
            report_constraints.append(
                f"⚠ 三阶交互 ({threeway_eff.effect}) 显著，"
                f"不能独立解读任何低阶交互或主效应。请进行简单效应分析。"
            )

    factor_vars = [
        VariableInfo(name=fa, dtype="category", role=VariableRole.BETWEEN,
                   n_unique=df_clean[fa].nunique())
        for fa in [factor_a, factor_b, factor_c]
    ]
    design = DesignInfo(
        variables=[VariableInfo(name=dv_col, dtype="float64", role=VariableRole.DEPENDENT)] + factor_vars,
        n_subjects=n_total,
        n_observations=n_total,
        between_factors=[factor_a, factor_b, factor_c],
        dependent_vars=[dv_col],
    )

    method = MethodInfo(
        name="threeway_anova",
        label_zh=f"三因素方差分析（Type {ss_type} SS）",
        formula=f"{dv_col} ~ {factor_a} * {factor_b} * {factor_c}",
        report_constraints=report_constraints,
    )

    # 简单描述统计
    desc = []
    for a in sorted(df_clean[factor_a].unique())[:5]:
        for b in sorted(df_clean[factor_b].unique())[:5]:
            for c in sorted(df_clean[factor_c].unique())[:3]:
                sub = df_clean[(df_clean[factor_a] == a) & (df_clean[factor_b] == b) & (df_clean[factor_c] == c)][dv_col]
                if len(sub) > 0:
                    desc.append({
                        factor_a: str(a), factor_b: str(b), factor_c: str(c),
                        "n": len(sub),
                        "mean": round(sub.mean(), 4),
                        "sd": round(sub.std(ddof=1), 4) if len(sub) > 1 else 0,
                    })

    emmeans: list[EMMeans] = []
    contrasts: list[ContrastResult] = []
    simple_effects: list[SimpleEffectResult] = []
    significance_letters: list[SignificanceLetterGroup] = []
    warnings: list[str] = []
    significant_interactions = [item.effect for item in omnibus_tests if item.is_significant and "×" in item.effect]
    interaction_structures = [tuple(part.strip() for part in effect.split("×")) for effect in significant_interactions]
    if interaction_structures:
        simple_effects, conditional_emmeans, conditional_contrasts, conditional_letters, simple_warnings = conditional_simple_effects(
            df_clean, dv_col, [factor_a, factor_b, factor_c], interaction_structures,
            alpha=alpha, ss_type=ss_type, p_adjust=simple_effect_correction,
            posthoc_methods=posthoc_methods, control_group=control_group,
        )
        emmeans.extend(conditional_emmeans)
        contrasts.extend(conditional_contrasts)
        significance_letters.extend(conditional_letters)
        warnings.extend(simple_warnings)
    if not (posthoc_methods == "none" or posthoc_methods == ["none"] or posthoc_methods == ("none",)):
        for item in omnibus_tests:
            if not item.is_significant or "×" in item.effect or df_clean[item.effect].nunique() < 2:
                continue
            involved = [effect for effect in significant_interactions if item.effect in [part.strip() for part in effect.split("×")]]
            if involved:
                warnings.append(
                    f"主效应 {item.effect} 参与显著交互 {involved}，未自动执行边际主效应事后比较；请使用 EMM 指定条件组合进行简单效应比较。"
                )
                continue
            factor_emm, raw = estimated_marginal_means(
                model, df_clean, target_factors=[item.effect],
                categorical_factors=[factor_a, factor_b, factor_c], covariates=[],
                alpha=alpha, correction="none", df_resid=float(model.df_resid),
            )
            adjusted, letter_rows, method_warnings = apply_posthoc_methods_to_emm(
                factor_emm, raw, methods=posthoc_methods, alpha=alpha,
                factor=item.effect, outcome=dv_col,
                control_group=resolve_control_group(control_group, item.effect),
                contrast_prefix=f"[{item.effect}] ",
            )
            emmeans.extend(factor_emm)
            contrasts.extend(adjusted)
            significance_letters.extend(letter_rows)
            warnings.extend(method_warnings)
    if emm_factors:
        requested_emm, requested_contrasts = estimated_marginal_means(
            model, df_clean, target_factors=emm_factors, categorical_factors=[factor_a, factor_b, factor_c],
            covariates=[], alpha=alpha, correction=contrast_correction, df_resid=float(model.df_resid),
        )
        existing = {(item.group, item.source) for item in emmeans}
        emmeans.extend(item for item in requested_emm if (item.group, item.source) not in existing)
        requested_involved = any(
            factor in set(part.strip() for part in interaction.split("×"))
            for factor in emm_factors for interaction in significant_interactions
        )
        if requested_involved:
            warnings.append(
                "显式 EMM 涉及显著交互中的因素，已保留边际均值作描述，但未自动加入跨条件边际对比；请优先解释条件简单效应。"
            )
        else:
            contrasts.extend(requested_contrasts)
    if ss_type == 1:
        cell_sizes = df_clean.groupby([factor_a, factor_b, factor_c], observed=True).size()
        if not cell_sizes.empty and cell_sizes.nunique() > 1:
            warnings.append("当前为不平衡设计且选择 Type I 平方和；结果依赖因素进入公式的顺序，建议优先使用 Type III + Sum 对比。")
    if ss_type == 2 and significant_interactions:
        warnings.append("存在显著交互且选择 Type II 平方和；主效应应谨慎解释，建议优先报告条件简单效应或改用 Type III。")
    selected_posthoc_set = set(posthoc_methods if isinstance(posthoc_methods, (list, tuple)) else [posthoc_methods])
    if selected_posthoc_set & {"duncan", "lsd"}:
        warnings.append("已选择 Duncan/LSD 宽松事后比较，可能提高第一类错误率；正式报告建议同时给出 Tukey 或 Holm 结果。")
    if "dunnett" in selected_posthoc_set:
        warnings.append("Dunnett 基于模型边际均值并使用 Bonferroni 保守近似；请确认对照水平填写唯一。")
    plots = []
    if diagnostic_plots:
        influence = model.get_influence()
        plots = regression_diagnostic_plots(
            model.fittedvalues, model.resid, leverage=influence.hat_matrix_diag,
            cooks_distance=influence.cooks_distance[0],
        )
        plots.append(interaction_plot(df_clean, dv_col, factor_a, factor_b))

    return StatisticalResult(
        analysis_id=f"threeway_{factor_a}_{factor_b}_{factor_c}",
        design=design,
        method=method,
        omnibus_tests=omnibus_tests,
        estimated_marginal_means=emmeans, contrasts=contrasts, simple_effects=simple_effects,
        diagnostic_plots=plots,
        warnings=warnings, descriptive_stats=desc,
        data_snapshot={"n_total": n_total, "posthoc_methods": list(posthoc_methods) if isinstance(posthoc_methods, (list, tuple)) else [posthoc_methods], "control_group": control_group, "simple_effect_correction": simple_effect_correction},
        provenance={"ss_type": ss_type, "formula": formula, "contrast": "Sum" if ss_type == 3 else "Treatment", "posthoc_basis": "model EMM"},
    )


def _clean_anova_effect_three(raw: str, fa: str, fb: str, fc: str) -> str:
    import re

    clean = raw
    for factor in (fa, fb, fc):
        pattern = rf"(?:C|__dw_cat)\(Q\('{re.escape(factor)}'\)(?:,\s*(?:Sum|__dw_sum))?\)"
        clean = re.sub(pattern, factor, clean)
    clean = clean.replace("Intercept", "截距")
    clean = clean.replace(":", " × ")
    return clean.strip()


def _find_effect_threeway(tests: list[OmnibusTest], keyword: str) -> Optional[OmnibusTest]:
    """找含两个 '×' 的三阶交互。"""
    for ot in tests:
        if ot.effect.count(keyword) >= 2:
            return ot
    # 回退：找一个 '×' 的
    for ot in tests:
        if keyword in ot.effect:
            return ot
    return None
