"""线性、Logistic 与混合效应回归。"""
from __future__ import annotations

import math
import warnings as pywarnings
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import variance_inflation_factor

from .common import design_info, significance
from .model_support import estimated_marginal_means, regression_diagnostic_plots
from .result import (
    CoefficientResult,
    DiagnosticResult,
    FitStatistic,
    MethodInfo,
    PrimaryTestResult,
    StatisticalResult,
)


def quote(column: str) -> str:
    escaped = str(column).replace("\\", "\\\\").replace('"', '\\"')
    return f'Q("{escaped}")'


def categorical(column: str, *, sum_contrast: bool = False) -> str:
    return f"C({quote(column)}, Sum)" if sum_contrast else f"C({quote(column)})"


def predictor_terms(fixed_factors: list[str], covariates: list[str], *, sum_contrast: bool = False) -> list[str]:
    return [categorical(column, sum_contrast=sum_contrast) for column in fixed_factors] + [quote(column) for column in covariates]


def linear_regression(
    df: pd.DataFrame, dv: str, fixed_factors: list[str], covariates: list[str], alpha: float,
    *, emm_factors: list[str] | None = None, contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    required = [dv] + fixed_factors + covariates
    clean = df[required].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    if len(clean) < max(8, len(fixed_factors) + len(covariates) + 3):
        raise ValueError("线性回归的完整案例不足")
    terms = predictor_terms(fixed_factors, covariates)
    if not terms:
        raise ValueError("线性回归至少需要一个连续协变量或分类固定因素")
    formula = f"{quote(dv)} ~ " + " + ".join(terms)
    model = smf.ols(formula, data=clean).fit()
    ci = model.conf_int(alpha=alpha)
    coefficients = [CoefficientResult(
        term=str(term), estimate=float(model.params[term]), se=float(model.bse[term]),
        statistic_name="t", statistic_value=float(model.tvalues[term]), p_value=float(model.pvalues[term]),
        ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]),
        significant=significance(float(model.pvalues[term]), alpha),
    ) for term in model.params.index]
    diagnostics: list[DiagnosticResult] = []
    warnings: list[str] = []
    residuals = np.asarray(model.resid, dtype=float)
    if len(residuals) >= 3:
        jb_stat, jb_p = stats.jarque_bera(residuals)
        diagnostics.append(DiagnosticResult(test_name="Jarque–Bera（残差正态性）", statistic=float(jb_stat), p_value=float(jb_p), passed=bool(jb_p >= alpha)))
    try:
        bp_stat, bp_p, _, _ = het_breuschpagan(residuals, model.model.exog)
        diagnostics.append(DiagnosticResult(test_name="Breusch–Pagan（同方差）", statistic=float(bp_stat), p_value=float(bp_p), passed=bool(bp_p >= alpha)))
    except Exception as exc:
        warnings.append(f"Breusch–Pagan 同方差诊断未能计算：{exc}")
    if len(model.model.exog_names) > 2:
        vif_values = []
        for index, name in enumerate(model.model.exog_names):
            if name == "Intercept":
                continue
            try:
                vif_values.append((name, float(variance_inflation_factor(model.model.exog, index))))
            except Exception:
                continue
        high = [(name, value) for name, value in vif_values if np.isfinite(value) and value >= 10]
        if high:
            warnings.append("检测到较高多重共线性（VIF≥10）: " + "；".join(f"{name}={value:.2f}" for name, value in high))
    primary = [PrimaryTestResult(
        effect="整体回归模型", statistic_name="F", statistic_value=float(model.fvalue) if model.fvalue is not None else 0.0,
        p_value=float(model.f_pvalue) if model.f_pvalue is not None else 1.0,
        df_num=float(model.df_model), df_den=float(model.df_resid), effect_size_name="R-squared", effect_size_value=float(model.rsquared),
        is_significant=significance(float(model.f_pvalue) if model.f_pvalue is not None else 1.0, alpha), significance_level=alpha,
    )]
    emmeans, contrasts = ([], [])
    if emm_factors:
        emmeans, contrasts = estimated_marginal_means(
            model, clean, target_factors=emm_factors, categorical_factors=fixed_factors, covariates=covariates,
            alpha=alpha, correction=contrast_correction, df_resid=float(model.df_resid),
        )
    plots = []
    if diagnostic_plots:
        influence = model.get_influence()
        plots = regression_diagnostic_plots(
            model.fittedvalues, residuals, leverage=influence.hat_matrix_diag,
            cooks_distance=influence.cooks_distance[0],
        )
    return StatisticalResult(
        analysis_id=f"linear_regression_{dv}",
        design=design_info(clean, dependent=[dv], fixed=fixed_factors, covariates=covariates),
        method=MethodInfo(name="linear_regression", label_zh="线性回归", formula=formula, report_constraints=["回归系数表示控制其他变量后的线性关联，不自动代表因果。"]),
        primary_tests=primary, coefficients=coefficients, estimated_marginal_means=emmeans, contrasts=contrasts,
        fit_statistics=[
            FitStatistic(name="R-squared", value=float(model.rsquared)),
            FitStatistic(name="Adjusted R-squared", value=float(model.rsquared_adj)),
            FitStatistic(name="AIC", value=float(model.aic)),
            FitStatistic(name="BIC", value=float(model.bic)),
            FitStatistic(name="RMSE", value=float(np.sqrt(np.mean(residuals**2)))),
        ],
        diagnostics=diagnostics, diagnostic_plots=plots, warnings=warnings,
        data_snapshot={"n": int(model.nobs), "formula": formula},
    )


