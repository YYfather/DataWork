"""四至八因素对象间方差分析。"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.formula.api import ols

from .model_support import estimated_marginal_means, regression_diagnostic_plots
from .result import (
    DesignInfo,
    DiagnosticResult,
    EffectSize,
    MethodInfo,
    OmnibusTest,
    StatisticalResult,
    VariableInfo,
    VariableRole,
)


def multiway_anova(
    df: pd.DataFrame,
    dv_col: str,
    factor_cols: list[str],
    *,
    alpha: float = 0.05,
    ss_type: int = 3,
    emm_factors: list[str] | None = None,
    contrast_correction: str = "holm",
    diagnostic_plots: bool = True,
) -> StatisticalResult:
    """拟合 4–8 个分类因素的完整析因 ANOVA。"""

    factors = list(dict.fromkeys(factor_cols))
    if not 4 <= len(factors) <= 8:
        raise ValueError("多因素方差分析需要 4–8 个互不重复的分类因素")
    if ss_type not in {1, 2, 3}:
        raise ValueError("ss_type 必须为 1、2 或 3")
    required = [dv_col, *factors]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"数据中缺少分析列: {missing}")

    clean = df[required].copy()
    clean[dv_col] = pd.to_numeric(clean[dv_col], errors="coerce")
    clean = clean.dropna(subset=required)
    if clean.empty:
        raise ValueError("删除缺失值后没有可用于多因素方差分析的观测")
    for factor in factors:
        clean[factor] = clean[factor].astype("category")
        if clean[factor].nunique() < 2:
            raise ValueError(f"因素 {factor} 至少需要两个有效水平")

    rename_map = {dv_col: "DV", **{factor: f"F{index + 1}" for index, factor in enumerate(factors)}}
    reverse_map = {safe: original for original, safe in rename_map.items()}
    safe = clean.rename(columns=rename_map)
    safe_factors = [rename_map[factor] for factor in factors]
    contrast = "Sum" if ss_type == 3 else "Treatment"
    terms = [f"C({factor}, Sum)" if ss_type == 3 else f"C({factor})" for factor in safe_factors]
    formula = f"DV ~ {' * '.join(terms)}"
    model = ols(formula, data=safe).fit()
    rank = int(np.linalg.matrix_rank(model.model.exog))
    columns = int(model.model.exog.shape[1])
    if rank < columns:
        raise RuntimeError(
            f"完整 {len(factors)} 因素模型不可估计：设计矩阵秩为 {rank}，参数列为 {columns}。"
            "请检查空单元、完全混杂或减少因素阶数。"
        )
    if model.df_resid <= 0:
        raise RuntimeError(
            f"完整 {len(factors)} 因素模型没有剩余自由度；至少需要在因素组合内保留重复观测。"
        )
    try:
        table = sm.stats.anova_lm(model, typ=ss_type)
    except Exception as exc:
        raise RuntimeError(f"Type {ss_type} 多因素 ANOVA 拟合失败，未切换其他平方和类型: {exc}") from exc

    residual_ss = float(table.loc["Residual", "sum_sq"])
    residual_df = float(table.loc["Residual", "df"])
    total_ss = float(np.sum((clean[dv_col] - clean[dv_col].mean()) ** 2))
    residual_ms = residual_ss / residual_df
    omnibus: list[OmnibusTest] = []
    effect_sizes: list[EffectSize] = []
    for raw_effect in table.index:
        if raw_effect == "Residual" or "Intercept" in raw_effect:
            continue
        row = table.loc[raw_effect]
        if not np.isfinite(row.get("F", np.nan)) or not np.isfinite(row.get("PR(>F)", np.nan)):
            raise RuntimeError(f"效应 {raw_effect} 无法获得有限的 F 或 p 值；完整模型不可稳定估计")
        effect = _display_effect(raw_effect, reverse_map)
        effect_ss = float(row["sum_sq"])
        effect_df = float(row["df"])
        eta_sq = effect_ss / total_ss if total_ss > 0 else 0.0
        eta_sq_p = effect_ss / (effect_ss + residual_ss) if effect_ss + residual_ss > 0 else 0.0
        omega_sq = max(0.0, (effect_ss - effect_df * residual_ms) / (total_ss + residual_ms)) if total_ss > 0 else 0.0
        p_value = float(row["PR(>F)"])
        omnibus.append(OmnibusTest(
            effect=effect,
            ss_type=ss_type,
            df_num=effect_df,
            df_den=residual_df,
            f_value=float(row["F"]),
            p_value=p_value,
            eta_sq=eta_sq,
            eta_sq_p=eta_sq_p,
            omega_sq=omega_sq,
            is_significant=p_value < alpha,
            significance_level=alpha,
        ))
        effect_sizes.append(EffectSize(measure=f"η²p ({effect})", value=eta_sq_p, interpretation=_eta_label(eta_sq_p)))

    diagnostics: list[DiagnosticResult] = []
    residuals = np.asarray(model.resid, dtype=float)
    if len(residuals) >= 3:
        sample = residuals[:5000]
        statistic, p_value = stats.shapiro(sample)
        diagnostics.append(DiagnosticResult(
            test_name="Shapiro–Wilk 残差正态性检验",
            statistic=float(statistic), p_value=float(p_value), passed=bool(p_value >= alpha),
            detail="样本超过 5000 时使用前 5000 个残差；大样本应同时结合 Q-Q 图。",
        ))
    groups = [subset[dv_col].to_numpy(dtype=float) for _, subset in clean.groupby(factors, observed=True) if len(subset) >= 2]
    if len(groups) >= 2:
        statistic, p_value = stats.levene(*groups, center="median")
        diagnostics.append(DiagnosticResult(
            test_name="Levene 方差齐性检验（完整因素单元）",
            statistic=float(statistic), p_value=float(p_value), passed=bool(p_value >= alpha),
            detail=f"基于 {len(groups)} 个具有重复观测的设计单元。",
        ))

    group_rows: list[dict[str, object]] = []
    grouped = clean.groupby(factors, observed=True)[dv_col]
    for key, values in grouped:
        levels = key if isinstance(key, tuple) else (key,)
        row: dict[str, object] = {factor: str(level) for factor, level in zip(factors, levels)}
        row.update({"n": int(values.count()), "mean": float(values.mean()), "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0})
        group_rows.append(row)

    emmeans = []
    contrasts = []
    requested = [factor for factor in (emm_factors or []) if factor in factors]
    if requested:
        safe_targets = [rename_map[factor] for factor in requested]
        emmeans, contrasts = estimated_marginal_means(
            model, safe, target_factors=safe_targets, categorical_factors=safe_factors,
            covariates=[], alpha=alpha, correction=contrast_correction, df_resid=residual_df,
        )
        for item in emmeans:
            item.group = _restore_names(item.group, reverse_map)
            item.levels = {reverse_map.get(key, key): value for key, value in item.levels.items()}
        for item in contrasts:
            item.contrast = _restore_names(item.contrast, reverse_map)

    significant_interactions = [item.effect for item in omnibus if item.is_significant and "×" in item.effect]
    warnings = [
        f"当前为 {len(factors)} 因素完整析因 ANOVA，共检验 {len(omnibus)} 个主效应与交互效应；解释应从最高阶显著交互开始。",
        "高阶析因模型对样本量、空单元和完全混杂非常敏感；通过可估计性检查不代表所有高阶效应都具有足够检验效能。",
    ]
    if significant_interactions:
        highest = max(significant_interactions, key=lambda item: item.count("×"))
        warnings.append(f"检测到显著交互，最高阶为 {highest}；涉及因素的主效应不得脱离条件水平单独解释。")

    level_counts = {factor: int(clean[factor].nunique()) for factor in factors}
    theoretical_cells = int(np.prod(list(level_counts.values())))
    observed_cells = int(clean.groupby(factors, observed=True).ngroups)
    plots = regression_diagnostic_plots(model.fittedvalues, model.resid) if diagnostic_plots else []
    variables = [VariableInfo(name=dv_col, dtype="float64", role=VariableRole.DEPENDENT, n_unique=int(clean[dv_col].nunique()))]
    variables.extend(VariableInfo(name=factor, dtype="category", role=VariableRole.BETWEEN, levels=[str(v) for v in clean[factor].cat.categories], n_unique=level_counts[factor]) for factor in factors)
    return StatisticalResult(
        analysis_id=f"multifactor_anova_{len(factors)}",
        design=DesignInfo(variables=variables, n_subjects=len(clean), n_observations=len(clean), between_factors=factors, dependent_vars=[dv_col]),
        method=MethodInfo(
            name="multifactor_anova", label_zh=f"{len(factors)} 因素方差分析（Type {ss_type} SS）",
            formula=f"{dv_col} ~ {' * '.join(factors)}",
            software="statsmodels OLS ANOVA",
            research_question=f"{dv_col} 是否受 {' × '.join(factors)} 的主效应与交互作用影响",
            assumptions=["观测独立", "完整析因模型可估计", "残差近似正态", "设计单元方差近似相等"],
            report_constraints=["优先报告最高阶交互，再依次报告低阶交互和主效应。", "显著交互涉及的主效应只能结合条件效应解释。"],
        ),
        diagnostics=diagnostics, diagnostic_plots=plots, omnibus_tests=omnibus,
        effect_sizes=effect_sizes, estimated_marginal_means=emmeans, contrasts=contrasts,
        warnings=warnings, report_constraints=["高阶交互应优先于低阶效应解释。"], descriptive_stats=group_rows,
        data_snapshot={"n_total": len(clean), "factor_count": len(factors), "factor_levels": level_counts, "theoretical_cells": theoretical_cells, "observed_cells": observed_cells, "model_rank": rank, "model_columns": columns},
        provenance={"ss_type": ss_type, "formula": formula, "contrast": contrast, "factor_order": len(factors)},
    )


def _display_effect(raw: str, reverse_map: dict[str, str]) -> str:
    clean = raw
    for safe, original in reverse_map.items():
        clean = re.sub(rf"C\({re.escape(safe)}(?:,\s*Sum)?\)", original, clean)
    return clean.replace(":", " × ").strip()


def _restore_names(text: str, reverse_map: dict[str, str]) -> str:
    restored = text
    for safe, original in reverse_map.items():
        restored = restored.replace(safe, original)
    return restored


def _eta_label(value: float) -> str:
    if value < 0.01:
        return "微小效应"
    if value < 0.06:
        return "小效应"
    if value < 0.14:
        return "中效应"
    return "大效应"
