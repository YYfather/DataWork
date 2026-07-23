"""单/双/三因素 MANOVA 多元方差分析。"""

from __future__ import annotations

import re
from collections.abc import Mapping

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.multivariate.manova import MANOVA as SM_MANOVA
from statsmodels.stats.multitest import multipletests

from .result import (
    DesignInfo,
    MethodInfo,
    ContrastResult,
    DiagnosticResult,
    EMMeans,
    SignificanceLetterGroup,
    OmnibusTest,
    StatisticalResult,
    UnivariateFollowUpResult,
    VariableInfo,
    VariableRole,
)
from .model_support import apply_posthoc_methods_to_emm, estimated_marginal_means, resolve_control_group
from .factorial_followup import conditional_simple_effects
from .posthoc import normalize_posthoc_methods


_MULTIVARIATE_STATISTICS: dict[str, tuple[str, str]] = {
    "pillai": ("Pillai's trace", "Pillai 轨迹"),
    "wilks": ("Wilks' lambda", "Wilks' Lambda"),
    "hotelling_lawley": ("Hotelling-Lawley trace", "Hotelling–Lawley 轨迹"),
    "roy": ("Roy's greatest root", "Roy 最大根"),
}

_STATISTIC_ALIASES = {
    "pillai_trace": "pillai",
    "wilks_lambda": "wilks",
    "hotelling": "hotelling_lawley",
    "hotelling_trace": "hotelling_lawley",
    "roys_largest_root": "roy",
    "roy_largest_root": "roy",
}


