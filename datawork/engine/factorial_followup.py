"""析因模型的交互分层简单效应与条件内比较。"""

from __future__ import annotations

from itertools import product
from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from patsy.builtins import C as __dw_cat
from patsy.contrasts import Sum as __dw_sum
from statsmodels.formula.api import ols
from statsmodels.stats.multitest import multipletests

from .model_support import apply_posthoc_methods_to_emm, estimated_marginal_means, resolve_control_group
from .result import ContrastResult, EMMeans, SignificanceLetterGroup, SimpleEffectResult


def _factor_term(name: str, ss_type: int) -> str:
    if ss_type == 3:
        return f"__dw_cat(Q('{name}'), __dw_sum)"
    return f"__dw_cat(Q('{name}'))"


def _clean_effect(raw: str, factors: Iterable[str]) -> str:
    import re

    clean = str(raw)
    for factor in factors:
        pattern = rf"(?:C|__dw_cat)\(Q\('{re.escape(factor)}'\)(?:,\s*(?:Sum|__dw_sum))?\)"
        clean = re.sub(pattern, factor, clean)
    return clean.replace(":", " × ").strip()


def _highest_order_interactions(interactions: Iterable[Iterable[str]]) -> list[tuple[str, ...]]:
    unique = {tuple(dict.fromkeys(item)) for item in interactions if len(tuple(item)) >= 2}
    selected: list[tuple[str, ...]] = []
    for item in sorted(unique, key=lambda value: (-len(value), value)):
        item_set = set(item)
        if any(item_set < set(existing) for existing in selected):
            continue
        selected.append(item)
    return selected


