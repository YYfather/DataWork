"""ANCOVA、重复测量和经典混合设计方法。"""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.anova import AnovaRM, anova_lm
from statsmodels.stats.multitest import multipletests

from .common import design_info, safe_paired_ttest, safe_standardized_statistic, significance
from .model_support import (
    apply_posthoc_methods_to_emm,
    estimated_marginal_means,
    interaction_plot,
    regression_diagnostic_plots,
    sphericity_adjustments,
    sphericity_result,
)
from .regression_methods import categorical, predictor_terms, quote
from .result import (
    CoefficientResult,
    ContrastResult,
    DiagnosticResult,
    DiagnosticPlot,
    EffectSize,
    EMMeans,
    FitStatistic,
    MethodInfo,
    OmnibusTest,
    PrimaryTestResult,
    StatisticalResult,
)


def ancova(
    df: pd.DataFrame,
    dv: str,
    fixed_factors: list[str],
    covariates: list[str],
    alpha: float,
    ss_type: int,
    *,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    required = [dv] + fixed_factors + covariates
    clean = df[required].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    if len(clean) < max(12, len(required) * 3):
        raise ValueError("ANCOVA 完整案例不足")
    terms = predictor_terms(fixed_factors, covariates, sum_contrast=ss_type == 3)
    formula = f"{quote(dv)} ~ " + " + ".join(terms)
    model = smf.ols(formula, data=clean).fit()
    table = anova_lm(model, typ=ss_type)
    residual_ss = float(table.loc["Residual", "sum_sq"])
    residual_df = float(table.loc["Residual", "df"])
    total_ss = float(np.sum((clean[dv] - clean[dv].mean()) ** 2))
    omnibus: list[OmnibusTest] = []
    for effect, row in table.drop(index="Residual").iterrows():
        if str(effect) == "Intercept":
            continue
        ss = float(row["sum_sq"])
        f_value = float(row["F"])
        p = float(row["PR(>F)"])
        partial_eta = ss / (ss + residual_ss) if ss + residual_ss > 0 else 0.0
        omnibus.append(OmnibusTest(
            effect=str(effect), ss_type=ss_type, df_num=float(row["df"]), df_den=residual_df,
            f_value=f_value, p_value=p, eta_sq=ss / total_ss if total_ss > 0 else 0.0,
            eta_sq_p=partial_eta, is_significant=significance(p, alpha), significance_level=alpha,
        ))
    ci = model.conf_int(alpha=alpha)
    coefficients = [CoefficientResult(
        term=str(term), estimate=float(model.params[term]), se=float(model.bse[term]), statistic_name="t",
        statistic_value=float(model.tvalues[term]), p_value=float(model.pvalues[term]),
        ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]), significant=significance(float(model.pvalues[term]), alpha),
    ) for term in model.params.index]
    warnings: list[str] = []
    interaction_terms = [f"{categorical(factor, sum_contrast=ss_type == 3)}:{quote(covariate)}" for factor in fixed_factors for covariate in covariates]
    if interaction_terms:
        slope_formula = formula + " + " + " + ".join(interaction_terms)
        try:
            slope_model = smf.ols(slope_formula, data=clean).fit()
            slope_table = anova_lm(model, slope_model)
            slope_p = float(slope_table.iloc[-1]["Pr(>F)"])
            if np.isfinite(slope_p) and slope_p < alpha:
                warnings.append(f"组别×协变量交互检验显著 (p={slope_p:.4g})，回归斜率同质性可能不满足。")
        except (ValueError, np.linalg.LinAlgError) as exc:
            warnings.append(f"无法稳定完成回归斜率同质性辅助检验：{exc}")
    emmeans: list[EMMeans] = []
    contrasts: list[ContrastResult] = []
    significance_letters = []
    posthoc_warnings: list[str] = []
    if emm_factors:
        emmeans, contrasts = estimated_marginal_means(
            model, clean, target_factors=emm_factors, categorical_factors=fixed_factors,
            covariates=covariates, alpha=alpha, correction=contrast_correction,
            df_resid=float(model.df_resid),
        )
    plots = []
    if diagnostic_plots:
        influence = model.get_influence()
        plots = regression_diagnostic_plots(
            model.fittedvalues, model.resid,
            leverage=influence.hat_matrix_diag,
            cooks_distance=influence.cooks_distance[0],
        )
    return StatisticalResult(
        analysis_id=f"ancova_{dv}",
        design=design_info(clean, dependent=[dv], fixed=fixed_factors, covariates=covariates),
        method=MethodInfo(name="ancova", label_zh="协方差分析（ANCOVA）", formula=formula),
        omnibus_tests=omnibus, coefficients=coefficients,
        estimated_marginal_means=emmeans, contrasts=contrasts,
        fit_statistics=[FitStatistic(name="R-squared", value=float(model.rsquared)), FitStatistic(name="Adjusted R-squared", value=float(model.rsquared_adj)), FitStatistic(name="AIC", value=float(model.aic))],
        effect_sizes=[EffectSize(measure=f"partial eta squared: {item.effect}", value=item.eta_sq_p) for item in omnibus],
        warnings=warnings, diagnostic_plots=plots,
        data_snapshot={"n": int(model.nobs), "ss_type": ss_type},
    )