def manova(
    df: pd.DataFrame,
    dv_cols: list[str],
    between_cols: list[str],
    alpha: float = 0.05,
    parameters: Mapping[str, object] | None = None,
    *,
    estimate_marginal_means: bool = False,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    """执行一至八因素对象间 MANOVA。

    因素采用 Sum 对比并拟合完整析因模型，因此各阶设计分别检验
    主效应以及所有低阶/高阶交互。该实现不把对象内重复因素或随机效应当作
    普通 MANOVA；重复测量应使用混合设计/线性混合模型。
    """
    parameters = dict(parameters or {})
    factors = list(dict.fromkeys(between_cols))
    outcomes = list(dict.fromkeys(dv_cols))
    if len(outcomes) < 2:
        raise ValueError("MANOVA 至少需要两个互不重复的连续因变量")
    if not 1 <= len(factors) <= 8:
        raise ValueError("MANOVA 需要 1–8 个互不重复的对象间分类因素")

    selected_keys = _selected_statistics(parameters)
    default_primary = selected_keys[0] if len(selected_keys) == 1 else "pillai"
    primary_key = str(parameters.get("primary_multivariate_test", default_primary)).strip().lower()
    primary_key = _STATISTIC_ALIASES.get(primary_key, primary_key)
    if primary_key not in _MULTIVARIATE_STATISTICS:
        raise ValueError(f"未知主要 MANOVA 判据: {primary_key}")
    # 正式报告必须能展示驱动结论的预先指定判据。即使用户只勾选了另一项
    # 补充统计量，也把主要判据加入结果，并放在每个效应的首要报告位置。
    if primary_key not in selected_keys:
        selected_keys = [primary_key, *selected_keys]
    elif selected_keys[0] != primary_key:
        selected_keys = [primary_key, *(key for key in selected_keys if key != primary_key)]

    required = outcomes + factors
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"数据中缺少 MANOVA 分析列: {missing}")
    df_clean = df[required].copy()
    for column in outcomes:
        df_clean[column] = pd.to_numeric(df_clean[column], errors="coerce")
    df_clean = df_clean.dropna(subset=required)
    if df_clean.empty:
        raise ValueError("MANOVA 删除缺失或非数值结果后没有完整案例")
    invalid_factors = [
        column for column in factors
        if df_clean[column].nunique(dropna=True) < 2
    ]
    if invalid_factors:
        raise ValueError(f"MANOVA 分类因素至少需要两个有效水平: {invalid_factors}")
    constant_outcomes = [
        column for column in outcomes
        if np.isclose(float(df_clean[column].var(ddof=1)), 0.0)
    ]
    if constant_outcomes:
        raise ValueError(f"MANOVA 因变量不能为常数或零方差: {constant_outcomes}")
    centered_outcomes = (
        df_clean[outcomes].to_numpy(dtype=float)
        - df_clean[outcomes].to_numpy(dtype=float).mean(axis=0)
    )
    outcome_rank = int(np.linalg.matrix_rank(centered_outcomes))
    if outcome_rank < len(outcomes):
        raise RuntimeError(
            f"MANOVA 联合响应矩阵秩不足：秩为 {outcome_rank}，因变量数为 {len(outcomes)}；"
            "请移除完全线性相关或重复的因变量"
        )

    rename_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    for index, column in enumerate(outcomes):
        safe = f"DV{index + 1}"
        rename_map[column] = safe
        reverse_map[safe] = column
    for index, column in enumerate(factors):
        safe = f"F{index + 1}"
        rename_map[column] = safe
        reverse_map[safe] = column
    df_safe = df_clean.rename(columns=rename_map)
    safe_outcomes = [rename_map[column] for column in outcomes]
    safe_factors = [rename_map[column] for column in factors]
    dv_part = " + ".join(safe_outcomes)
    rhs = " * ".join(f"C({column}, Sum)" for column in safe_factors)
    formula = f"{dv_part} ~ {rhs}"

    try:
        model = SM_MANOVA.from_formula(formula, data=df_safe)
    except Exception as exc:
        raise RuntimeError(f"MANOVA 完整析因模型构造失败: {exc}") from exc
    model_rank = int(np.linalg.matrix_rank(model.exog))
    model_columns = int(model.exog.shape[1])
    if model_rank < model_columns:
        raise RuntimeError(
            f"MANOVA 设计矩阵秩不足：秩为 {model_rank}，参数列为 {model_columns}；"
            "请检查空单元、完全混杂或减少因素阶数"
        )
    if model.exog.shape[0] <= model_rank:
        raise RuntimeError(
            f"MANOVA 完整模型没有剩余自由度：完整案例 {model.exog.shape[0]}，"
            f"模型秩 {model_rank}；请增加因素单元内重复观测"
        )
    try:
        multivariate_results = _safe_multivariate_results(model)
    except Exception as exc:
        raise RuntimeError(
            f"MANOVA 多元统计量计算失败，请检查响应协方差矩阵和样本量: {exc}"
        ) from exc

    omnibus_tests: list[OmnibusTest] = []
    warnings: list[str] = []
    effect_primary_p: dict[str, float] = {}
    for raw_effect, effect_result in multivariate_results.items():
        if raw_effect == "Intercept" or "stat" not in effect_result:
            continue
        effect_label = _display_effect(raw_effect, reverse_map)
        statistic_table = effect_result["stat"]
        primary_statsmodels_name = _MULTIVARIATE_STATISTICS[primary_key][0]
        if primary_statsmodels_name in statistic_table.index:
            try:
                primary_p = float(statistic_table.loc[primary_statsmodels_name]["Pr > F"])
                if np.isfinite(primary_p):
                    effect_primary_p[effect_label] = primary_p
            except (KeyError, TypeError, ValueError):
                warnings.append(f"{effect_label} 的主要多元判据无法读取，显著性跟进将按保守方式跳过。")
        for statistic_key in selected_keys:
            statsmodels_name, display_name = _MULTIVARIATE_STATISTICS[statistic_key]
            if statsmodels_name not in statistic_table.index:
                warnings.append(f"{effect_label} 未返回 {display_name}，该行已跳过。")
                continue
            row = statistic_table.loc[statsmodels_name]
            try:
                statistic_value = float(row["Value"])
                df_num = float(row["Num DF"])
                df_den = float(row["Den DF"])
                f_value = float(row["F Value"])
                p_value = float(row["Pr > F"])
            except (KeyError, TypeError, ValueError):
                warnings.append(f"{effect_label} 的 {display_name} 结果格式异常，未纳入结果表。")
                continue
            if not np.all(np.isfinite([statistic_value, df_num, df_den, f_value, p_value])):
                warnings.append(f"{effect_label} 的 {display_name} 出现非有限值，未纳入结果表。")
                continue
            omnibus_tests.append(OmnibusTest(
                effect=effect_label, statistic_name=display_name, statistic_value=statistic_value,
                ss_type=3, df_num=df_num, df_den=df_den, f_value=f_value, p_value=p_value,
                eta_sq=0.0, eta_sq_p=0.0, omega_sq=0.0,
                is_significant=p_value < alpha, significance_level=alpha,
            ))
    if not omnibus_tests:
        raise RuntimeError("MANOVA 未获得任何有限的多元总体检验结果")

    diagnostics: list[DiagnosticResult] = []
    residuals: np.ndarray | None = None
    try:
        fitted_params, _, _, _ = model._fittedmod
        residuals = np.asarray(model.endog - model.exog.dot(fitted_params), dtype=float)
    except Exception as exc:
        warnings.append(f"完整析因模型残差未能提取：{exc}")

    box_m_alpha = float(parameters.get("box_m_alpha", 0.001))
    if not 0 < box_m_alpha < 1:
        raise ValueError("Box's M 判定阈值必须位于 0 和 1 之间")
    if bool(parameters.get("covariance_test", True)):
        box_result, box_warning = _box_m_test(df_clean, outcomes, factors, box_m_alpha)
        if box_result is not None:
            diagnostics.append(box_result)
        if box_warning:
            warnings.append(box_warning)
    if bool(parameters.get("correlation_diagnostics", True)) and residuals is not None:
        bartlett = _bartlett_sphericity_test(
            pd.DataFrame(residuals, columns=outcomes), alpha, residual_based=True
        )
        if bartlett is not None:
            diagnostics.append(bartlett)
    if bool(parameters.get("normality_test", True)) and residuals is not None:
        try:
            diagnostics.extend(_mardia_diagnostics(residuals, alpha))
        except Exception as exc:
            warnings.append(f"Mardia 多元正态近似诊断未能计算：{exc}")

    correlation = df_clean[outcomes].corr().astype(float)
    off_diagonal = correlation.to_numpy()[~np.eye(len(outcomes), dtype=bool)]
    max_abs_correlation = float(np.max(np.abs(off_diagonal))) if off_diagonal.size else 0.0
    numeric = df_clean[outcomes].to_numpy(dtype=float)
    scale = np.std(numeric, axis=0, ddof=1)
    standardized = (numeric - np.mean(numeric, axis=0)) / np.where(scale > 0, scale, 1.0)
    condition_number = float(np.linalg.cond(standardized)) if standardized.size else float("nan")
    if max_abs_correlation >= 0.95:
        warnings.append(f"因变量最大绝对相关系数为 {max_abs_correlation:.3f}，存在严重冗余/共线风险。")
    elif max_abs_correlation >= 0.85:
        warnings.append(f"因变量最大绝对相关系数为 {max_abs_correlation:.3f}，建议核对是否存在高度重复指标。")
    if np.isfinite(condition_number) and condition_number > 1000:
        warnings.append(f"因变量矩阵条件数为 {condition_number:.1f}，数值稳定性较弱。")

    follow_up_tests: list[UnivariateFollowUpResult] = []
    contrasts: list[ContrastResult] = []
    emmeans_all: list[EMMeans] = []
    significance_letters: list[SignificanceLetterGroup] = []
    follow_up_mode = str(parameters.get("follow_up_mode", "significant")).strip().lower()
    follow_up_ss_type = int(parameters.get("follow_up_ss_type", 3))
    follow_up_correction = str(parameters.get("follow_up_correction", "holm")).strip().lower()
    posthoc_methods = normalize_posthoc_methods(parameters.get("posthoc_methods", ["tukey"]), default="tukey")
    control_group = str(parameters.get("control_group", "")).strip() or None
    posthoc_scope = str(parameters.get("posthoc_scope", "significance_gated")).strip().lower()
    if follow_up_mode not in {"none", "significant", "all"}:
        raise ValueError("follow_up_mode 必须为 none、significant 或 all")
    if follow_up_ss_type not in {1, 2, 3}:
        raise ValueError("MANOVA 单变量跟进平方和类型必须为 1、2 或 3")
    if posthoc_scope not in {"significance_gated", "branch_all"}:
        raise ValueError("posthoc_scope 必须为 significance_gated 或 branch_all")

    follow_rows: list[dict[str, object]] = []
    fitted_models: dict[str, object] = {}
    if follow_up_mode != "none" or estimate_marginal_means:
        for safe_outcome, outcome in zip(safe_outcomes, outcomes):
            if follow_up_ss_type == 3:
                univariate_rhs = " * ".join(f"C({factor}, Sum)" for factor in safe_factors)
            else:
                univariate_rhs = " * ".join(f"C({factor})" for factor in safe_factors)
            uni_formula = f"{safe_outcome} ~ {univariate_rhs}"
            uni_model = ols(uni_formula, data=df_safe).fit()
            fitted_models[outcome] = uni_model
            table = sm.stats.anova_lm(uni_model, typ=follow_up_ss_type)
            residual_ss = float(table.loc["Residual", "sum_sq"])
            residual_df = float(table.loc["Residual", "df"])
            for raw_effect in table.index:
                if raw_effect == "Residual" or "Intercept" in raw_effect:
                    continue
                effect = _display_effect(raw_effect, reverse_map)
                if follow_up_mode == "none":
                    continue
                if follow_up_mode == "significant" and effect_primary_p.get(effect, 1.0) >= alpha:
                    continue
                row = table.loc[raw_effect]
                p_value = float(row["PR(>F)"]) if np.isfinite(row["PR(>F)"]) else 1.0
                ss_effect = float(row["sum_sq"])
                eta_partial = ss_effect / (ss_effect + residual_ss) if ss_effect + residual_ss > 0 else 0.0
                follow_rows.append({
                    "outcome": outcome, "effect": effect, "ss_type": follow_up_ss_type,
                    "df_num": float(row["df"]), "df_den": residual_df,
                    "f_value": float(row["F"]) if np.isfinite(row["F"]) else 0.0,
                    "p_value": p_value, "sum_sq": ss_effect,
                    "mean_sq": ss_effect / float(row["df"]) if float(row["df"]) > 0 else None,
                    "eta_sq_p": eta_partial,
                })
        if follow_rows:
            raw_p = np.asarray([float(row["p_value"]) for row in follow_rows], dtype=float)
            adjusted = raw_p if follow_up_correction == "none" else multipletests(raw_p, alpha=alpha, method=follow_up_correction)[1]
            for index, row in enumerate(follow_rows):
                p_adjusted = float(adjusted[index])
                follow_up_tests.append(UnivariateFollowUpResult(
                    **row, p_adjusted=p_adjusted, significant=p_adjusted < alpha,
                    correction=follow_up_correction,
                    interpretation="多元总体检验后的单变量定位结果；需与多元结论及效应量共同解释。",
                ))

    simple_effects = []
    significant_interactions_by_outcome: dict[str, list[tuple[str, ...]]] = {}
    blocked_main_factors: dict[str, set[str]] = {}
    for item in follow_up_tests:
        if not item.significant or "×" not in item.effect:
            continue
        interaction_factors = tuple(part.strip() for part in item.effect.split("×") if part.strip())
        significant_interactions_by_outcome.setdefault(item.outcome, []).append(interaction_factors)
        blocked_main_factors.setdefault(item.outcome, set()).update(interaction_factors)

    simple_effect_correction = str(parameters.get("simple_effect_correction", "holm")).strip().lower()
    if significant_interactions_by_outcome and len(factors) <= 3:
        for outcome, interactions in significant_interactions_by_outcome.items():
            outcome_simple, outcome_emm, outcome_contrasts, outcome_letters, outcome_warnings = conditional_simple_effects(
                df_clean, outcome, factors, interactions, alpha=alpha,
                ss_type=follow_up_ss_type, p_adjust=simple_effect_correction,
                posthoc_methods=posthoc_methods, control_group=control_group, outcome_label=outcome,
                compare_all=posthoc_scope == "branch_all",
            )
            simple_effects.extend(outcome_simple)
            emmeans_all.extend(outcome_emm)
            contrasts.extend(outcome_contrasts)
            significance_letters.extend(outcome_letters)
            warnings.extend(outcome_warnings)
    elif significant_interactions_by_outcome:
        warnings.append(
            "四因素及以上 MANOVA 检测到显著交互；为避免自动生成指数级条件比较，"
            "系统保留多元总体检验和校正后单变量跟进，但不自动展开简单效应。请依据预先规划的条件对比继续分析。"
        )

    # 无显著交互时，或主效应未卷入任何显著交互时，才执行边际主效应比较。
    if posthoc_methods != ["none"] and follow_up_tests:
        if posthoc_scope == "branch_all":
            marginal_candidates = [
                (outcome, factor)
                for outcome in outcomes
                for factor in factors
                if factor not in blocked_main_factors.get(outcome, set())
            ]
        else:
            marginal_candidates = [
                (item.outcome, item.effect)
                for item in follow_up_tests
                if item.significant
                and "×" not in item.effect
                and item.effect in factors
                and item.effect not in blocked_main_factors.get(item.outcome, set())
            ]
        for outcome, factor in marginal_candidates:
            if int(df_clean[factor].nunique()) < 2:
                continue
            safe_factor = rename_map[factor]
            uni_model = fitted_models[outcome]
            emmeans, raw_contrasts = estimated_marginal_means(
                uni_model, df_safe, target_factors=[safe_factor], categorical_factors=safe_factors,
                covariates=[], alpha=alpha, correction="none", df_resid=float(uni_model.df_resid),
            )
            for emm in emmeans:
                emm.group = emm.group.replace(safe_factor, factor)
                emm.levels = {factor if key == safe_factor else reverse_map.get(key, key): value for key, value in emm.levels.items()}
                emm.source = f"MANOVA 跟进模型 EMM：{outcome}"
            adjusted_contrasts, letter_rows, method_warnings = apply_posthoc_methods_to_emm(
                emmeans, raw_contrasts, methods=posthoc_methods, alpha=alpha,
                factor=factor, outcome=outcome,
                control_group=resolve_control_group(control_group, factor),
                contrast_prefix=f"[{outcome} | {factor}] ",
            )
            for contrast in adjusted_contrasts:
                contrast.contrast = contrast.contrast.replace(safe_factor, factor)
            emmeans_all.extend(emmeans)
            contrasts.extend(adjusted_contrasts)
            significance_letters.extend(letter_rows)
            warnings.extend(method_warnings)

    # 用户显式选择的 EMM 必须真正传入引擎。显著交互存在时只输出描述性 EMM，
    # 跨条件边际对比由条件简单效应替代。
    requested_emm_factors = [factor for factor in (emm_factors or []) if factor in factors]
    if estimate_marginal_means and requested_emm_factors:
        safe_targets = [rename_map[factor] for factor in requested_emm_factors]
        for outcome in outcomes:
            uni_model = fitted_models.get(outcome)
            if uni_model is None:
                continue
            requested_emm, requested_contrasts = estimated_marginal_means(
                uni_model, df_safe, target_factors=safe_targets, categorical_factors=safe_factors,
                covariates=[], alpha=alpha, correction=contrast_correction, df_resid=float(uni_model.df_resid),
            )
            for emm in requested_emm:
                emm.group = f"[{outcome}] " + emm.group
                emm.levels = {reverse_map.get(key, key): value for key, value in emm.levels.items()}
                emm.source = f"用户指定 MANOVA 跟进 EMM：{outcome}"
            existing = {(item.group, tuple(sorted(item.levels.items()))) for item in emmeans_all}
            emmeans_all.extend(
                item for item in requested_emm
                if (item.group, tuple(sorted(item.levels.items()))) not in existing
            )
            involved = blocked_main_factors.get(outcome, set())
            if not involved.intersection(requested_emm_factors):
                for contrast in requested_contrasts:
                    display = contrast.contrast
                    for safe, original in reverse_map.items():
                        display = display.replace(safe, original)
                    contrast.contrast = f"[{outcome} | 用户指定 EMM] {display}"
                contrasts.extend(requested_contrasts)

    if "duncan" in posthoc_methods:
        warnings.append("Duncan 多重极差检验较宽松，可能提高第一类错误率；默认推荐 Tukey/Holm。")
    if "lsd" in posthoc_methods:
        warnings.append("Fisher protected LSD 未控制全部成对比较的家族错误率，仅建议用于预先规划或探索性分析。")
    if "dunnett" in posthoc_methods:
        warnings.append("Dunnett 只覆盖处理组与对照组，不生成完整显著性字母分组。")
    if significant_interactions_by_outcome:
        warnings.append("检测到显著交互：已停止涉及因素的自动边际主效应比较，并改为校正后的条件简单效应及条件内比较。")
    if estimate_marginal_means and requested_emm_factors and any(
        blocked_main_factors.get(outcome, set()).intersection(requested_emm_factors) for outcome in outcomes
    ):
        warnings.append("部分用户指定 EMM 涉及显著交互因素：仅保留 EMM 描述，未执行跨条件边际对比。")
    cell_counts = df_clean.groupby(factors, observed=False).size()
    balanced = bool(len(cell_counts) and cell_counts.nunique() == 1)
    if follow_up_ss_type == 1 and not balanced:
        warnings.append("单变量跟进使用 Type I 且设计不平衡，结果依赖因素进入公式的顺序；通常优先 Type III。")
    if follow_up_ss_type == 2 and significant_interactions_by_outcome:
        warnings.append("存在显著交互时，Type II 单变量主效应不宜脱离交互解释；请优先查看简单效应。")

    variables: list[VariableInfo] = [
        VariableInfo(name=column, dtype="float64", role=VariableRole.DEPENDENT,
                     n_unique=int(df_clean[column].nunique(dropna=True)),
                     missing_rate=float(df[column].isna().mean()), confidence=1.0)
        for column in outcomes
    ]
    for column in factors:
        levels = sorted(df_clean[column].dropna().astype(str).unique().tolist())
        variables.append(VariableInfo(name=column, dtype="category", role=VariableRole.BETWEEN,
                                      levels=levels, n_unique=len(levels),
                                      missing_rate=float(df[column].isna().mean()), confidence=1.0))

    selected_labels = [_MULTIVARIATE_STATISTICS[key][1] for key in selected_keys]
    warnings.append(
        f"当前为{len(factors)}因素 MANOVA，完整模型包含全部主效应及最高至 {len(factors)} 阶交互；主要判据为 {_MULTIVARIATE_STATISTICS[primary_key][1]}。"
    )
    if selected_keys == list(_MULTIVARIATE_STATISTICS):
        warnings.append("已完整输出四种多元检验统计量；正式结论应依据预先指定的主要判据，避免事后挑选显著结果。")

    design = DesignInfo(variables=variables, n_subjects=len(df_clean), n_observations=len(df_clean),
                        between_factors=factors, dependent_vars=outcomes)
    method = MethodInfo(
        name="manova", label_zh=f"{len(factors)}因素多元方差分析（MANOVA）",
        formula=f"{' + '.join(outcomes)} ~ {' * '.join(factors)}",
        software="statsmodels MANOVA + OLS follow-up",
        research_question=f"{', '.join(outcomes)} 的联合响应是否受 {' × '.join(factors)} 影响",
        reasoning=[
            "多个连续因变量被作为联合响应分析。",
            f"完整析因模型检验 {len(factors)} 个因素的主效应及全部交互作用。",
            "采用 Sum 对比获得对参考水平不敏感的对称效应检验。",
            f"主要多元判据：{_MULTIVARIATE_STATISTICS[primary_key][1]}；输出：{'、'.join(selected_labels)}。",
        ],
        assumptions=["观测独立", "各设计单元近似多元正态", "设计单元方差-协方差矩阵相近", "因变量不存在严重共线"],
        report_constraints=[
            "多元总体检验显著后，单变量跟进用于定位差异来源，不能替代多元总体结论。",
            f"{len(factors)} 因素模型对样本量和单元重复要求较高；空单元、单例单元或秩不足会阻止执行。",
            "当前为对象间 MANOVA，不支持对象内重复测量或随机效应。",
        ],
    )
    return StatisticalResult(
        analysis_id=f"manova_{'_'.join(factors)}", design=design, method=method,
        diagnostics=diagnostics, omnibus_tests=omnibus_tests, follow_up_tests=follow_up_tests,
        contrasts=contrasts, significance_letters=significance_letters, estimated_marginal_means=emmeans_all, simple_effects=simple_effects,
        warnings=warnings, report_constraints=list(method.report_constraints),
        data_snapshot={
            "n_total": len(df_clean), "design": " × ".join(factors), "factor_count": len(factors),
            "selected_multivariate_tests": selected_keys, "primary_multivariate_test": primary_key,
            "selected_multivariate_test_labels": selected_labels,
            "follow_up_mode": follow_up_mode, "follow_up_ss_type": follow_up_ss_type,
            "follow_up_correction": follow_up_correction, "posthoc_methods": posthoc_methods,
            "simple_effect_correction": simple_effect_correction, "posthoc_scope": posthoc_scope,
            "estimate_marginal_means": estimate_marginal_means, "emm_factors": requested_emm_factors,
            "contrast_correction": contrast_correction, "diagnostic_plots_requested": diagnostic_plots,
            "box_m_alpha": box_m_alpha,
            "model_rank": model_rank,
            "model_columns": model_columns,
            "outcome_correlation_matrix": correlation.round(6).to_dict(),
            "max_abs_outcome_correlation": max_abs_correlation,
            "outcome_matrix_condition_number": condition_number,
            "outcome_matrix_rank": outcome_rank,
        },
        descriptive_stats=_manova_descriptive_stats(df_clean, outcomes, factors),
    )