def conditional_simple_effects(
    df: pd.DataFrame,
    dv_col: str,
    all_factors: list[str],
    significant_interactions: Iterable[Iterable[str]],
    *,
    alpha: float = 0.05,
    ss_type: int = 3,
    p_adjust: str = "holm",
    posthoc_methods: str | list[str] | tuple[str, ...] = "tukey",
    control_group: str | None = None,
    outcome_label: str = "",
    compare_all: bool = False,
) -> tuple[list[SimpleEffectResult], list[EMMeans], list[ContrastResult], list[SignificanceLetterGroup], list[str]]:
    """按显著交互的最高阶结构计算简单效应。

    二阶交互 A×B：分别检验 A|B 和 B|A；若模型还有第三因素 C，C 仍保留在
    条件子模型中。三阶交互 A×B×C：分别在另外两个因素的每个水平组合下检验
    剩余因素。所有简单效应 p 值按同一假设族进行校正；默认仅显著后做条件内 EMM，
    ``compare_all`` 用于预先指定的完整分支比较。
    成对比较。
    """
    if ss_type not in {1, 2, 3}:
        raise ValueError("简单效应平方和类型必须为 1、2 或 3")
    if p_adjust not in {"none", "holm", "bonferroni", "sidak", "fdr_bh"}:
        raise ValueError(f"未知简单效应校正方法: {p_adjust}")

    clean = df[[dv_col, *all_factors]].copy()
    clean[dv_col] = pd.to_numeric(clean[dv_col], errors="coerce")
    clean = clean.dropna(subset=[dv_col, *all_factors])
    for factor in all_factors:
        clean[factor] = clean[factor].astype("category")

    interactions = _highest_order_interactions(significant_interactions)
    raw_rows: list[dict[str, object]] = []
    model_cache: list[tuple[dict[str, object], object, pd.DataFrame, str, list[str]]] = []
    warnings: list[str] = []

    for interaction in interactions:
        interaction_set = set(interaction)
        for tested_factor in interaction:
            conditioners = [factor for factor in interaction if factor != tested_factor]
            levels = [list(pd.unique(clean[factor].dropna())) for factor in conditioners]
            for values in product(*levels):
                subset = clean
                condition_parts: list[str] = []
                for factor, value in zip(conditioners, values):
                    subset = subset[subset[factor] == value]
                    condition_parts.append(f"{factor}={value}")
                if subset.empty or subset[tested_factor].nunique(dropna=True) < 2:
                    continue

                # 未被固定的其他因素继续留在条件模型中，避免把第三因素的变异丢失。
                remaining = [factor for factor in all_factors if factor not in conditioners]
                subset = subset.copy()
                for factor in remaining:
                    if isinstance(subset[factor].dtype, pd.CategoricalDtype):
                        subset[factor] = subset[factor].cat.remove_unused_categories()
                rhs = " * ".join(_factor_term(factor, ss_type) for factor in remaining)
                formula = f"Q('{dv_col}') ~ {rhs}"
                try:
                    fitted = ols(formula, data=subset).fit()
                    table = sm.stats.anova_lm(fitted, typ=ss_type)
                except Exception as exc:
                    warnings.append(
                        f"{dv_col} 的简单效应 {tested_factor} | {', '.join(condition_parts)} 无法拟合：{exc}"
                    )
                    continue

                target_row = None
                for raw_effect in table.index:
                    if raw_effect == "Residual" or "Intercept" in raw_effect:
                        continue
                    if _clean_effect(raw_effect, remaining) == tested_factor:
                        target_row = raw_effect
                        break
                if target_row is None:
                    warnings.append(
                        f"{dv_col} 的条件模型未返回 {tested_factor} 主效应：{', '.join(condition_parts)}"
                    )
                    continue
                row = table.loc[target_row]
                f_value = float(row.get("F", np.nan))
                p_value = float(row.get("PR(>F)", np.nan))
                df_num = float(row.get("df", np.nan))
                df_den = float(table.loc["Residual", "df"]) if "Residual" in table.index else float(fitted.df_resid)
                if not np.all(np.isfinite([f_value, p_value, df_num, df_den])):
                    continue
                condition_label = ", ".join(condition_parts)
                effect_label = f"{tested_factor} @ {condition_label}"
                if outcome_label:
                    effect_label = f"[{outcome_label}] {effect_label}"
                record = {
                    "tested_factor": tested_factor,
                    "conditioners": conditioners,
                    "condition_label": condition_label,
                    "effect": effect_label,
                    "df_num": df_num,
                    "df_den": df_den,
                    "f_value": f_value,
                    "p_value": p_value,
                }
                raw_rows.append(record)
                model_cache.append((record, fitted, subset.copy(), tested_factor, remaining))

    if not raw_rows:
        return [], [], [], [], warnings

    raw_p = np.asarray([float(row["p_value"]) for row in raw_rows], dtype=float)
    adjusted = raw_p if p_adjust == "none" else multipletests(raw_p, alpha=alpha, method=p_adjust)[1]
    simple_effects: list[SimpleEffectResult] = []
    significant_keys: set[str] = set()
    for index, row in enumerate(raw_rows):
        p_adjusted = float(adjusted[index])
        significant = p_adjusted < alpha
        if significant:
            significant_keys.add(str(row["effect"]))
        simple_effects.append(SimpleEffectResult(
            fixed_factor=" × ".join(row["conditioners"]),
            fixed_level=str(row["condition_label"]),
            effect=str(row["effect"]),
            df_num=float(row["df_num"]),
            df_den=float(row["df_den"]),
            f_value=float(row["f_value"]),
            p_value=float(row["p_value"]),
            p_adjusted=p_adjusted,
            correction=p_adjust,
            is_significant=significant,
        ))

    emmeans_all: list[EMMeans] = []
    contrasts_all: list[ContrastResult] = []
    letters_all: list[SignificanceLetterGroup] = []

    for row, fitted, subset, tested_factor, remaining in model_cache:
        if not compare_all and str(row["effect"]) not in significant_keys:
            continue
        try:
            emmeans, raw_contrasts = estimated_marginal_means(
                fitted,
                subset,
                target_factors=[tested_factor],
                categorical_factors=remaining,
                covariates=[],
                alpha=alpha,
                correction="none",
                df_resid=float(fitted.df_resid),
            )
            adjusted_contrasts, letter_rows, method_warnings = apply_posthoc_methods_to_emm(
                emmeans,
                raw_contrasts,
                methods=posthoc_methods,
                alpha=alpha,
                factor=tested_factor,
                outcome=outcome_label or dv_col,
                context=str(row["effect"]),
                control_group=resolve_control_group(control_group, tested_factor),
                contrast_prefix=f"{row['effect']} | ",
            )
            letters_all.extend(letter_rows)
            warnings.extend(method_warnings)
        except Exception as exc:
            warnings.append(f"{row['effect']} 的条件内比较无法计算：{exc}")
            continue
        prefix = f"{row['effect']} | "
        for emm in emmeans:
            updated = emm.model_copy(deep=True)
            updated.group = prefix + updated.group
            updated.source = "显著交互后的条件简单效应 EMM"
            emmeans_all.append(updated)
        contrasts_all.extend(adjusted_contrasts)

    return simple_effects, emmeans_all, contrasts_all, letters_all, warnings
