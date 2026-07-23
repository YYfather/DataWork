"""假设检验诊断 — Shapiro-Wilk, Levene, Mauchly, Box's M。"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import numpy as np
from scipy import stats


@dataclass
class AssumptionResult:
    """一次假设检验的结果。"""
    test_name: str
    statistic: float
    p_value: float
    passed: bool
    detail: str


def test_normality(data: pd.Series | np.ndarray, alpha: float = 0.05) -> AssumptionResult:
    """Shapiro-Wilk 正态性检验。"""
    # 去除 NaN
    arr = pd.Series(data).dropna().to_numpy()
    if len(arr) < 3:
        return AssumptionResult("Shapiro-Wilk", np.nan, np.nan, False,
                                f"样本量 {len(arr)} < 3，无法检验")
    scale = max(1.0, float(np.max(np.abs(arr))))
    if float(np.ptp(arr)) <= np.finfo(float).eps * scale * 32:
        return AssumptionResult(
            "Shapiro-Wilk", 0.0, 0.0, False,
            "数据为常数，正态性检验无定义；应先检查零方差。",
        )
    if len(arr) > 5000:
        # scipy Shapiro-Wilk 不支持 > 5000 样本
        stat, p = stats.normaltest(arr)  # D'Agostino's K-squared
        return AssumptionResult(
            "D'Agostino K²", stat, p,
            p > alpha,
            f"D'Agostino K² (Shapiro-Wilk 替代, 因 n={len(arr)} > 5000)"
        )
    stat, p = stats.shapiro(arr)
    return AssumptionResult(
        "Shapiro-Wilk", stat, p,
        p > alpha,
        "正态性满足" if p > alpha else "偏离正态分布"
    )


def test_normality_groups(
    df: pd.DataFrame,
    dv_col: str,
    group_cols: list[str],
    alpha: float = 0.05,
) -> list[dict]:
    """在每个分组下检验正态性。"""
    results = []
    groups = df.groupby(group_cols, dropna=True, observed=True)
    for group_keys, group_df in groups:
        if isinstance(group_keys, tuple):
            group_label = ", ".join(str(k) for k in group_keys)
        else:
            group_label = str(group_keys)
        arr = group_df[dv_col].dropna()
        if len(arr) < 3:
            results.append({"group": group_label, "n": len(arr),
                            "test": "Shapiro-Wilk", "statistic": np.nan,
                            "p_value": np.nan, "passed": False,
                            "detail": f"n={len(arr)} < 3"})
            continue
        values = arr.to_numpy(dtype=float)
        scale = max(1.0, float(np.max(np.abs(values))))
        if float(np.ptp(values)) <= np.finfo(float).eps * scale * 32:
            results.append({
                "group": group_label, "n": len(arr), "test": "Shapiro-Wilk",
                "statistic": 0.0, "p_value": 0.0, "passed": False,
                "detail": "组内数据为常数，正态性检验无定义；应检查零方差。",
            })
            continue
        if len(arr) > 5000:
            stat, p = stats.normaltest(arr)
            test_name = "D'Agostino K²"
        else:
            stat, p = stats.shapiro(arr)
            test_name = "Shapiro-Wilk"
        results.append({
            "group": group_label, "n": len(arr),
            "test": test_name, "statistic": round(stat, 4),
            "p_value": round(p, 4),
            "passed": p > alpha,
            "detail": "正态性满足" if p > alpha else "偏离正态分布",
        })
    return results


def test_homogeneity(
    df: pd.DataFrame,
    dv_col: str,
    group_col: str,
    center: str = "median",
    alpha: float = 0.05,
) -> AssumptionResult:
    """Levene 方差齐性检验。"""
    groups = df.groupby(group_col, dropna=True)
    group_data = []
    for _, gdf in groups:
        arr = gdf[dv_col].dropna().to_numpy()
        if len(arr) > 0:
            group_data.append(arr)

    if len(group_data) < 2:
        return AssumptionResult("Levene", np.nan, np.nan, False, "分组不足 2 个")

    variances = [float(np.var(values, ddof=1)) if len(values) > 1 else 0.0 for values in group_data]
    if all(np.isclose(value, 0.0, rtol=1e-12, atol=1e-15) for value in variances):
        return AssumptionResult(
            "Levene", 0.0, 1.0, True,
            "各组组内方差均为 0；方差数值相同，但数据为退化常数，应结合模型零误差结果解释。",
        )
    stat, p = stats.levene(*group_data, center=center)
    return AssumptionResult(
        "Levene", stat, p,
        p > alpha,
        "方差齐性满足" if p > alpha else "方差不齐"
    )


def test_homogeneity_two_factor(
    df: pd.DataFrame,
    dv_col: str,
    factor_a: str,
    factor_b: str,
    alpha: float = 0.05,
) -> AssumptionResult:
    """双因素方差齐性检验—按所有组合分组。"""
    df_copy = df.copy()
    df_copy["_combo"] = df_copy[factor_a].astype(str) + " × " + df_copy[factor_b].astype(str)
    return test_homogeneity(df_copy, dv_col, "_combo", alpha=alpha)


def test_sphericity_mauchly(
    df: pd.DataFrame,
    dv_cols: list[str],
    id_col: str = "",
    alpha: float = 0.05,
) -> dict:
    """兼容入口：委托给唯一的 Mauchly/GG/HF 计算核心。

    ``id_col`` 保留用于旧调用兼容；宽格式下每行已经代表一个对象。
    """
    del id_col
    from .model_support import sphericity_result

    wide = df[dv_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(wide) < 3:
        return {
            "W": np.nan, "chi2": np.nan, "df": np.nan, "p_value": np.nan,
            "passed": False, "GG_epsilon": np.nan, "HF_epsilon": np.nan,
            "detail": "完整对象少于 3，无法计算球形性诊断",
        }
    result = sphericity_result(wide, alpha)
    if result is None:
        return {
            "W": 1.0, "chi2": 0.0, "df": 0.0, "p_value": 1.0,
            "passed": True, "GG_epsilon": 1.0, "HF_epsilon": 1.0,
            "detail": "两个重复水平时球形性恒成立。",
        }
    return {
        "W": round(float(result.statistic), 6),
        "chi2": round(float(result.chi_square), 6),
        "df": float(result.df),
        "p_value": round(float(result.p_value), 6),
        "passed": bool(result.passed),
        "GG_epsilon": round(float(result.epsilon_gg), 6),
        "HF_epsilon": round(float(result.epsilon_hf), 6),
        "detail": result.detail,
    }