def _box_m_test(
    df: pd.DataFrame,
    outcomes: list[str],
    factors: list[str],
    alpha: float,
) -> tuple[DiagnosticResult | None, str]:
    """Box's M 协方差齐性近似检验（按完整因素单元分组）。"""
    p = len(outcomes)
    grouped = list(df.groupby(factors, observed=True, dropna=True))
    g = len(grouped)
    if g < 2:
        return None, "Box's M 至少需要两个设计单元，已跳过。"
    covariances: list[np.ndarray] = []
    sizes: list[int] = []
    pooled_numerator = np.zeros((p, p), dtype=float)
    for key, subset in grouped:
        values = subset[outcomes].to_numpy(dtype=float)
        n_i = len(values)
        if n_i <= p:
            return None, f"Box's M 未计算：设计单元 {key!r} 仅 {n_i} 个观测，不足以稳定估计 {p} 维协方差矩阵。"
        covariance = np.cov(values, rowvar=False, ddof=1)
        sign, logdet = np.linalg.slogdet(covariance)
        if sign <= 0 or not np.isfinite(logdet):
            return None, f"Box's M 未计算：设计单元 {key!r} 的协方差矩阵奇异或非正定。"
        covariances.append(covariance)
        sizes.append(n_i)
        pooled_numerator += (n_i - 1) * covariance
    total = sum(sizes)
    pooled_df = total - g
    pooled = pooled_numerator / pooled_df
    sign_pool, logdet_pool = np.linalg.slogdet(pooled)
    if sign_pool <= 0 or not np.isfinite(logdet_pool):
        return None, "Box's M 未计算：合并协方差矩阵奇异或非正定。"
    m_stat = pooled_df * logdet_pool - sum((n_i - 1) * np.linalg.slogdet(cov)[1] for n_i, cov in zip(sizes, covariances))
    correction = ((2 * p**2 + 3 * p - 1) / (6 * (p + 1) * (g - 1))) * (
        sum(1 / (n_i - 1) for n_i in sizes) - 1 / pooled_df
    )
    chi_square = float(max(0.0, (1 - correction) * m_stat))
    df_chi = float((g - 1) * p * (p + 1) / 2)
    p_value = float(scipy_stats.chi2.sf(chi_square, df_chi))
    return DiagnosticResult(
        test_name="Box's M 协方差齐性检验", statistic=chi_square, p_value=p_value,
        passed=bool(p_value >= alpha),
        detail=("未发现显著协方差矩阵差异。" if p_value >= alpha else
                "设计单元协方差矩阵可能不齐；优先解释 Pillai 轨迹并谨慎报告。") +
               " Box's M 对非正态较敏感，应与样本量和其他诊断共同判断。",
    ), ""