def logistic_regression(
    df: pd.DataFrame, dv: str, fixed_factors: list[str], covariates: list[str], alpha: float,
    parameters: dict[str, Any] | None = None,
) -> StatisticalResult:
    required = [dv] + fixed_factors + covariates
    clean = df[required].copy()
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    levels = list(pd.unique(clean[dv]))
    if len(levels) != 2:
        raise ValueError(f"二元 Logistic 回归要求因变量恰好 2 个水平，当前为 {len(levels)} 个")
    requested_success = str((parameters or {}).get("success_level", "")).strip()
    if requested_success:
        matches = [level for level in levels if str(level) == requested_success]
        if not matches:
            raise ValueError(f"指定的成功水平 {requested_success!r} 不在因变量水平中: {[str(item) for item in levels]}")
        success_level = matches[0]
        reference_level = next(level for level in levels if level != success_level)
    else:
        reference_level, success_level = levels[0], levels[1]
    mapping = {reference_level: 0, success_level: 1}
    clean = clean.assign(_binary_outcome=clean[dv].map(mapping).astype(float))
    terms = predictor_terms(fixed_factors, covariates)
    if not terms:
        raise ValueError("Logistic 回归至少需要一个预测变量")
    if len(clean) < max(20, 5 * (len(terms) + 1)):
        raise ValueError("Logistic 回归完整案例过少，无法稳定拟合")
    formula = "_binary_outcome ~ " + " + ".join(terms)
    with pywarnings.catch_warnings(record=True) as caught:
        pywarnings.simplefilter("always")
        max_iterations = int((parameters or {}).get("max_iterations", 200))
        covariance_type = str((parameters or {}).get("covariance_type", "nonrobust"))
        fit_kwargs = {"maxiter": max_iterations}
        if covariance_type != "nonrobust":
            fit_kwargs["cov_type"] = covariance_type
        model = smf.glm(formula, data=clean, family=sm.families.Binomial()).fit(**fit_kwargs)
    ci = model.conf_int(alpha=alpha)
    coefficients = []
    for term in model.params.index:
        estimate = float(model.params[term])
        coefficients.append(CoefficientResult(
            term=str(term), estimate=estimate, se=float(model.bse[term]), statistic_name="z",
            statistic_value=float(model.tvalues[term]), p_value=float(model.pvalues[term]),
            ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]),
            transformed_name="odds ratio", transformed_value=float(math.exp(estimate)),
            significant=significance(float(model.pvalues[term]), alpha),
        ))
    null_deviance = float(model.null_deviance)
    deviance_r2 = 1 - float(model.deviance) / null_deviance if null_deviance > 0 else 0.0
    llf = float(model.llf)
    llnull = float(model.llnull)
    mcfadden_r2 = 1 - llf / llnull if np.isfinite(llnull) and not np.isclose(llnull, 0.0) else 0.0
    lr_stat = max(0.0, null_deviance - float(model.deviance))
    lr_df = max(1, int(model.df_model))
    lr_p = float(stats.chi2.sf(lr_stat, lr_df))
    warnings = [str(item.message) for item in caught]
    fitted = np.asarray(model.fittedvalues)
    if np.any((fitted < 1e-8) | (fitted > 1 - 1e-8)):
        warnings.append("部分预测概率接近 0 或 1，可能存在准完全分离或过拟合。")
    return StatisticalResult(
        analysis_id=f"logistic_regression_{dv}",
        design=design_info(clean, dependent=[dv], fixed=fixed_factors, covariates=covariates),
        method=MethodInfo(name="logistic_regression", label_zh="二元 Logistic 回归", formula=f"{dv}({success_level}=1) ~ " + " + ".join(terms), report_constraints=["优势比是关联强度，不自动代表因果。"]),
        primary_tests=[PrimaryTestResult(
            effect="整体 Logistic 模型", statistic_name="likelihood-ratio chi-square", statistic_value=lr_stat,
            p_value=lr_p, df_num=float(lr_df), effect_size_name="McFadden pseudo R-squared", effect_size_value=mcfadden_r2,
            is_significant=significance(lr_p, alpha), significance_level=alpha,
        )],
        coefficients=coefficients,
        fit_statistics=[
            FitStatistic(name="AIC", value=float(model.aic)),
            FitStatistic(name="Deviance", value=float(model.deviance)),
            FitStatistic(name="Null deviance", value=null_deviance),
            FitStatistic(name="McFadden pseudo R-squared", value=mcfadden_r2),
            FitStatistic(name="Deviance explained", value=deviance_r2),
        ],
        warnings=warnings,
        data_snapshot={"n": int(model.nobs), "outcome_mapping": {str(key): value for key, value in mapping.items()}, "covariance_type": covariance_type, "max_iterations": max_iterations},
    )


