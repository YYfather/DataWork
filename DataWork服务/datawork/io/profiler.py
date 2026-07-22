"""数据画像 — 列类型推断、缺失/异常/重复扫描。"""

from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
import re


@dataclass
class ColumnProfile:
    """单列画像。"""
    name: str
    dtype: str                     # object / int64 / float64 / bool
    n_unique: int
    n_missing: int
    missing_rate: float
    unique_values: list[str] = field(default_factory=list)  # 前 20 个唯一值
    inferred_role: str = ""        # "id" / "between" / "within" / "covariate" / "dependent" / "time" / "ignore"
    role_confidence: float = 0.0
    note: str = ""                 # 额外的推断注释


@dataclass
class DataProfile:
    """整体数据画像。"""
    file_name: str = ""
    sheet_name: str = ""
    n_rows: int = 0
    n_cols: int = 0
    columns: list[ColumnProfile] = field(default_factory=list)
    total_missing_rate: float = 0.0
    n_duplicate_rows: int = 0
    percent_columns_found: list[str] = field(default_factory=list)
    wide_to_long_hint: Optional[str] = None  # 宽格式提示


def profile_dataframe(df: pd.DataFrame, file_name: str = "", sheet_name: str = "") -> DataProfile:
    """对 DataFrame 做完整画像。"""
    df = df.copy()

    n_rows, n_cols = df.shape
    total_missing = df.isna().mean().mean()

    # 重复行
    n_dups = df.duplicated().sum()

    # 检测 % 列
    pct_cols: list[str] = []
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col].dtype):
            sample = df[col].dropna().astype(str)
            if len(sample) > 0 and sample.str.contains('%', regex=False).mean() > 0.3:
                pct_cols.append(col)

    columns: list[ColumnProfile] = []
    for col in df.columns:
        series = df[col]
        n_unique = series.nunique(dropna=True)
        n_missing = int(series.isna().sum())
        missing_r = series.isna().mean()

        # 唯一值样本
        uniq_vals = series.dropna().unique()[:20].tolist()
        uniq_vals_str = [str(v) for v in uniq_vals]

        # 推断角色
        role, confidence, note = _infer_column_role(series, col, n_unique, n_rows, missing_r)

        columns.append(ColumnProfile(
            name=col,
            dtype=str(series.dtype),
            n_unique=n_unique,
            n_missing=n_missing,
            missing_rate=round(missing_r, 4),
            unique_values=uniq_vals_str,
            inferred_role=role,
            role_confidence=confidence,
            note=note,
        ))

    # 宽格式检测：查找符合 "前缀 + 数值" 模式的一组列
    wide_hint = _detect_wide_format(columns)

    return DataProfile(
        file_name=file_name,
        sheet_name=sheet_name,
        n_rows=n_rows,
        n_cols=n_cols,
        columns=columns,
        total_missing_rate=round(total_missing, 4),
        n_duplicate_rows=n_dups,
        percent_columns_found=pct_cols,
        wide_to_long_hint=wide_hint,
    )


