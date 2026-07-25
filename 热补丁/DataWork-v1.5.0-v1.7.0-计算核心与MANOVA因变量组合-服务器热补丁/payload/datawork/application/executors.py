"""统计方法执行器注册表。"""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from datawork.core.plan import AnalysisPlan
from datawork.engine.advanced_methods import ancova, friedman_test, mixed_anova, repeated_measures_anova
from datawork.engine.basic_methods import (
    chi_square_goodness_of_fit,
    correlation,
    descriptive_statistics,
    kruskal_wallis,
    mann_whitney_u,
    one_sample_ttest,
    wilcoxon_signed_rank,
)
from datawork.engine.categorical_methods import (
    barnard_exact_test,
    boschloo_exact_test,
    bowker_symmetry_test,
    breslow_day_test,
    chi_square_independence,
    cochran_armitage_trend_test,
    cochran_mantel_haenszel,
    cochran_q_test,
    cohen_kappa_test,
    exact_binomial_test,
    fisher_exact_test,
    fleiss_kappa_test,
    k_proportion_chi_square,
    mcnemar_test,
    multinomial_logistic_regression,
    one_sample_proportion_ztest,
    ordinal_logistic_regression,
    stuart_maxwell_test,
    two_proportion_ztest,
)
from datawork.engine.manova import manova
from datawork.engine.multiway_anova import multiway_anova
from datawork.engine.model_support import resolve_control_group
from datawork.engine.oneway_anova import oneway_anova
from datawork.engine.regression_methods import linear_mixed_model, linear_regression, logistic_regression
from datawork.engine.result import StatisticalResult
from datawork.engine.ttest import independent_ttest, paired_ttest
from datawork.engine.twoway_anova import threeway_anova, twoway_anova


Executor = Callable[[pd.DataFrame, AnalysisPlan], StatisticalResult]
_EXECUTORS: dict[str, Executor] = {}


def register_executor(name: str) -> Callable[[Executor], Executor]:
    def decorator(function: Executor) -> Executor:
        if name in _EXECUTORS:
            raise RuntimeError(f"执行器已注册: {name}")
        _EXECUTORS[name] = function
        return function
    return decorator


def get_executor(name: str | None) -> Executor:
    if not name:
        raise ValueError("方法没有配置执行器")
    try:
        return _EXECUTORS[name]
    except KeyError as exc:
        raise ValueError(f"缺少统计执行器: {name}") from exc