def _bartlett_sphericity_test(
    values: pd.DataFrame, alpha: float, *, residual_based: bool = False
) -> DiagnosticResult | None:
    matrix = values.dropna().to_numpy(dtype=float)
    n, p = matrix.shape
    if n <= p or p < 2:
        return None
    correlation = np.corrcoef(matrix, rowvar=False)
    sign, logdet = np.linalg.slogdet(correlation)
    if sign <= 0 or not np.isfinite(logdet):
        return DiagnosticResult(
            test_name=("Bartlett 残差相关矩阵球形检验" if residual_based else "Bartlett 相关矩阵球形检验"), statistic=0.0, p_value=0.0, passed=False,
            detail="相关矩阵奇异，因变量可能存在完全或近完全线性依赖。",
        )
    chi_square = float(-(n - 1 - (2 * p + 5) / 6) * logdet)
    df_chi = float(p * (p - 1) / 2)
    p_value = float(scipy_stats.chi2.sf(chi_square, df_chi))
    # 此处“通过”表示变量间存在足够相关结构，不是传统假设未拒绝。
    return DiagnosticResult(
        test_name=("Bartlett 残差相关矩阵球形检验" if residual_based else "Bartlett 相关矩阵球形检验"), statistic=chi_square, p_value=p_value,
        passed=bool(p_value < alpha),
        detail=("相关矩阵显著偏离单位阵，多个因变量具有联合分析的信息基础。" if p_value < alpha else
                "未能证明因变量之间存在足够相关结构；逐变量模型可能更容易解释。") +
               (" 该结果基于完整析因模型残差；该检验不是 MANOVA 必需假设。" if residual_based else " 该检验不是 MANOVA 必需假设。"),
    )


