"""批量分析引擎 — 按列拆分数据，对每个子集运行同一分析方法。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .result import StatisticalResult


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