@register_executor("descriptive_statistics")
def execute_descriptive(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return descriptive_statistics(frame, plan.dependent_variables)


@register_executor("one_sample_ttest")
def execute_one_sample_ttest(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return one_sample_ttest(frame, plan.dependent_variables[0], plan.test_value, plan.alpha)


@register_executor("welch_ttest")
def execute_welch_ttest(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    dv, factor = plan.dependent_variables[0], plan.fixed_factors[0]
    return independent_ttest(frame[dv], frame[factor], dv, factor, equal_var=False, alpha=plan.alpha)


@register_executor("independent_ttest")
def execute_independent_ttest(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    dv, factor = plan.dependent_variables[0], plan.fixed_factors[0]
    return independent_ttest(frame[dv], frame[factor], dv, factor, equal_var=True, alpha=plan.alpha)


@register_executor("paired_ttest")
def execute_paired_ttest(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return paired_ttest(frame[first], frame[second], dv_name=f"{first} / {second}", time_labels=(first, second), alpha=plan.alpha)


@register_executor("mann_whitney_u")
def execute_mann_whitney(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return mann_whitney_u(frame, plan.dependent_variables[0], plan.fixed_factors[0], plan.alpha)


@register_executor("wilcoxon_signed_rank")
def execute_wilcoxon(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return wilcoxon_signed_rank(frame, first, second, plan.alpha)


@register_executor("oneway_anova")
def execute_oneway_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    params = plan.method_parameters or {}
    return oneway_anova(
        frame, plan.dependent_variables[0], plan.fixed_factors[0], welch=False,
        posthoc_methods=params.get("posthoc_methods", [plan.posthoc_method or "auto"]),
        control_group=resolve_control_group(str(params.get("control_group", "")).strip() or None, plan.fixed_factors[0]),
        random_seed=int(params.get("random_seed", 2026)),
        alpha=plan.alpha, estimate_emm=plan.estimate_marginal_means,
        diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("welch_anova")
def execute_welch_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    params = plan.method_parameters or {}
    return oneway_anova(
        frame, plan.dependent_variables[0], plan.fixed_factors[0], welch=True,
        posthoc_methods=params.get("posthoc_methods", ["auto"]),
        control_group=resolve_control_group(str(params.get("control_group", "")).strip() or None, plan.fixed_factors[0]),
        random_seed=int(params.get("random_seed", 2026)),
        alpha=plan.alpha, estimate_emm=plan.estimate_marginal_means,
        diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("kruskal_wallis")
def execute_kruskal(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return kruskal_wallis(frame, plan.dependent_variables[0], plan.fixed_factors[0], plan.alpha)


@register_executor("twoway_anova")
def execute_twoway_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.fixed_factors
    params = plan.method_parameters or {}
    return twoway_anova(
        frame, plan.dependent_variables[0], first, second,
        posthoc_methods=params.get("posthoc_methods", [plan.posthoc_method or "tukey"]),
        control_group=str(params.get("control_group", "")).strip() or None,
        alpha=plan.alpha, ss_type=plan.ss_type,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction, diagnostic_plots=plan.diagnostic_plots,
        simple_effect_correction=str(params.get("simple_effect_correction", "holm")),
    )


@register_executor("threeway_anova")
def execute_threeway_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second, third = plan.fixed_factors
    params = plan.method_parameters or {}
    return threeway_anova(
        frame, plan.dependent_variables[0], first, second, third,
        posthoc_methods=params.get("posthoc_methods", [plan.posthoc_method or "tukey"]),
        control_group=str(params.get("control_group", "")).strip() or None,
        alpha=plan.alpha, ss_type=plan.ss_type,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction, diagnostic_plots=plan.diagnostic_plots,
        simple_effect_correction=str(params.get("simple_effect_correction", "holm")),
    )


@register_executor("multifactor_anova")
def execute_multifactor_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    order = int(plan.method_parameters.get("factor_model_order", 4))
    if order not in range(4, 9) or len(plan.fixed_factors) != order:
        raise ValueError(f"多因素方差分析阶数为 {order}，必须恰好选择 {order} 个分类因素")
    return multiway_anova(
        frame, plan.dependent_variables[0], plan.fixed_factors,
        alpha=plan.alpha, ss_type=plan.ss_type,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction,
        diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("ancova")
def execute_ancova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return ancova(
        frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.alpha, plan.ss_type,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction, diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("pearson_correlation")
def execute_pearson(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return correlation(frame, first, second, "pearson_correlation", plan.alpha)


@register_executor("spearman_correlation")
def execute_spearman(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return correlation(frame, first, second, "spearman_correlation", plan.alpha)


@register_executor("kendall_correlation")
def execute_kendall(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return correlation(frame, first, second, "kendall_correlation", plan.alpha)


@register_executor("linear_regression")
def execute_linear_regression(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return linear_regression(
        frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.alpha,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction, diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("logistic_regression")
def execute_logistic_regression(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return logistic_regression(frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.alpha, plan.method_parameters)


@register_executor("chi_square_independence")
def execute_chi_square(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.fixed_factors
    return chi_square_independence(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("fisher_exact")
def execute_fisher(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.fixed_factors
    return fisher_exact_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("chi_square_goodness_of_fit")
def execute_goodness(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return chi_square_goodness_of_fit(frame, plan.fixed_factors[0], plan.expected_proportions, plan.alpha)


@register_executor("mcnemar_test")
def execute_mcnemar(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return mcnemar_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("exact_binomial_test")
def execute_exact_binomial(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return exact_binomial_test(frame, plan.fixed_factors[0], plan.alpha, plan.method_parameters)


@register_executor("one_sample_proportion_ztest")
def execute_one_proportion(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return one_sample_proportion_ztest(frame, plan.fixed_factors[0], plan.alpha, plan.method_parameters)


@register_executor("two_proportion_ztest")
def execute_two_proportion(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return two_proportion_ztest(frame, plan.dependent_variables[0], plan.fixed_factors[0], plan.alpha, plan.method_parameters)


@register_executor("k_proportion_chi_square")
def execute_k_proportion(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return k_proportion_chi_square(frame, plan.dependent_variables[0], plan.fixed_factors[0], plan.alpha, plan.method_parameters)


@register_executor("barnard_exact")
def execute_barnard(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.fixed_factors
    return barnard_exact_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("boschloo_exact")
def execute_boschloo(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.fixed_factors
    return boschloo_exact_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("cochran_q_test")
def execute_cochran_q(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return cochran_q_test(frame, plan.dependent_variables, plan.alpha, plan.method_parameters)


@register_executor("bowker_symmetry")
def execute_bowker(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return bowker_symmetry_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("stuart_maxwell")
def execute_stuart_maxwell(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return stuart_maxwell_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("cochran_mantel_haenszel")
def execute_cmh(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    exposure, strata = plan.fixed_factors
    return cochran_mantel_haenszel(frame, plan.dependent_variables[0], exposure, strata, plan.alpha, plan.method_parameters)


@register_executor("breslow_day")
def execute_breslow_day(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    exposure, strata = plan.fixed_factors
    return breslow_day_test(frame, plan.dependent_variables[0], exposure, strata, plan.alpha, plan.method_parameters)


@register_executor("cohen_kappa")
def execute_cohen_kappa(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    first, second = plan.dependent_variables
    return cohen_kappa_test(frame, first, second, plan.alpha, plan.method_parameters)


@register_executor("fleiss_kappa")
def execute_fleiss_kappa(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return fleiss_kappa_test(frame, plan.dependent_variables, plan.alpha, plan.method_parameters)


@register_executor("cochran_armitage_trend")
def execute_cochran_armitage(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return cochran_armitage_trend_test(frame, plan.dependent_variables[0], plan.fixed_factors[0], plan.alpha, plan.method_parameters)


@register_executor("multinomial_logistic_regression")
def execute_multinomial_logit(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return multinomial_logistic_regression(frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.alpha, plan.method_parameters)


@register_executor("ordinal_logistic_regression")
def execute_ordinal_logit(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return ordinal_logistic_regression(frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.alpha, plan.method_parameters)


@register_executor("repeated_measures_anova")
def execute_repeated(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    if not plan.subject_id or not plan.repeated_factor:
        raise ValueError("重复测量 ANOVA 缺少对象 ID 或重复因素")
    return repeated_measures_anova(
        frame, plan.dependent_variables[0], plan.subject_id, plan.repeated_factor, plan.alpha,
        plan.method_parameters, estimate_emm=plan.estimate_marginal_means, diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("friedman_test")
def execute_friedman(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    if not plan.subject_id or not plan.repeated_factor:
        raise ValueError("Friedman 检验缺少对象 ID 或重复因素")
    return friedman_test(frame, plan.dependent_variables[0], plan.subject_id, plan.repeated_factor, plan.alpha)


@register_executor("linear_mixed_model")
def execute_mixed(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return linear_mixed_model(
        frame, plan.dependent_variables[0], plan.fixed_factors, plan.covariates, plan.random_factors[0], plan.alpha,
        parameters=plan.method_parameters, random_slopes=plan.random_slopes,
        emm_factors=plan.emm_factors if plan.estimate_marginal_means else [],
        contrast_correction=plan.contrast_correction, diagnostic_plots=plan.diagnostic_plots,
    )


@register_executor("mixed_anova")
def execute_mixed_anova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    if not plan.subject_id or not plan.repeated_factor:
        raise ValueError("混合设计方差分析缺少对象 ID 或重复因素")
    return mixed_anova(
        frame, plan.dependent_variables[0], plan.subject_id, plan.repeated_factor, plan.fixed_factors,
        plan.alpha, plan.method_parameters, estimate_emm=plan.estimate_marginal_means,
        diagnostic_plots=plan.diagnostic_plots,
    )


def _execute_manova_core(frame: pd.DataFrame, plan: AnalysisPlan, expected_factors: int | None = None) -> StatisticalResult:
    if expected_factors is not None and len(plan.fixed_factors) != expected_factors:
        raise ValueError(f"当前方法固定需要 {expected_factors} 个因素，实际收到 {len(plan.fixed_factors)} 个")
    result = manova(
        frame, plan.dependent_variables, plan.fixed_factors, alpha=plan.alpha,
        parameters=plan.method_parameters,
        estimate_marginal_means=plan.estimate_marginal_means,
        emm_factors=plan.emm_factors, contrast_correction=plan.contrast_correction,
        diagnostic_plots=plan.diagnostic_plots,
    )
    return result


@register_executor("oneway_manova")
def execute_oneway_manova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return _execute_manova_core(frame, plan, 1)


@register_executor("twoway_manova")
def execute_twoway_manova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return _execute_manova_core(frame, plan, 2)


@register_executor("threeway_manova")
def execute_threeway_manova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    return _execute_manova_core(frame, plan, 3)


@register_executor("multifactor_manova")
def execute_multifactor_manova(frame: pd.DataFrame, plan: AnalysisPlan) -> StatisticalResult:
    order = int(plan.method_parameters.get("factor_model_order", 4))
    if order not in range(4, 9) or len(plan.fixed_factors) != order:
        raise ValueError(f"多因素 MANOVA 阶数为 {order}，必须恰好选择 {order} 个分类因素")
    return _execute_manova_core(frame, plan, order)


def list_executor_names() -> set[str]:
    """返回所有已注册执行器名称，用于启动自检和测试。"""
    return set(_EXECUTORS)