def _mardia_diagnostics(residuals: np.ndarray, alpha: float) -> list[DiagnosticResult]:
    residuals = np.asarray(residuals, dtype=float)
    residuals = residuals[np.all(np.isfinite(residuals), axis=1)]
    n, p = residuals.shape
    if n <= p + 2:
        return []
    centered = residuals - residuals.mean(axis=0)
    covariance = np.cov(centered, rowvar=False, ddof=1)
    inverse = np.linalg.pinv(covariance)
    cross = centered @ inverse @ centered.T
    b1p = float(np.sum(cross**3) / (n**2))
    skew_chi = float(n * b1p / 6)
    skew_df = float(p * (p + 1) * (p + 2) / 6)
    skew_p = float(scipy_stats.chi2.sf(skew_chi, skew_df))
    distances = np.einsum("ij,jk,ik->i", centered, inverse, centered)
    b2p = float(np.mean(distances**2))
    expected = p * (p + 2)
    z = float((b2p - expected) / np.sqrt(8 * p * (p + 2) / n))
    kurt_p = float(2 * scipy_stats.norm.sf(abs(z)))
    return [
        DiagnosticResult(
            test_name="Mardia 多元偏度（残差近似）", statistic=skew_chi, p_value=skew_p,
            passed=bool(skew_p >= alpha),
            detail="基于完整析因模型残差的近似诊断；小样本时检验力和校准有限。",
        ),
        DiagnosticResult(
            test_name="Mardia 多元峰度（残差近似）", statistic=z, p_value=kurt_p,
            passed=bool(kurt_p >= alpha),
            detail=f"Mardia 峰度={b2p:.4f}，正态期望={expected:.4f}；基于模型残差近似。",
        ),
    ]