def _infer_column_role(
    series: pd.Series,
    col_name: str,
    n_unique: int,
    n_rows: int,
    missing_rate: float,
) -> tuple[str, float, str]:
    """基于规则推断单列的变量角色。"""
    name_lower = col_name.lower().strip()
    dtype = series.dtype

    # ---- 全空列 → ignore ----
    if missing_rate > 0.95:
        return "ignore", 0.99, "缺失率 > 95%，建议排除"

    # ---- 高缺失 → 降低置信度 ----
    if missing_rate > 0.5:
        return "dependent", 0.3, f"缺失率 {missing_rate:.0%}，建议检查"

    # ---- Unnamed 开头 → 可能是空列 ----
    if name_lower.startswith("unnamed"):
        return "ignore", 0.85, "Unnamed 列，可能为空"

    # ---- 明显 ID 列 ----
    id_keywords = ["id", "编号", "序号", "subject", "被试", "样本号", "编号", "编号", "小区编号", "plot"]
    if any(kw in name_lower for kw in id_keywords):
        if n_unique > n_rows * 0.5:   # 唯一值 > 50% 行数
            return "id", 0.9, "列名含 ID 关键词 + 高唯一性 → 疑似 ID"
        return "id", 0.6, "列名含 ID 关键词"

    # ---- 数值列 ----
    if pd.api.types.is_numeric_dtype(dtype):
        # 名称语义优先于“小样本唯一值数量”。否则 6 行、6 个不同测量值会被误判为六水平因素。
        cov_kw = ["pre", "baseline", "基线", "期中", "期初", "初始", "start", "协变量"]
        dependent_kw = [
            "value", "measurement", "response", "score", "height", "weight", "yield", "rate",
            "percent", "concentration", "index", "length", "area", "数值", "结果", "指标", "得分",
            "高度", "重量", "产量", "比率", "脱叶率", "含量", "浓度", "长度", "面积",
        ]
        factor_kw = [
            "year", "年份", "年度", "group", "组别", "treatment", "处理", "level", "水平",
            "category", "类别", "code", "编码", "repeat", "重复", "block", "区组",
        ]
        if any(kw in name_lower for kw in cov_kw):
            return "covariate", 0.65, "列名含基线/初始等关键词 → 疑似连续协变量"
        if any(kw in name_lower for kw in dependent_kw):
            return "dependent", 0.75, "列名含测量/响应指标关键词 → 疑似因变量"
        if any(kw in name_lower for kw in factor_kw) and n_unique <= 20:
            return "between", 0.7, "列名含分类因素关键词 → 疑似组间因素"
        if n_unique <= 2:
            # 0/1 或只有 2 个值 → 可能是二分类变量；最终角色仍由用户确认。
            return "between", 0.55, "数值列仅 2 个水平 → 可能为类别因素"
        low_cardinality_limit = max(3, int(n_rows * 0.25))
        if 2 < n_unique <= 10 and n_unique <= low_cardinality_limit:
            return "between", 0.45, "相对样本量取值较少 → 可能为有序/类别因素"
        return "dependent", 0.65, "数值变化相对连续 → 疑似因变量"

    # ---- 字符串/类别列 ----
    if n_unique == 1:
        return "ignore", 0.9, "仅 1 个唯一值，无分析意义"

    if n_unique == n_rows:
        # 完全唯一 → 可能是 ID 或文本
        return "id", 0.6, "完全唯一 → 疑似 ID"

    if n_unique <= 15:
        # 类别变量关键词
        factor_kw = ["处理", "品种", "性别", "方法", "组别", "地点", "年份",
                      "区组", "重复", "treatment", "variety", "cultivar",
                      "method", "group", "gender", "time", "时间", "模式",
                      "喷施", "种植", "年份", "年度"]
        if any(kw in name_lower for kw in factor_kw):
            return "between", 0.8, "列名含因素关键词 + 少量水平 → 组间因素"
        # 时间关键词
        time_kw = ["时间", "时期", "阶段", "time", "period", "day", "d", "week", "w"]
        if any(kw in name_lower for kw in time_kw):
            return "time", 0.7, "列名含时间关键词 → 疑似时间变量"
        # 标签列：中等基数、非数值、不含因素关键词
        label_kw = ["名称", "标签", "label", "name", "组名", "类别", "分组", "类型", "描述"]
        if any(kw in name_lower for kw in label_kw) or n_unique <= 8:
            return "label", 0.55, f"中等基数 → 可能是标签/分组列"
        return "between", 0.6, f"仅 {n_unique} 个水平 → 疑似类别因素"

    # 非常多的唯一值 + 字符串 → 可能是 ID 或备注
    if n_unique > 15:
        return "id", 0.35, "高唯一值字符串 → 可能是 ID/备注/自由文本"

    return "ignore", 0.1, "无法推断角色"


def _detect_wide_format(columns: list[ColumnProfile]) -> Optional[str]:
    """
    检测是否需要在宽格式中转换。
    
    查找模式: "XdYYY" 或 "YYY_Xd" 或 "YYY d X" 风格的列名组。
    例如: "7d脱叶率", "14d脱叶率", "21d脱叶率" → 时间变量
    """
    # 简单启发式：寻找多个列名以连续数值开头的模式
    numeric_prefix = []
    for col in columns:
        m = re.match(r'^(\d+)\s*[d天D]', col.name)
        if m:
            numeric_prefix.append((col.name, int(m.group(1)), m.group(0)))

    if len(numeric_prefix) >= 2:
        # 提取共同的 stem
        names = [np[0] for np in numeric_prefix]
        stems = set()
        for name, num, prefix in numeric_prefix:
            stem = name[len(prefix):]  # 去除前缀后的部分
            stems.add(stem)
        if len(stems) == 1:
            stem = stems.pop()
            time_values = sorted(set(np[1] for np in numeric_prefix))
            return (f"检测到宽格式时间列: {names}"
                    f"，建议转为长格式 (Time: {time_values}, Value: {stem})")
    return None
