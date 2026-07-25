"""效应量计算。"""

from __future__ import annotations

import numpy as np

from .common import safe_standardized_statistic


def cohens_d(
    group1: np.ndarray,
    group2: np.ndarray,
    paired: bool = False,
    hedges_correction: bool = True,
) -> dict:
    """Cohen's d 和 Hedges' g。

    配对设计使用差值标准差（d_z），Hedges 校正使用配对自由度 n-1；
    独立组使用合并标准差和自由度 n1+n2-2。置信区间为大样本近似。
    """
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    if paired:
        if g1.shape != g2.shape:
            raise ValueError("配对效应量要求两组观测等长且一一对应")
        valid = np.isfinite(g1) & np.isfinite(g2)
        g1, g2 = g1[valid], g2[valid]
    else:
        g1 = g1[np.isfinite(g1)]
        g2 = g2[np.isfinite(g2)]

    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        raise ValueError("Cohen's d 至少需要每组 2 个有效观测")
    m1, m2 = float(np.mean(g1)), float(np.mean(g2))
    v1, v2 = float(np.var(g1, ddof=1)), float(np.var(g2, ddof=1))

    if paired:
        diff = g1 - g2
        sd_diff = float(np.std(diff, ddof=1))
        d = safe_standardized_statistic(float(np.mean(diff)), sd_diff)
        se = float(np.sqrt(1 / n1 + d**2 / (2 * n1))) if np.isfinite(d) else float("inf")
        df = n1 - 1
    else:
        df = n1 + n2 - 2
        pooled_variance = ((n1 - 1) * v1 + (n2 - 1) * v2) / df
        pooled_sd = float(np.sqrt(max(pooled_variance, 0.0)))
        d = safe_standardized_statistic(m1 - m2, pooled_sd)
        se = float(np.sqrt((n1 + n2) / (n1 * n2) + d**2 / (2 * (n1 + n2)))) if np.isfinite(d) else float("inf")

    correction = 1 - 3 / (4 * df - 1) if hedges_correction and df > 1 else 1.0
    hedges_g = float(d * correction)
    ci_lower = float(d - 1.96 * se) if np.isfinite(d) and np.isfinite(se) else float(d)
    ci_upper = float(d + 1.96 * se) if np.isfinite(d) and np.isfinite(se) else float(d)

    abs_effect = abs(hedges_g if hedges_correction else d)
    if abs_effect < 0.2:
        interp = "微小效应"
    elif abs_effect < 0.5:
        interp = "小效应"
    elif abs_effect < 0.8:
        interp = "中效应"
    else:
        interp = "大效应"

    return {
        "d": round(float(d), 4),
        "hedges_g": round(hedges_g, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "interpretation": interp,
        "df_correction": float(df),
        "ci_method": "large-sample approximation",
    }


def eta_squared(
    ss_effect: float,
    ss_total: float,
) -> dict:
    """η² = SS_effect / SS_total。"""
    eta = ss_effect / ss_total if ss_total > 0 else 0
    return _eta_interpret(eta, "η²")


def partial_eta_squared(
    ss_effect: float,
    ss_error: float,
) -> dict:
    """偏 η² = SS_effect / (SS_effect + SS_error)。"""
    eta_p = ss_effect / (ss_effect + ss_error) if (ss_effect + ss_error) > 0 else 0
    return _eta_interpret(eta_p, "η²p")


def omega_squared(
    ss_effect: float,
    ss_error: float,
    ss_total: float,
    df_effect: int,
    df_error: int,
    n: int,
) -> dict:
    """ω² (omega-squared) — 比 η² 更无偏。"""
    mse = ss_error / df_error if df_error > 0 else 0
    omega = (ss_effect - df_effect * mse) / (ss_total + mse) if (ss_total + mse) > 0 else 0
    return _eta_interpret(max(omega, 0), "ω²")


def _eta_interpret(value: float, name: str) -> dict:
    """解释 η²/η²p/ω² 的大小。"""
    if value < 0.01:
        interp = "微小效应"
    elif value < 0.06:
        interp = "小效应"
    elif value < 0.14:
        interp = "中效应"
    else:
        interp = "大效应"
    return {"measure": name, "value": round(value, 4), "interpretation": interp}