def _safe_multivariate_results(model: SM_MANOVA) -> dict[str, dict[str, object]]:
    """按公式项逐项计算多元统计量，并安全处理数值上为零的效应。

    statsmodels 的 ``mv_test`` 在某个效应所有特征根均低于容差时，Roy 最大根
    会对空数组取最大值并使整个 MANOVA 失败。这里使用同一组统计公式逐项计算，
    将这种精确零效应正确返回为统计量 0、F=0、p=1，而不是让其他效应一并丢失。
    """
    if not hasattr(model, "data") or not hasattr(model.data, "design_info"):
        raise ValueError("MANOVA 公式设计信息不可用")

    params, df_resid, inv_cov, residual_sscp = model._fittedmod
    terms = model.data.design_info.term_name_slices
    results: dict[str, dict[str, object]] = {}
    identity = np.eye(model.exog.shape[1])

    for term_name, term_slice in terms.items():
        if term_name == "Intercept":
            continue
        contrast = identity[term_slice, :]
        transformed = np.eye(model.endog.shape[1])
        hypothesis_delta = contrast.dot(params).dot(transformed)
        contrast_cov = contrast.dot(inv_cov).dot(contrast.T)
        q = int(np.linalg.matrix_rank(contrast_cov))
        if q == 0:
            raise np.linalg.LinAlgError(f"{term_name} 的对比矩阵秩为 0")
        hypothesis_sscp = hypothesis_delta.T.dot(np.linalg.pinv(contrast_cov)).dot(hypothesis_delta)
        error_sscp = transformed.T.dot(residual_sscp).dot(transformed)
        total_sscp = error_sscp + hypothesis_sscp
        p = int(np.linalg.matrix_rank(total_sscp))
        if p == 0:
            raise np.linalg.LinAlgError(f"{term_name} 的误差与假设矩阵均为零")

        eigenvalues = np.linalg.eigvals(np.linalg.solve(total_sscp, hypothesis_sscp))
        eigenvalues = np.real_if_close(eigenvalues, tol=1000)
        if np.iscomplexobj(eigenvalues):
            raise np.linalg.LinAlgError(f"{term_name} 的特征根包含不可忽略的复数部分")
        eigenvalues = np.asarray(eigenvalues, dtype=float)
        # 理论范围为 [0, 1)，仅消除浮点误差造成的极小负值或略超 1。
        eigenvalues = np.clip(eigenvalues, 0.0, 1.0 - np.finfo(float).eps)
        results[term_name] = {
            "stat": _multivariate_stat_table(eigenvalues, p, q, float(df_resid)),
            "contrast_L": contrast,
            "transform_M": transformed,
            "E": error_sscp,
            "H": hypothesis_sscp,
        }
    return results