def linear_mixed_model(
    df: pd.DataFrame,
    dv: str,
    fixed_factors: list[str],
    covariates: list[str],
    group: str,
    alpha: float,
    *,
    parameters: dict[str, Any] | None = None,
    random_slopes: list[str] | None = None,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    parameters = parameters or {}
    random_slopes = random_slopes or []
    required = list(dict.fromkeys([dv, group] + fixed_factors + covariates + random_slopes))
    clean = df[required].copy()
    clean[dv] = pd.to_numeric(clean[dv], errors="coerce")
    for column in covariates:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    for column in random_slopes:
        if column not in fixed_factors:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna()
    n_groups = int(clean[group].nunique())
    if n_groups < 3:
        raise ValueError("线性混合模型至少需要 3 个随机分组水平")
    terms = predictor_terms(fixed_factors, covariates)
    if not terms:
        raise ValueError("线性混合模型至少需要一个固定预测变量")
    formula = f"{quote(dv)} ~ " + " + ".join(terms)
    random_terms = [categorical(name) if name in fixed_factors else quote(name) for name in random_slopes]
    re_formula = "1" + (" + " + " + ".join(random_terms) if random_terms else "")
    reml = bool(parameters.get("reml", True))
    optimizer = str(parameters.get("optimizer", "lbfgs"))
    max_iterations = int(parameters.get("max_iterations", 500))
    with pywarnings.catch_warnings(record=True) as caught:
        pywarnings.simplefilter("always")
        model = smf.mixedlm(formula, clean, groups=clean[group], re_formula=re_formula)
        fit = model.fit(reml=reml, method=optimizer, maxiter=max_iterations, disp=False)
    ci = fit.conf_int(alpha=alpha)
    coefficients = []
    for term in fit.fe_params.index:
        estimate = float(fit.fe_params[term])
        coefficients.append(CoefficientResult(
            term=str(term), estimate=estimate, se=float(fit.bse_fe[term]), statistic_name="z",
            statistic_value=float(fit.tvalues[term]), p_value=float(fit.pvalues[term]),
            ci_lower=float(ci.loc[term, 0]), ci_upper=float(ci.loc[term, 1]),
            significant=significance(float(fit.pvalues[term]), alpha),
        ))
    covariance_matrix = np.asarray(fit.cov_re, dtype=float)
    residual_variance = float(fit.scale)
    random_variance = float(covariance_matrix[0, 0]) if covariance_matrix.size else 0.0
    icc = random_variance / (random_variance + residual_variance) if random_variance + residual_variance > 0 else 0.0
    warnings = [str(item.message) for item in caught]
    if not fit.converged:
        warnings.append("混合模型优化器未完全收敛，结果不应直接用于正式结论。")
    if np.linalg.matrix_rank(covariance_matrix) < covariance_matrix.shape[0]:
        warnings.append("随机效应协方差矩阵接近奇异；随机结构可能过于复杂。")
    fit_statistics = [
        FitStatistic(name="Log-likelihood", value=float(fit.llf)),
        FitStatistic(name="Random intercept variance", value=random_variance),
        FitStatistic(name="Residual variance", value=residual_variance),
        FitStatistic(name="ICC", value=icc),
    ]
    if np.isfinite(fit.aic):
        fit_statistics.insert(0, FitStatistic(name="AIC", value=float(fit.aic), detail="最大似然模型比较指标"))
    elif reml:
        warnings.append("REML 拟合不报告 AIC/BIC；如需比较固定效应模型，请使用 ML（reml=false）并保持随机结构一致。")
    if np.isfinite(fit.bic):
        insertion = 1 if fit_statistics and fit_statistics[0].name == "AIC" else 0
        fit_statistics.insert(insertion, FitStatistic(name="BIC", value=float(fit.bic), detail="最大似然模型比较指标"))
    random_names = list(getattr(fit.model.data, "exog_re_names", []) or [f"random_{index}" for index in range(covariance_matrix.shape[0])])
    for index, name in enumerate(random_names):
        if index < covariance_matrix.shape[0]:
            fit_statistics.append(FitStatistic(name=f"Random variance: {name}", value=float(covariance_matrix[index, index])))
    for row in range(covariance_matrix.shape[0]):
        for column in range(row + 1, covariance_matrix.shape[1]):
            fit_statistics.append(FitStatistic(
                name=f"Random covariance: {random_names[row]} × {random_names[column]}",
                value=float(covariance_matrix[row, column]),
            ))
    emmeans, contrasts = ([], [])
    if emm_factors:
        fixed_names = list(fit.fe_params.index)
        fixed_cov = fit.cov_params().loc[fixed_names, fixed_names]
        emmeans, contrasts = estimated_marginal_means(
            fit, clean, target_factors=emm_factors, categorical_factors=fixed_factors,
            covariates=covariates, alpha=alpha, correction=contrast_correction,
            fixed_params=fit.fe_params, fixed_cov=fixed_cov, normal_approximation=True,
        )
    plots = regression_diagnostic_plots(fit.fittedvalues, fit.resid) if diagnostic_plots else []
    return StatisticalResult(
        analysis_id=f"mixedlm_{dv}",
        design=design_info(clean, dependent=[dv], fixed=fixed_factors, covariates=covariates, random=[group]),
        method=MethodInfo(
            name="linear_mixed_model", label_zh="线性混合效应模型",
            formula=formula + f" + ({re_formula}|{group})",
            report_constraints=["固定效应采用大样本 z 近似；随机效应结构和收敛状态必须一并报告。"],
        ),
        coefficients=coefficients, fit_statistics=fit_statistics,
        estimated_marginal_means=emmeans, contrasts=contrasts,
        diagnostic_plots=plots, warnings=warnings,
        data_snapshot={
            "n": int(fit.nobs), "n_groups": n_groups, "converged": bool(fit.converged),
            "reml": reml, "optimizer": optimizer, "max_iterations": max_iterations,
            "random_slopes": random_slopes,
        },
    )