def _paired_level_contrasts(wide: pd.DataFrame, alpha: float, correction: str) -> list[ContrastResult]:
    """重复水平的配对比较，并使区间标签与多重校正规则一致。"""
    rows: list[tuple[str, float, float, float, float]] = []
    p_values: list[float] = []
    for left, right in combinations(wide.columns, 2):
        difference = wide[left].to_numpy(dtype=float) - wide[right].to_numpy(dtype=float)
        n = len(difference)
        estimate = float(np.mean(difference))
        se = float(np.std(difference, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        statistic, p_value = safe_paired_ttest(wide[left], wide[right])
        rows.append((f"{left} - {right}", estimate, se, float(statistic), float(p_value)))
        p_values.append(float(p_value))

    adjusted = np.asarray(p_values, dtype=float)
    normalized = str(correction).lower().replace("-", "_")
    if len(adjusted) and normalized != "none":
        adjusted = multipletests(adjusted, alpha=alpha, method=normalized)[1]
    m = max(len(rows), 1)
    if normalized in {"holm", "bonferroni"}:
        interval_alpha = alpha / m
        label = "Holm（CI 使用 Bonferroni 同步区间）" if normalized == "holm" else "Bonferroni"
    elif normalized == "sidak":
        interval_alpha = 1 - (1 - alpha) ** (1 / m)
        label = "Šidák"
    elif normalized == "fdr_bh":
        interval_alpha = alpha
        label = "Benjamini–Hochberg FDR（CI 未作同步校正）"
    else:
        interval_alpha = alpha
        label = "未校正"
    df = float(len(wide) - 1)
    critical = float(stats.t.ppf(1 - interval_alpha / 2, df)) if df > 0 else 0.0
    return [ContrastResult(
        contrast=row[0], estimate=row[1], se=row[2], t_value=row[3], p_value=row[4],
        p_adjusted=float(adjusted[index]), ci_lower=row[1] - critical * row[2],
        ci_upper=row[1] + critical * row[2], df=df,
        significant=bool(adjusted[index] < alpha), correction=label,
    ) for index, row in enumerate(rows)]


def repeated_measures_anova(
    df: pd.DataFrame,
    dv: str,
    subject_id: str,
    repeated_factor: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
    *,
    estimate_emm: bool = True,
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    parameters = parameters or {}
    clean = df[[dv, subject_id, repeated_factor]].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna()
    duplicate_count = int(clean.duplicated([subject_id, repeated_factor]).sum())
    if duplicate_count:
        raise ValueError(f"每个受试者×重复水平必须只有一条观测，发现 {duplicate_count} 条重复")
    levels = list(pd.unique(clean[repeated_factor]))
    if len(levels) < 2:
        raise ValueError("重复因素至少需要 2 个水平")
    wide = clean.pivot(index=subject_id, columns=repeated_factor, values=dv).reindex(columns=levels)
    if wide.isna().any().any():
        incomplete = int(wide.isna().any(axis=1).sum())
        raise ValueError(f"重复测量 ANOVA 要求完整数据；有 {incomplete} 个对象缺少重复水平")
    fit = AnovaRM(clean, depvar=dv, subject=subject_id, within=[repeated_factor]).fit()
    row = fit.anova_table.iloc[0]
    f_value = float(row["F Value"])
    df_num = float(row["Num DF"])
    df_den = float(row["Den DF"])
    p = float(row["Pr > F"])
    partial_eta = (f_value * df_num) / (f_value * df_num + df_den) if f_value * df_num + df_den > 0 else 0.0
    sph = sphericity_result(wide, alpha)
    adjustments = sphericity_adjustments(f_value, df_num, df_den, sph, alpha)
    omnibus = OmnibusTest(
        effect=repeated_factor, df_num=df_num, df_den=df_den, f_value=f_value, p_value=p,
        eta_sq=partial_eta, eta_sq_p=partial_eta, is_significant=significance(p, alpha),
        significance_level=alpha, adjustments=adjustments,
    )
    pairwise_correction = str(parameters.get("pairwise_correction", "holm"))
    contrasts = _paired_level_contrasts(wide, alpha, pairwise_correction)
    desc = clean.groupby(repeated_factor, observed=True)[dv].agg(["count", "mean", "std"]).reset_index().rename(columns={"count": "n", "std": "sd"}).to_dict("records")
    emmeans: list[EMMeans] = []
    if estimate_emm:
        for level in levels:
            values = wide[level].to_numpy(dtype=float)
            mean = float(np.mean(values))
            se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
            critical = float(stats.t.ppf(1 - alpha / 2, len(values) - 1))
            emmeans.append(EMMeans(group=f"{repeated_factor}={level}", levels={repeated_factor: str(level)}, mean=mean, se=se, ci_lower=mean-critical*se, ci_upper=mean+critical*se, df=float(len(values)-1), source="repeated-level mean"))
    subject_means = clean.groupby(subject_id, observed=True)[dv].transform("mean")
    level_means = clean.groupby(repeated_factor, observed=True)[dv].transform("mean")
    fitted = subject_means + level_means - float(clean[dv].mean())
    plots = regression_diagnostic_plots(fitted, clean[dv] - fitted) if diagnostic_plots else []
    plots.append(DiagnosticPlot(
        kind="line", title=f"重复水平均值图：{repeated_factor}", x_label=repeated_factor, y_label=f"{dv} 均值",
        series=[{"name": dv, "x": [str(level) for level in levels], "y": [float(wide[level].mean()) for level in levels], "error": [float(wide[level].std(ddof=1)/np.sqrt(len(wide))) for level in levels]}],
    ))
    warnings: list[str] = []
    correction_mode = str(parameters.get("sphericity_correction", "auto"))
    if sph and not sph.passed:
        warnings.append("Mauchly 检验提示球形性可能不满足；请优先解释校正后的自由度与 p 值。")
    if correction_mode != "none" and adjustments:
        chosen = "Greenhouse–Geisser" if correction_mode in {"auto", "greenhouse_geisser"} else "Huynh–Feldt"
        selected = next(item for item in adjustments if item.correction == chosen)
        warnings.append(f"当前计划选择 {chosen} 结果：F({selected.df_num:.3f}, {selected.df_den:.3f})，p={selected.p_value:.6g}。")
    return StatisticalResult(
        analysis_id=f"repeated_anova_{dv}",
        design=design_info(clean, dependent=[dv], subject_id=subject_id, repeated_factor=repeated_factor),
        method=MethodInfo(name="repeated_measures_anova", label_zh="单因素重复测量 ANOVA", formula=f"{dv} ~ {repeated_factor} + Error({subject_id}/{repeated_factor})"),
        omnibus_tests=[omnibus], sphericity=sph,
        effect_sizes=[EffectSize(measure="partial eta squared", value=partial_eta)],
        estimated_marginal_means=emmeans, contrasts=contrasts,
        descriptive_stats=desc, warnings=warnings, diagnostic_plots=plots,
        data_snapshot={"n_subjects": int(len(wide)), "levels": [str(value) for value in levels], "sphericity_correction": correction_mode},
    )


def mixed_anova(
    df: pd.DataFrame,
    dv: str,
    subject_id: str,
    repeated_factor: str,
    between_factors: str | list[str],
    alpha: float,
    parameters: dict[str, Any] | None = None,
    *,
    estimate_emm: bool = True,
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    """混合设计统一入口。

    完整平衡的一个对象间因素设计默认使用经典裂区 ANOVA；存在缺失、
    组间不平衡或两个对象间因素时，自动使用以对象为随机截距的线性混合模型。
    """
    parameters = parameters or {}
    factors = [between_factors] if isinstance(between_factors, str) else list(between_factors)
    factors = list(dict.fromkeys(factors))
    if not 1 <= len(factors) <= 2:
        raise ValueError("混合设计需要 1–2 个对象间因素")
    required = [dv, subject_id, repeated_factor, *factors]
    clean = df[required].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna(subset=[dv, subject_id, repeated_factor, *factors])
    if clean.empty:
        raise ValueError("混合设计没有可用完整观测")
    if clean.duplicated([subject_id, repeated_factor]).any():
        duplicate_count = int(clean.duplicated([subject_id, repeated_factor]).sum())
        raise ValueError(f"每个对象×重复水平必须只有一条观测，发现 {duplicate_count} 条重复")
    for factor in factors:
        memberships = clean.groupby(subject_id, observed=True)[factor].nunique()
        if (memberships != 1).any():
            raise ValueError(f"每个对象必须只属于对象间因素 {factor!r} 的一个水平")
    if clean[repeated_factor].nunique() < 2:
        raise ValueError("对象内重复因素至少需要 2 个水平")
    for factor in factors:
        if clean[factor].nunique() < 2:
            raise ValueError(f"对象间因素 {factor!r} 至少需要 2 个水平")

    mode = str(parameters.get("analysis_mode", "auto")).lower()
    if mode not in {"auto", "classical", "mixedlm"}:
        raise ValueError("analysis_mode 必须为 auto、classical 或 mixedlm")
    classical_ok, reason = _classical_mixed_suitability(
        clean, subject_id, repeated_factor, factors
    )
    if mode == "classical" and not classical_ok:
        raise ValueError(f"当前数据不满足经典平衡混合 ANOVA：{reason}")
    if mode != "mixedlm" and classical_ok:
        result = _classical_mixed_anova(
            clean, dv, subject_id, repeated_factor, factors[0], alpha, parameters,
            estimate_emm=estimate_emm, diagnostic_plots=diagnostic_plots,
        )
        result.data_snapshot["analysis_mode"] = "classical"
        result.provenance["selection_reason"] = "完整、平衡、单一对象间因素"
        return result

    result = _mixed_anova_lmm(
        clean, dv, subject_id, repeated_factor, factors, alpha, parameters,
        estimate_emm=estimate_emm, diagnostic_plots=diagnostic_plots,
    )
    if mode == "auto":
        result.warnings.insert(0, f"经典平衡混合 ANOVA 不适用（{reason}），已自动使用线性混合效应模型。")
        result.provenance["selection_reason"] = reason
    return result


def _classical_mixed_suitability(
    clean: pd.DataFrame, subject_id: str, repeated_factor: str, factors: list[str]
) -> tuple[bool, str]:
    if len(factors) != 1:
        return False, "经典实现仅支持一个对象间因素"
    levels = list(pd.unique(clean[repeated_factor]))
    wide = clean.pivot(index=subject_id, columns=repeated_factor, values=clean.columns[0]).reindex(columns=levels)
    if wide.isna().any().any():
        return False, "部分对象缺少重复水平"
    factor = factors[0]
    group_by_subject = clean.drop_duplicates(subject_id).set_index(subject_id)[factor].reindex(wide.index)
    counts = group_by_subject.value_counts()
    if counts.nunique() != 1:
        return False, "对象间组样本数不平衡"
    if int(counts.min()) < 2:
        return False, "部分对象间组少于 2 个对象"
    return True, "满足经典平衡设计"


def _clean_mixed_term(term: str, factors: list[str]) -> str:
    import re
    clean = str(term)
    for factor in factors:
        clean = re.sub(rf"C\(Q\('{re.escape(factor)}'\),\s*Sum\)", factor, clean)
    return clean.replace(":", " × ").replace("Intercept", "截距").strip()


def _mixed_anova_lmm(
    clean: pd.DataFrame,
    dv: str,
    subject_id: str,
    repeated_factor: str,
    between_factors: list[str],
    alpha: float,
    parameters: dict[str, Any],
    *,
    estimate_emm: bool,
    diagnostic_plots: bool,
) -> StatisticalResult:
    categorical_factors = [*between_factors, repeated_factor]
    for column in categorical_factors:
        clean[column] = clean[column].astype("category")
    fixed_terms = [categorical(column, sum_contrast=True) for column in categorical_factors]
    formula = f"{quote(dv)} ~ " + " * ".join(fixed_terms)
    random_slope = bool(parameters.get("random_slope_repeated", False))
    re_formula = f"~{categorical(repeated_factor, sum_contrast=True)}" if random_slope else "1"
    optimizer = str(parameters.get("optimizer", "auto"))
    optimizers = [optimizer] if optimizer != "auto" else ["lbfgs", "powell", "cg"]
    maxiter = int(parameters.get("max_iterations", 500))
    reml = bool(parameters.get("reml", False))
    fitted_model = None
    failures: list[str] = []
    for method in optimizers:
        try:
            candidate = smf.mixedlm(
                formula, clean, groups=clean[subject_id], re_formula=re_formula
            ).fit(reml=reml, method=method, maxiter=maxiter, disp=False)
            fitted_model = candidate
            if bool(getattr(candidate, "converged", True)):
                break
            failures.append(f"{method}: 未收敛")
        except Exception as exc:  # statsmodels 可能抛出多种线性代数/优化异常
            failures.append(f"{method}: {exc}")
    if fitted_model is None:
        raise RuntimeError("线性混合模型拟合失败；" + "；".join(failures))

    fe_names = list(fitted_model.fe_params.index)
    fe_params = fitted_model.fe_params
    fixed_cov = fitted_model.cov_params().loc[fe_names, fe_names]
    design_info_obj = fitted_model.model.data.design_info
    primary: list[PrimaryTestResult] = []
    for term, slc in design_info_obj.term_name_slices.items():
        if term == "Intercept":
            continue
        indices = np.arange(slc.start, min(slc.stop, len(fe_names)))
        if len(indices) == 0:
            continue
        beta = fe_params.to_numpy(dtype=float)[indices]
        covariance = fixed_cov.to_numpy(dtype=float)[np.ix_(indices, indices)]
        rank = int(np.linalg.matrix_rank(covariance))
        if rank == 0:
            statistic, p_value = 0.0, 1.0
        else:
            statistic = float(beta @ np.linalg.pinv(covariance) @ beta)
            p_value = float(stats.chi2.sf(statistic, rank))
        primary.append(PrimaryTestResult(
            effect=_clean_mixed_term(term, categorical_factors),
            statistic_name="Wald chi-square", statistic_value=statistic, p_value=p_value,
            df_num=float(rank), is_significant=bool(p_value < alpha), significance_level=alpha,
            detail="线性混合模型固定效应联合 Wald 检验（渐近近似）",
        ))

    ci = fitted_model.conf_int(alpha=alpha)
    coefficients: list[CoefficientResult] = []
    for term in fe_names:
        p_value = float(fitted_model.pvalues.get(term, np.nan))
        coefficients.append(CoefficientResult(
            term=_clean_mixed_term(term, categorical_factors),
            estimate=float(fe_params[term]), se=float(fitted_model.bse_fe[term]),
            statistic_name="z", statistic_value=safe_standardized_statistic(float(fe_params[term]), float(fitted_model.bse_fe[term])),
            p_value=p_value if np.isfinite(p_value) else 1.0,
            ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]),
            significant=bool(np.isfinite(p_value) and p_value < alpha),
        ))

    emmeans: list[EMMeans] = []
    contrasts: list[ContrastResult] = []
    significance_letters = []
    posthoc_warnings: list[str] = []
    if estimate_emm:
        scope = str(parameters.get("emm_scope", "cells"))
        if scope == "within":
            targets = [repeated_factor]
        elif scope == "between":
            targets = between_factors
        else:
            targets = categorical_factors
        emmeans, raw = estimated_marginal_means(
            fitted_model, clean, target_factors=targets, categorical_factors=categorical_factors,
            covariates=[], alpha=alpha, correction="none", fixed_params=fe_params,
            fixed_cov=fixed_cov, normal_approximation=True,
        )
        pairwise_methods = parameters.get("posthoc_methods", [parameters.get("pairwise_correction", "holm")])
        contrasts, significance_letters, posthoc_warnings = apply_posthoc_methods_to_emm(
            emmeans, raw, methods=pairwise_methods, alpha=alpha,
            factor=" × ".join(targets), outcome=dv,
            control_group=str(parameters.get("control_group", "")).strip() or None,
        )

    plots = regression_diagnostic_plots(
        fitted_model.fittedvalues, fitted_model.resid
    ) if diagnostic_plots else []
    if between_factors:
        plots.append(interaction_plot(clean, dv, between_factors[0], repeated_factor))
    residuals = np.asarray(fitted_model.resid, dtype=float)
    shapiro_stat, shapiro_p = stats.shapiro(residuals) if 3 <= len(residuals) <= 5000 else (0.0, 1.0)
    diagnostics = [DiagnosticResult(
        test_name="Shapiro–Wilk（条件残差）", statistic=float(shapiro_stat),
        p_value=float(shapiro_p), passed=bool(shapiro_p >= alpha),
        detail="用于检查条件残差近似正态；大样本时应结合 Q-Q 图判断。",
    )]
    warnings = [*failures, *posthoc_warnings]
    if not bool(getattr(fitted_model, "converged", True)):
        warnings.append("线性混合模型未完全收敛，参数与显著性检验仅供诊断，需调整随机结构或优化器。")
    if random_slope:
        warnings.append("已为重复因素拟合随机斜率；请结合收敛状态和随机效应协方差判断模型是否过度复杂。")
    posthoc_methods = parameters.get("posthoc_methods", [parameters.get("pairwise_correction", "holm")])
    if isinstance(posthoc_methods, str):
        posthoc_methods = [posthoc_methods]
    if set(posthoc_methods) & {"duncan", "lsd"}:
        warnings.append("Duncan/LSD 属于较宽松的事后比较，可能提高第一类错误率。")
    random_variance = float(np.asarray(fitted_model.cov_re)[0, 0]) if np.asarray(fitted_model.cov_re).size else 0.0
    fit_statistics = [
        FitStatistic(name="Log-likelihood", value=float(fitted_model.llf)),
        FitStatistic(name="Subject random-intercept variance", value=random_variance),
        FitStatistic(name="Residual variance", value=float(fitted_model.scale)),
    ]
    if np.isfinite(fitted_model.aic):
        fit_statistics.insert(0, FitStatistic(name="AIC", value=float(fitted_model.aic), detail="ML 模型比较指标"))
    if np.isfinite(fitted_model.bic):
        position = 1 if fit_statistics and fit_statistics[0].name == "AIC" else 0
        fit_statistics.insert(position, FitStatistic(name="BIC", value=float(fitted_model.bic), detail="ML 模型比较指标"))
    if reml and not (np.isfinite(fitted_model.aic) and np.isfinite(fitted_model.bic)):
        warnings.append("REML 拟合不使用 AIC/BIC 比较固定效应；如需比较固定效应结构，请改用 ML 并保持随机结构一致。")
    random_label = f"({re_formula}|{subject_id})"
    return StatisticalResult(
        analysis_id=f"mixed_anova_lmm_{dv}",
        design=design_info(clean, dependent=[dv], fixed=between_factors, subject_id=subject_id, repeated_factor=repeated_factor),
        method=MethodInfo(
            name="mixed_anova", label_zh="广义混合设计（线性混合效应模型）",
            formula=formula + f" + {random_label}",
            report_constraints=[
                "固定效应采用渐近 Wald 卡方检验，不应与经典平衡 ANOVA 的有限样本 F 检验混为一谈。",
                "模型允许不平衡与部分缺失，但缺失机制仍需合理，且对象内协方差结构由随机效应近似。",
            ],
        ),
        diagnostics=diagnostics, primary_tests=primary, coefficients=coefficients,
        estimated_marginal_means=emmeans, contrasts=contrasts, significance_letters=significance_letters, diagnostic_plots=plots,
        fit_statistics=fit_statistics,
        warnings=warnings,
        descriptive_stats=clean.groupby([*between_factors, repeated_factor], observed=True)[dv].agg(["count", "mean", "std"]).reset_index().rename(columns={"count":"n", "std":"sd"}).to_dict("records"),
        data_snapshot={
            "analysis_mode": "mixedlm", "n_observations": int(len(clean)),
            "n_subjects": int(clean[subject_id].nunique()), "between_factors": between_factors,
            "within_levels": [str(value) for value in pd.unique(clean[repeated_factor])],
            "reml": reml, "optimizer": optimizer, "random_slope_repeated": random_slope,
        },
        provenance={"engine": "statsmodels MixedLM", "fixed_effect_test": "joint Wald chi-square"},
    )


def _classical_mixed_anova(
    df: pd.DataFrame,
    dv: str,
    subject_id: str,
    repeated_factor: str,
    between_factor: str,
    alpha: float,
    parameters: dict[str, Any] | None = None,
    *,
    estimate_emm: bool = True,
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    """一个对象间因素×一个对象内因素的完整平衡经典混合设计 ANOVA。"""
    parameters = parameters or {}
    clean = df[[dv, subject_id, repeated_factor, between_factor]].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna()
    if clean.duplicated([subject_id, repeated_factor]).any():
        raise ValueError("混合设计要求每个对象×重复水平只有一条观测")
    subject_groups = clean.groupby(subject_id, observed=True)[between_factor].nunique()
    if (subject_groups != 1).any():
        raise ValueError("每个对象必须只属于一个对象间因素水平")
    within_levels = list(pd.unique(clean[repeated_factor]))
    between_levels = list(pd.unique(clean[between_factor]))
    if len(within_levels) < 2 or len(between_levels) < 2:
        raise ValueError("混合设计需要至少 2 个对象内水平和 2 个对象间水平")
    wide = clean.pivot(index=subject_id, columns=repeated_factor, values=dv).reindex(columns=within_levels)
    if wide.isna().any().any():
        raise ValueError("经典混合设计要求每个对象具有全部重复水平；缺失设计请改用线性混合模型")
    group_by_subject = clean.drop_duplicates(subject_id).set_index(subject_id)[between_factor].reindex(wide.index)
    counts = group_by_subject.value_counts().reindex(between_levels)
    if counts.isna().any() or counts.nunique() != 1:
        raise ValueError("当前经典混合设计实现要求各对象间组具有相同对象数；不平衡设计请改用线性混合模型")
    n_per_group = int(counts.iloc[0])
    if n_per_group < 2:
        raise ValueError("每个对象间组至少需要 2 个对象")
    a, b = len(between_levels), len(within_levels)
    n_subjects = len(wide)
    values = wide.to_numpy(dtype=float)
    grand = float(values.mean())
    subject_means = wide.mean(axis=1)
    time_means = wide.mean(axis=0)
    group_means = {level: float(subject_means[group_by_subject == level].mean()) for level in between_levels}
    cell_means = {(g, t): float(wide.loc[group_by_subject == g, t].mean()) for g in between_levels for t in within_levels}
    ss_between = float(b * n_per_group * sum((group_means[g] - grand) ** 2 for g in between_levels))
    ss_subject = float(b * sum((float(subject_means.loc[s]) - group_means[group_by_subject.loc[s]]) ** 2 for s in wide.index))
    ss_within_total = float(np.sum((values - subject_means.to_numpy()[:, None]) ** 2))
    ss_within = float(n_subjects * sum((float(time_means[t]) - grand) ** 2 for t in within_levels))
    ss_interaction = float(n_per_group * sum((cell_means[g, t] - group_means[g] - float(time_means[t]) + grand) ** 2 for g in between_levels for t in within_levels))
    ss_error = max(0.0, ss_within_total - ss_within - ss_interaction)
    df_between, df_subject = a - 1, n_subjects - a
    df_within, df_interaction, df_error = b - 1, (a - 1) * (b - 1), (n_subjects - a) * (b - 1)
    ms_subject = ss_subject / df_subject
    ms_error = ss_error / df_error
    effects = [
        (between_factor, ss_between, df_between, ms_subject, df_subject),
        (repeated_factor, ss_within, df_within, ms_error, df_error),
        (f"{between_factor} × {repeated_factor}", ss_interaction, df_interaction, ms_error, df_error),
    ]
    sph = sphericity_result(wide, alpha)
    omnibus: list[OmnibusTest] = []
    for effect, ss_value, df_num, denominator_ms, df_den in effects:
        ms = ss_value / df_num
        f_value = safe_standardized_statistic(ms, denominator_ms)
        p_value = float(stats.f.sf(f_value, df_num, df_den)) if np.isfinite(f_value) else 0.0
        error_ss = ss_subject if effect == between_factor else ss_error
        partial_eta = ss_value / (ss_value + error_ss) if ss_value + error_ss > 0 else 0.0
        adjustments = [] if effect == between_factor else sphericity_adjustments(f_value, df_num, df_den, sph, alpha)
        omnibus.append(OmnibusTest(
            effect=effect, df_num=float(df_num), df_den=float(df_den), f_value=float(f_value), p_value=p_value,
            eta_sq=ss_value / (ss_between + ss_subject + ss_within_total) if (ss_between + ss_subject + ss_within_total) > 0 else 0.0,
            eta_sq_p=partial_eta, is_significant=bool(p_value < alpha), significance_level=alpha,
            adjustments=adjustments,
        ))
    emmeans: list[EMMeans] = []
    if estimate_emm:
        for group in between_levels:
            for level in within_levels:
                sample = wide.loc[group_by_subject == group, level].to_numpy(dtype=float)
                mean = float(sample.mean())
                se = float(sample.std(ddof=1) / np.sqrt(len(sample)))
                critical = float(stats.t.ppf(1 - alpha / 2, len(sample) - 1))
                emmeans.append(EMMeans(
                    group=f"{between_factor}={group}, {repeated_factor}={level}",
                    levels={between_factor: str(group), repeated_factor: str(level)},
                    mean=mean, se=se, ci_lower=mean-critical*se, ci_upper=mean+critical*se,
                    df=float(len(sample)-1), source="balanced cell mean",
                ))
    raw_contrasts: list[ContrastResult] = []
    raw_p: list[float] = []
    # 对象内：每个组内比较重复水平。
    for group in between_levels:
        group_wide = wide.loc[group_by_subject == group]
        for left, right in combinations(within_levels, 2):
            difference = group_wide[left] - group_wide[right]
            statistic, p_value = safe_paired_ttest(group_wide[left], group_wide[right])
            se = float(difference.std(ddof=1) / np.sqrt(len(difference)))
            raw_p.append(float(p_value))
            raw_contrasts.append(ContrastResult(
                contrast=f"[{between_factor}={group}] {left} - {right}", estimate=float(difference.mean()), se=se,
                t_value=float(statistic), p_value=float(p_value), p_adjusted=float(p_value),
                df=float(len(difference)-1), significant=False, correction="none",
            ))
    # 对象间：每个重复水平比较组别。
    for level in within_levels:
        for left, right in combinations(between_levels, 2):
            left_values = wide.loc[group_by_subject == left, level]
            right_values = wide.loc[group_by_subject == right, level]
            statistic, p_value = stats.ttest_ind(left_values, right_values, equal_var=True)
            estimate = float(left_values.mean() - right_values.mean())
            pooled = ((len(left_values)-1)*left_values.var(ddof=1)+(len(right_values)-1)*right_values.var(ddof=1))/(len(left_values)+len(right_values)-2)
            se = float(np.sqrt(pooled*(1/len(left_values)+1/len(right_values))))
            raw_p.append(float(p_value))
            raw_contrasts.append(ContrastResult(
                contrast=f"[{repeated_factor}={level}] {left} - {right}", estimate=estimate, se=se,
                t_value=float(statistic), p_value=float(p_value), p_adjusted=float(p_value),
                df=float(len(left_values)+len(right_values)-2), significant=False, correction="none",
            ))
    correction = str(parameters.get("pairwise_correction", "holm"))
    adjusted = np.asarray(raw_p, dtype=float)
    if len(adjusted) and correction != "none":
        adjusted = multipletests(adjusted, alpha=alpha, method=correction)[1]
    comparison_count = max(1, len(raw_contrasts))
    if correction in {"bonferroni", "holm"}:
        interval_alpha = alpha / comparison_count
    elif correction == "sidak":
        interval_alpha = 1 - (1 - alpha) ** (1 / comparison_count)
    else:
        interval_alpha = alpha
    for index, contrast in enumerate(raw_contrasts):
        contrast.p_adjusted = float(adjusted[index])
        contrast.significant = bool(adjusted[index] < alpha)
        contrast.correction = correction
        critical = float(stats.t.ppf(1 - interval_alpha / 2, contrast.df))
        contrast.ci_lower = float(contrast.estimate - critical * contrast.se)
        contrast.ci_upper = float(contrast.estimate + critical * contrast.se)
    fitted = np.array([cell_means[group_by_subject.loc[s], t] for s in wide.index for t in within_levels], dtype=float)
    observed = wide.to_numpy(dtype=float).reshape(-1)
    plots = regression_diagnostic_plots(fitted, observed-fitted) if diagnostic_plots else []
    plots.append(interaction_plot(clean, dv, between_factor, repeated_factor))
    warnings: list[str] = []
    if sph and not sph.passed:
        warnings.append("对象内球形性可能不满足，请优先解释 GG/HF 校正结果。")
    return StatisticalResult(
        analysis_id=f"mixed_anova_{dv}",
        design=design_info(clean, dependent=[dv], fixed=[between_factor], subject_id=subject_id, repeated_factor=repeated_factor),
        method=MethodInfo(name="mixed_anova", label_zh="混合设计方差分析", formula=f"{dv} ~ {between_factor} * {repeated_factor} + Error({subject_id}/{repeated_factor})"),
        omnibus_tests=omnibus, sphericity=sph, estimated_marginal_means=emmeans,
        contrasts=raw_contrasts, diagnostic_plots=plots, warnings=warnings,
        effect_sizes=[EffectSize(measure=f"partial eta squared: {item.effect}", value=item.eta_sq_p) for item in omnibus],
        descriptive_stats=clean.groupby([between_factor, repeated_factor], observed=True)[dv].agg(["count", "mean", "std"]).reset_index().rename(columns={"count":"n", "std":"sd"}).to_dict("records"),
        data_snapshot={"n_subjects": n_subjects, "subjects_per_group": n_per_group, "between_levels": [str(x) for x in between_levels], "within_levels": [str(x) for x in within_levels]},
    )


def friedman_test(df: pd.DataFrame, dv: str, subject_id: str, repeated_factor: str, alpha: float) -> StatisticalResult:
    clean = df[[dv, subject_id, repeated_factor]].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    clean = clean.dropna()
    if clean.duplicated([subject_id, repeated_factor]).any():
        raise ValueError("Friedman 检验要求每个受试者×重复水平只有一条观测")
    wide = clean.pivot(index=subject_id, columns=repeated_factor, values=dv).dropna()
    if wide.shape[0] < 2 or wide.shape[1] < 3:
        raise ValueError("Friedman 检验至少需要 2 个完整对象和 3 个重复水平")
    statistic, p = stats.friedmanchisquare(*(wide[column].to_numpy() for column in wide.columns))
    n, k = wide.shape
    kendall_w = float(statistic / (n * (k - 1)))
    desc = [{"level": str(column), "n": n, "median": float(np.median(wide[column])), "mean_rank": float(stats.rankdata(wide.to_numpy(), axis=1)[:, index].mean())} for index, column in enumerate(wide.columns)]
    return StatisticalResult(
        analysis_id=f"friedman_{dv}",
        design=design_info(clean, dependent=[dv], subject_id=subject_id, repeated_factor=repeated_factor),
        method=MethodInfo(name="friedman_test", label_zh="Friedman 重复测量秩检验", formula=f"rank({dv}) ~ {repeated_factor} | {subject_id}"),
        primary_tests=[PrimaryTestResult(
            effect=repeated_factor, statistic_name="chi-square", statistic_value=float(statistic), p_value=float(p), df_num=float(k - 1),
            effect_size_name="Kendall's W", effect_size_value=kendall_w,
            is_significant=significance(float(p), alpha), significance_level=alpha,
        )],
        effect_sizes=[EffectSize(measure="Kendall's W", value=kendall_w)],
        descriptive_stats=desc,
        data_snapshot={"n_subjects": n, "n_conditions": k},
    )