def _multivariate_stat_table(
    eigenvalues: np.ndarray,
    p: int,
    q: int,
    df_resid: float,
    tolerance: float = 1e-8,
) -> pd.DataFrame:
    """复现 statsmodels 的四种 MANOVA 近似检验，并允许全部特征根为零。"""
    positive = np.asarray(eigenvalues, dtype=float)
    positive = positive[positive > tolerance]
    roots = positive / (1.0 - positive) if positive.size else np.array([], dtype=float)

    v = float(df_resid)
    s = float(min(p, q))
    m = (abs(p - q) - 1.0) / 2.0
    n = (v - p - 1.0) / 2.0

    columns = ["Value", "Num DF", "Den DF", "F Value", "Pr > F"]
    index = [item[0] for item in _MULTIVARIATE_STATISTICS.values()]
    table = pd.DataFrame(index=index, columns=columns, dtype=float)

    wilks = float(np.prod(1.0 - positive)) if positive.size else 1.0
    pillai = float(positive.sum()) if positive.size else 0.0
    hotelling = float(roots.sum()) if roots.size else 0.0
    roy = float(roots.max()) if roots.size else 0.0

    table.loc["Wilks' lambda", "Value"] = wilks
    table.loc["Pillai's trace", "Value"] = pillai
    table.loc["Hotelling-Lawley trace", "Value"] = hotelling
    table.loc["Roy's greatest root", "Value"] = roy

    # Wilks' Lambda
    r = v - (p - q + 1.0) / 2.0
    u = (p * q - 2.0) / 4.0
    df1 = float(p * q)
    if p * p + q * q - 5 > 0:
        t = float(np.sqrt((p * p * q * q - 4.0) / (p * p + q * q - 5.0)))
    else:
        t = 1.0
    df2 = float(r * t - 2.0 * u)
    lambda_power = wilks ** (1.0 / t)
    f_value = 0.0 if np.isclose(lambda_power, 1.0) else float((1.0 - lambda_power) / lambda_power * df2 / df1)
    _fill_multivariate_row(table, "Wilks' lambda", df1, df2, f_value)

    # Pillai's trace
    df1 = float(s * (2.0 * m + s + 1.0))
    df2 = float(s * (2.0 * n + s + 1.0))
    denominator = s - pillai
    f_value = 0.0 if np.isclose(pillai, 0.0) else float(df2 / df1 * pillai / denominator)
    _fill_multivariate_row(table, "Pillai's trace", df1, df2, f_value)

    # Hotelling–Lawley trace
    if n > 0:
        df1 = float(p * q)
        if np.isclose(n, 1.0):
            # statsmodels 原公式在 n=1 时出现除零；取 n→1 的极限。
            df2 = 4.0
            c = 1.0
        else:
            b = (p + 2.0 * n) * (q + 2.0 * n) / (2.0 * (2.0 * n + 1.0) * (n - 1.0))
            df2 = float(4.0 + (p * q + 2.0) / (b - 1.0))
            c = (df2 - 2.0) / (2.0 * n)
        f_value = 0.0 if np.isclose(hotelling, 0.0) else float(df2 / df1 * hotelling / c)
    else:
        df1 = float(s * (2.0 * m + s + 1.0))
        df2 = float(s * (s * n + 1.0))
        f_value = 0.0 if np.isclose(hotelling, 0.0) else float(df2 / df1 / s * hotelling)
    _fill_multivariate_row(table, "Hotelling-Lawley trace", df1, df2, f_value)

    # Roy's greatest root
    r_roy = float(max(p, q))
    df1 = r_roy
    df2 = float(v - r_roy + q)
    f_value = 0.0 if np.isclose(roy, 0.0) else float(df2 / df1 * roy)
    _fill_multivariate_row(table, "Roy's greatest root", df1, df2, f_value)
    return table


