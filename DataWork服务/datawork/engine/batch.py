"""批量分析引擎 — 按列拆分数据，对每个子集运行同一分析方法。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .ttest import independent_ttest
from .oneway_anova import oneway_anova
from .twoway_anova import twoway_anova
from .result import StatisticalResult, MultiDVResult


@dataclass
class BatchResult:
    """单次批量分析的一个子集结果。"""
    subset_key: str                       # "T1, 7d"
    subset_info: dict[str, str]           # {脱叶剂喷施时间: T1, 调查时间: 7d}
    n_rows: int
    omnibus_tests: list[dict]             # 兼容旧字段
    records: list[dict] = field(default_factory=list)  # 通用长表记录
    error: str = ""
    result: StatisticalResult | None = None  # 保留完整单次结果，供逐批展示与分表导出


@dataclass
class BatchAnalysisResult:
    """批量分析的完整结果。"""
    split_cols: list[str]
    method: str
    dv_col: str
    factor_cols: list[str]
    results: list[BatchResult] = field(default_factory=list)
    summary_df: Optional[pd.DataFrame] = None
    overview_df: Optional[pd.DataFrame] = None
    settings: dict = field(default_factory=dict)


def batch_anova(
    df: pd.DataFrame,
    dv_col: str,
    factor_cols: list[str],
    split_cols: list[str],
    method: str = "twoway_anova",
    alpha: float = 0.05,
    ss_type: int = 3,
) -> BatchAnalysisResult:
    """
    按 split_cols 拆分数据，对每个子集运行指定的方差分析。

    Args:
        df: 数据框
        dv_col: 因变量列
        factor_cols: 因素列（如 ["品种", "种植模式"]）
        split_cols: 拆分列（如 ["脱叶剂喷施时间", "调查时间"]）
        method: 支持 welch_ttest / independent_ttest / oneway_anova / welch_anova / twoway_anova
        alpha: 显著性水平
        ss_type: 多因素 ANOVA 的平方和类型

    Returns:
        BatchAnalysisResult 包含所有子集的结果和汇总表
    """
    df_clean = df.dropna(subset=[dv_col] + factor_cols + split_cols).copy()

    results: list[BatchResult] = []

    # 按拆分列分组
    groups = df_clean.groupby(split_cols, dropna=True)

    for group_keys, sub_df in groups:
        if isinstance(group_keys, tuple):
            key_str = ", ".join(str(k) for k in group_keys)
            key_info = {split_cols[i]: str(group_keys[i]) for i in range(len(split_cols))}
        else:
            key_str = str(group_keys)
            key_info = {split_cols[0]: str(group_keys)}

        if len(sub_df) < 6:  # 样本量太小
            results.append(BatchResult(
                subset_key=key_str, subset_info=key_info,
                n_rows=len(sub_df), omnibus_tests=[],
                error=f"样本量不足 ({len(sub_df)} rows)",
            ))
            continue

        try:
            if method == "twoway_anova" and len(factor_cols) == 2:
                r = twoway_anova(
                    sub_df, dv_col, factor_cols[0], factor_cols[1],
                    alpha=alpha, ss_type=ss_type,
                )
            elif method == "oneway_anova" and len(factor_cols) == 1:
                r = oneway_anova(sub_df, dv_col, factor_cols[0], alpha=alpha)
            elif method == "welch_anova" and len(factor_cols) == 1:
                r = oneway_anova(sub_df, dv_col, factor_cols[0], welch=True, alpha=alpha)
            elif method in {"welch_ttest", "independent_ttest", "ttest"} and len(factor_cols) == 1:
                equal_var = method == "independent_ttest"
                r = independent_ttest(
                    sub_df[dv_col], sub_df[factor_cols[0]], dv_col, factor_cols[0],
                    equal_var=equal_var, alpha=alpha,
                )
            else:
                results.append(BatchResult(
                    subset_key=key_str, subset_info=key_info,
                    n_rows=len(sub_df), omnibus_tests=[],
                    error=f"不支持的方法: {method}",
                ))
                continue

            tests = []
            for ot in r.omnibus_tests:
                tests.append({
                    "effect": ot.effect,
                    "F": round(ot.f_value, 3),
                    "df_num": ot.df_num,
                    "df_den": ot.df_den,
                    "p": round(ot.p_value, 4),
                    "eta_sq_p": round(ot.eta_sq_p, 4),
                    "significant": ot.is_significant,
                })

            results.append(BatchResult(
                subset_key=key_str, subset_info=key_info,
                n_rows=len(sub_df), omnibus_tests=tests,
            ))

        except Exception as e:
            results.append(BatchResult(
                subset_key=key_str, subset_info=key_info,
                n_rows=len(sub_df), omnibus_tests=[],
                error=str(e)[:100],
            ))

    # 构建汇总表
    summary = _build_batch_summary(results, split_cols)

    return BatchAnalysisResult(
        split_cols=split_cols,
        method=method,
        dv_col=dv_col,
        factor_cols=factor_cols,
        results=results,
        summary_df=summary,
    )


def _build_batch_summary(
    results: list[BatchResult],
    split_cols: list[str],
) -> pd.DataFrame:
    """构建通用长表汇总；兼容旧 ANOVA 宽表记录。"""
    rows: list[dict] = []
    for batch_result in results:
        base = dict(batch_result.subset_info)
        base["n"] = batch_result.n_rows
        if batch_result.error:
            rows.append({**base, "result_type": "error", "error": batch_result.error})
            continue
        if batch_result.records:
            for record in batch_result.records:
                rows.append({**base, **record})
            continue
        if batch_result.omnibus_tests:
            for test in batch_result.omnibus_tests:
                rows.append({
                    **base,
                    "result_type": "test",
                    "effect": test.get("effect", ""),
                    "statistic_name": test.get("statistic_name", "F"),
                    "statistic_value": test.get("statistic_value", test.get("F")),
                    "df_num": test.get("df_num"),
                    "df_den": test.get("df_den"),
                    "p_value": test.get("p"),
                    "effect_size_name": test.get("effect_size_name", "eta_sq_p"),
                    "effect_size_value": test.get("effect_size_value", test.get("eta_sq_p")),
                    "significant": test.get("significant"),
                })
        else:
            rows.append({**base, "result_type": "completed"})
    frame = pd.DataFrame(rows)
    sort_cols = [column for column in split_cols if column in frame.columns]
    if sort_cols:
        frame = frame.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    return frame


def _fmt_p(p: float) -> str:
    if p < 0.001:
        return "<.001"
    elif p < 0.01:
        return f"{p:.3f}"
    else:
        return f"{p:.4f}"


def derive_variable(
    df: pd.DataFrame,
    new_col: str,
    formula: str,
) -> pd.DataFrame:
    """从现有列安全派生新变量。

    仅允许列名、数值、括号以及 ``+ - * / ** %``。函数调用、属性访问、
    下标和任何 Python 语句都会被拒绝。
    """
    from datawork.core.formula import evaluate_formula

    if not new_col or not str(new_col).strip():
        raise ValueError("新变量名不能为空")
    if new_col in df.columns:
        raise ValueError(f"列 {new_col!r} 已存在")

    result = df.copy()
    result[new_col] = evaluate_formula(result, formula)
    return result


def analyze_multi_dv(
    df: pd.DataFrame,
    dv_cols: list[str],
    between_cols: list[str],
    method: str = "twoway_anova",
    alpha: float = 0.05,
) -> MultiDVResult:
    """
    对多个因变量运行同一分析方法，返回汇总结果。

    Args:
        df: 数据框
        dv_cols: 多个因变量列名
        between_cols: 因素列 (至少 2 个用于 twoway_anova)
        method: 支持 welch_ttest / independent_ttest / oneway_anova / welch_anova / twoway_anova
        alpha: 显著性水平
        ss_type: 多因素 ANOVA 的平方和类型
    """
    method_labels = {
        "twoway_anova": "双因素方差分析",
        "oneway_anova": "单因素方差分析",
        "ttest": "独立样本 t 检验",
    }

    results: list[StatisticalResult] = []

    for dv in dv_cols:
        df_clean = df.dropna(subset=[dv] + between_cols)
        if len(df_clean) < 6:
            continue

        try:
            if method == "twoway_anova" and len(between_cols) >= 2:
                r = twoway_anova(df_clean, dv, between_cols[0], between_cols[1], alpha=alpha)
            elif method == "oneway_anova":
                r = oneway_anova(df_clean, dv, between_cols[0], alpha=alpha)
            elif method == "ttest":
                r = independent_ttest(
                    df_clean[dv], df_clean[between_cols[0]], dv, between_cols[0]
                )
            else:
                continue
            r.method.research_question = dv
            results.append(r)
        except Exception:
            continue

    return MultiDVResult(
        dv_results=results,
        method_name=method,
        method_label=method_labels.get(method, method),
        factor_cols=between_cols,
    )
