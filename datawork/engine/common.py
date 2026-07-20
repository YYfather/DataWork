"""新增统计引擎共享工具。"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from .result import DesignInfo, VariableInfo
from datawork.core.roles import VariableRole


def numeric_frame(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = df[list(columns)].copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna()


def numeric_series(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    return values


def design_info(
    frame: pd.DataFrame,
    *,
    dependent: list[str] | None = None,
    fixed: list[str] | None = None,
    covariates: list[str] | None = None,
    random: list[str] | None = None,
    subject_id: str | None = None,
    repeated_factor: str | None = None,
) -> DesignInfo:
    dependent = dependent or []
    fixed = fixed or []
    covariates = covariates or []
    random = random or []
    variables: list[VariableInfo] = []
    for column in dependent:
        variables.append(VariableInfo(name=column, dtype=str(frame[column].dtype), role=VariableRole.DEPENDENT, n_unique=int(frame[column].nunique(dropna=True))))
    for column in fixed:
        variables.append(VariableInfo(name=column, dtype=str(frame[column].dtype), role=VariableRole.BETWEEN, levels=[str(v) for v in frame[column].dropna().unique().tolist()], n_unique=int(frame[column].nunique(dropna=True))))
    for column in covariates:
        variables.append(VariableInfo(name=column, dtype=str(frame[column].dtype), role=VariableRole.COVARIATE, n_unique=int(frame[column].nunique(dropna=True))))
    for column in random:
        variables.append(VariableInfo(name=column, dtype=str(frame[column].dtype), role=VariableRole.RANDOM, n_unique=int(frame[column].nunique(dropna=True))))
    if subject_id:
        variables.append(VariableInfo(name=subject_id, dtype=str(frame[subject_id].dtype), role=VariableRole.ID, n_unique=int(frame[subject_id].nunique(dropna=True))))
    if repeated_factor:
        variables.append(VariableInfo(name=repeated_factor, dtype=str(frame[repeated_factor].dtype), role=VariableRole.WITHIN, levels=[str(v) for v in frame[repeated_factor].dropna().unique().tolist()], n_unique=int(frame[repeated_factor].nunique(dropna=True))))
    n_subjects = int(frame[subject_id].nunique(dropna=True)) if subject_id else int(len(frame))
    return DesignInfo(
        variables=variables,
        n_subjects=n_subjects,
        n_observations=int(len(frame)),
        between_factors=fixed,
        within_factors=[repeated_factor] if repeated_factor else [],
        covariates=covariates,
        dependent_vars=dependent,
        id_column=subject_id,
        time_column=repeated_factor,
    )


def fisher_r_ci(r: float, n: int, alpha: float = 0.05) -> tuple[float | None, float | None]:
    if n <= 3 or abs(r) >= 1:
        return None, None
    z = math.atanh(r)
    se = 1 / math.sqrt(n - 3)
    critical = float(stats.norm.ppf(1 - alpha / 2))
    return math.tanh(z - critical * se), math.tanh(z + critical * se)


def describe_numeric(values: np.ndarray, *, name: str = "value") -> dict[str, float | int | str]:
    n = len(values)
    if n == 0:
        return {"variable": name, "n": 0}
    values = np.asarray(values, dtype=float)
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    standard_deviation = float(np.std(values, ddof=1)) if n > 1 else 0.0
    # SciPy 对常数或近常数数组计算偏度/峰度时会发出 precision-loss 警告并返回 NaN。
    # 描述统计不应让这种退化数据污染日志，因此在离散程度不足时返回 0，并保持其余指标可用。
    scale = max(1.0, float(np.max(np.abs(values))))
    has_shape_variation = bool(np.ptp(values) > np.finfo(float).eps * scale * 32)
    skewness = float(stats.skew(values, bias=False)) if n > 2 and has_shape_variation else 0.0
    kurtosis = float(stats.kurtosis(values, bias=False)) if n > 3 and has_shape_variation else 0.0
    if not np.isfinite(skewness):
        skewness = 0.0
    if not np.isfinite(kurtosis):
        kurtosis = 0.0
    return {
        "variable": name,
        "n": n,
        "mean": round(float(np.mean(values)), 6),
        "sd": round(standard_deviation, 6),
        "median": round(float(median), 6),
        "q1": round(float(q1), 6),
        "q3": round(float(q3), 6),
        "min": round(float(np.min(values)), 6),
        "max": round(float(np.max(values)), 6),
        "skewness": round(skewness, 6),
        "kurtosis": round(kurtosis, 6),
    }


def rank_biserial_from_u(u: float, n1: int, n2: int) -> float:
    """Mann–Whitney U 的秩双列相关，正值表示第一组整体更大。

    SciPy 返回的是第一组的 U 统计量，因此常用方向约定为
    ``r_rb = 2U/(n1*n2) - 1``。
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("秩双列相关要求两组样本量均大于 0")
    return float(2 * u / (n1 * n2) - 1)


def safe_standardized_statistic(estimate: float, standard_error: float) -> float:
    """计算 estimate / SE，并正确处理零标准误的退化情形。

    当标准误为 0 且估计值也为 0 时，统计量定义为 0；当估计值非 0 时，
    统计量趋于正/负无穷，不能错误地回退为 0。
    """
    estimate = float(estimate)
    standard_error = float(standard_error)
    if not np.isfinite(estimate) or not np.isfinite(standard_error):
        return float(estimate / standard_error)
    tolerance = np.finfo(float).eps * max(1.0, abs(estimate)) * 32
    if abs(standard_error) <= tolerance:
        if abs(estimate) <= tolerance:
            return 0.0
        return float(np.copysign(np.inf, estimate))
    return float(estimate / standard_error)


def significance(p: float, alpha: float) -> bool:
    return bool(np.isfinite(p) and p < alpha)


def safe_paired_ttest(first: Iterable[float], second: Iterable[float]) -> tuple[float, float]:
    """配对 t 检验，显式处理零差值方差，避免 SciPy 精度丢失警告。"""
    first_array = np.asarray(list(first), dtype=float)
    second_array = np.asarray(list(second), dtype=float)
    if first_array.shape != second_array.shape or first_array.size < 2:
        raise ValueError("配对 t 检验至少需要 2 对等长观测")
    difference = first_array - second_array
    mean_difference = float(np.mean(difference))
    sd_difference = float(np.std(difference, ddof=1))
    if np.isclose(sd_difference, 0.0, rtol=1e-12, atol=1e-15):
        if np.isclose(mean_difference, 0.0, rtol=1e-12, atol=1e-15):
            return 0.0, 1.0
        return float(np.copysign(np.inf, mean_difference)), 0.0
    statistic = mean_difference / (sd_difference / np.sqrt(len(difference)))
    p_value = float(2 * stats.t.sf(abs(statistic), len(difference) - 1))
    return float(statistic), p_value