def _fill_multivariate_row(
    table: pd.DataFrame,
    row_name: str,
    df_num: float,
    df_den: float,
    f_value: float,
) -> None:
    if df_num <= 0 or df_den <= 0 or not np.isfinite(f_value):
        raise ValueError(f"{row_name} 的自由度或 F 值无效")
    table.loc[row_name, "Num DF"] = df_num
    table.loc[row_name, "Den DF"] = df_den
    table.loc[row_name, "F Value"] = f_value
    table.loc[row_name, "Pr > F"] = float(scipy_stats.f.sf(f_value, df_num, df_den))


def _selected_statistics(parameters: Mapping[str, object] | None) -> list[str]:
    raw = str((parameters or {}).get("multivariate_test", "all")).strip().lower()
    raw = _STATISTIC_ALIASES.get(raw, raw)
    if raw == "all":
        return list(_MULTIVARIATE_STATISTICS)
    if raw not in _MULTIVARIATE_STATISTICS:
        raise ValueError(f"未知 MANOVA 多元检验统计量: {raw}")
    return [raw]


def _display_effect(raw_effect: str, reverse_map: Mapping[str, str]) -> str:
    display = raw_effect
    for safe, original in reverse_map.items():
        display = display.replace(f"C({safe}, Sum)", original)
        display = display.replace(f"C({safe})", original)
        display = re.sub(rf"\b{re.escape(safe)}\b", lambda _: original, display)
    return display.replace(":", " × ")


def _manova_descriptive_stats(
    df: pd.DataFrame,
    dv_cols: list[str],
    between_cols: list[str],
) -> list[dict[str, object]]:
    groups = df.groupby(between_cols, dropna=True, observed=False)
    rows: list[dict[str, object]] = []
    for group_key, subset in groups:
        keys = group_key if isinstance(group_key, tuple) else (group_key,)
        row: dict[str, object] = {name: value for name, value in zip(between_cols, keys)}
        row["n"] = len(subset)
        for outcome in dv_cols:
            row[f"{outcome}_mean"] = round(float(subset[outcome].mean()), 4)
            row[f"{outcome}_sd"] = round(float(subset[outcome].std()), 4)
        rows.append(row)
    return rows
