"""跨平台数据读取与保守清洗。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import csv
import re

import pandas as pd


_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
_UNNAMED_RE = re.compile(r"^\s*unnamed\s*:\s*\d+\s*$", re.IGNORECASE)


def read_file(path: str | Path, sheet_name: Optional[str | int] = None) -> dict[str, pd.DataFrame]:
    """读取数据文件并返回 ``{工作表名: DataFrame}``。"""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        df = _read_delimited(path)
        return {_clean_sheet_name(path.stem): df}

    if suffix == ".xlsx":
        return _read_excel(path, sheet_name=sheet_name, engine="openpyxl")

    if suffix == ".xls":
        try:
            import xlrd  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "读取旧版 .xls 需要可选依赖 xlrd。请执行: pip install 'datawork[legacy-excel]'，"
                "或先在 Excel 中另存为 .xlsx。"
            ) from exc
        return _read_excel(path, sheet_name=sheet_name, engine="xlrd")

    raise ValueError(f"不支持的文件格式: {suffix}；支持 .csv/.tsv/.txt/.xlsx/.xls")


def _read_delimited(path: Path) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in _CSV_ENCODINGS:
        try:
            sample = path.read_text(encoding=encoding)[:65536]
            delimiter = _detect_delimiter(sample, path.suffix.lower())
            return pd.read_csv(path, encoding=encoding, sep=delimiter, engine="python")
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except (pd.errors.ParserError, csv.Error) as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError("无法识别文本文件编码或分隔符。尝试过: " + "; ".join(errors[-3:]))


def _detect_delimiter(sample: str, suffix: str) -> str:
    """只在常见安全分隔符中探测，避免单列数值里的小数点/负号被误判为分隔符。"""
    non_empty_lines = [line for line in sample.splitlines() if line.strip()]
    probe = "\n".join(non_empty_lines[:50])
    if not probe:
        return "\t" if suffix == ".tsv" else ","
    try:
        return csv.Sniffer().sniff(probe, delimiters=",;\t|").delimiter
    except csv.Error:
        # 无候选分隔符通常意味着这是合法的单列文件，而不是解析失败。
        return "\t" if suffix == ".tsv" else ","


def _read_excel(path: Path, sheet_name: Optional[str | int], engine: str) -> dict[str, pd.DataFrame]:
    with pd.ExcelFile(path, engine=engine) as workbook:
        available = workbook.sheet_names
        if sheet_name is not None:
            if isinstance(sheet_name, str) and sheet_name not in available:
                raise ValueError(f"工作表 {sheet_name!r} 不存在；可选: {available}")
            frame = pd.read_excel(workbook, sheet_name=sheet_name)
            selected_name = available[sheet_name] if isinstance(sheet_name, int) else sheet_name
            return {str(selected_name): frame}

        result: dict[str, pd.DataFrame] = {}
        for name in available:
            frame = pd.read_excel(workbook, sheet_name=name)
            if frame.empty or frame.dropna(how="all").empty:
                continue
            result[str(name)] = frame
        return result or {_clean_sheet_name(path.stem): pd.DataFrame()}


def _clean_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name).strip("_")
    return cleaned or "sheet"


def _normalise_empty_cells(df: pd.DataFrame) -> pd.DataFrame:
    """把只含空白字符的字符串视为缺失值，但不改动普通文本。"""
    result = df.copy()
    object_columns = result.select_dtypes(include=["object", "string"]).columns
    for column in object_columns:
        result[column] = result[column].map(
            lambda value: pd.NA if isinstance(value, str) and not value.strip() else value
        )
    return result


def inspect_excluded_columns(df: pd.DataFrame) -> list[dict[str, Any]]:
    """返回将在清洗阶段被排除的空列或占位列信息。

    空标题 CSV 列通常会被 pandas 命名为 ``Unnamed: n``。即使其中夹杂一两个
    误填字符，也应视为占位列并排除，同时通过 ``non_empty_cells`` 留下审计信息。
    """
    normalised = _normalise_empty_cells(df)
    report: list[dict[str, Any]] = []
    for column in normalised.columns:
        name = str(column).strip()
        series = normalised[column]
        non_empty = int(series.notna().sum())
        if not name or _UNNAMED_RE.match(name):
            report.append({
                "name": str(column),
                "reason": "blank_or_unnamed_header",
                "non_empty_cells": non_empty,
            })
        elif non_empty == 0:
            report.append({
                "name": str(column),
                "reason": "all_empty",
                "non_empty_cells": 0,
            })
    return report


def clean_dataframe(df: pd.DataFrame, *, fill_merged_like_cells: bool = False) -> pd.DataFrame:
    """执行保守清洗，并彻底排除空标题、Unnamed 和全空列。

    默认不会按低基数启发式前向填充缺失值。只有调用方明确选择时才启用旧行为。
    """
    result = _normalise_empty_cells(df)
    excluded = {item["name"] for item in inspect_excluded_columns(result)}
    if excluded:
        result = result.drop(columns=[column for column in result.columns if str(column) in excluded])

    result = result.dropna(how="all").reset_index(drop=True)
    result = result.dropna(axis=1, how="all")
    result.columns = [str(column).strip() for column in result.columns]

    if fill_merged_like_cells:
        result = _auto_fill_merged(result)
    return result


def _auto_fill_merged(df: pd.DataFrame) -> pd.DataFrame:
    """兼容旧流程的启发式前向填充；必须由调用方显式启用。"""
    result = df.copy()
    for column in result.columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            continue
        n_total = len(result)
        n_unique = result[column].nunique(dropna=True)
        if n_total and 2 <= n_unique < n_total * 0.3:
            result[column] = result[column].ffill()
    return result


def detect_label_columns(df: pd.DataFrame) -> list[str]:
    label_cols: list[str] = []
    n_total = len(df)
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            continue
        n_unique = df[column].nunique(dropna=True)
        if 2 <= n_unique <= 30 and n_unique < n_total * 0.5:
            factor_keywords = ["处理", "品种", "方法", "组别", "treatment", "method", "group"]
            if not any(keyword in str(column).lower() for keyword in factor_keywords):
                label_cols.append(column)
    return label_cols


def detect_percentage_columns(df: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in df.columns:
        if df[column].dtype == object or pd.api.types.is_string_dtype(df[column].dtype):
            sample = df[column].dropna().astype(str)
            if len(sample) and sample.str.contains("%", regex=False).mean() > 0.3:
                columns.append(column)
    return columns


def auto_clean_percentage(
    df: pd.DataFrame,
    *,
    scale: str = "percent_points",
) -> tuple[pd.DataFrame, list[str]]:
    """把百分号文本转为数值。"""
    if scale not in {"percent_points", "proportion"}:
        raise ValueError("scale 必须为 'percent_points' 或 'proportion'")
    columns = detect_percentage_columns(df)
    result = df.copy()
    for column in columns:
        values = result[column].astype(str).str.replace("%", "", regex=False)
        result[column] = pd.to_numeric(values, errors="coerce")
        if scale == "proportion":
            result[column] = result[column] / 100.0
    return result, columns


def wide_to_long(
    df: pd.DataFrame,
    stubnames: list[str],
    id_vars: list[str],
    time_values: Optional[list] = None,
    time_name: str = "time",
    value_name: str = "value",
) -> pd.DataFrame:
    result = df.copy()
    result["_temp_id"] = range(len(result))
    return pd.wide_to_long(
        result,
        stubnames=stubnames,
        i="_temp_id",
        j=time_name,
        sep="",
        suffix=r".+",
    ).reset_index(drop=True)
