"""受限的派生变量表达式计算器。"""

from __future__ import annotations

import ast
import operator
import re
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from .plan import DerivedColumn


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class UnsafeFormulaError(ValueError):
    """表达式包含不允许的语法。"""


_BRACKET_REFERENCE = re.compile(r"\[([^\[\]]+)\]")


def formula_references(formula: str) -> list[str]:
    """返回可视化公式编辑器生成的 ``[列名]`` 引用，保持首次出现顺序。"""
    return list(dict.fromkeys(match.group(1).strip() for match in _BRACKET_REFERENCE.finditer(formula)))


def evaluate_formula(
    df: pd.DataFrame,
    formula: str,
    *,
    allowed_columns: list[str] | None = None,
    require_brackets: bool = False,
) -> pd.Series:
    """仅允许列名、数值常量、括号和基本算术运算。"""
    if not formula or not formula.strip():
        raise ValueError("公式不能为空")

    expression = formula.strip()
    env: dict[str, pd.Series] = {}

    allowed = set(allowed_columns) if allowed_columns is not None else set(map(str, df.columns))
    bracket_references = formula_references(expression)
    token_index = 0
    for column in bracket_references:
        if column not in allowed:
            raise UnsafeFormulaError(f"公式引用了未授权列: {column}")
        if column not in df.columns:
            raise UnsafeFormulaError(f"公式引用的列不存在: {column}")
        token = f"__col_{token_index}"
        token_index += 1
        expression = expression.replace(f"[{column}]", token)
        env[token] = pd.to_numeric(df[column], errors="coerce")

    # 兼容旧版直接书写列名的调用；正式分析计划要求使用无歧义的方括号引用。
    if not require_brackets:
        for column in sorted(allowed, key=len, reverse=True):
            token = f"__col_{token_index}"
            if column in expression:
                token_index += 1
                expression = expression.replace(column, token)
                env[token] = pd.to_numeric(df[column], errors="coerce")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"公式语法错误: {exc.msg}") from exc

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        result = _evaluate_node(tree.body, env)
    if isinstance(result, pd.Series):
        return result.reindex(df.index)
    if isinstance(result, (int, float)):
        return pd.Series(result, index=df.index, dtype="float64")
    raise UnsafeFormulaError("公式结果必须是数值列")


def apply_derived_columns(
    df: pd.DataFrame,
    definitions: list["DerivedColumn"],
) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """按计划计算互相独立的派生列，并返回清理日志和用户可见警告。"""
    if not definitions:
        return df, [], []
    result = df.copy()
    original_columns = set(map(str, df.columns))
    derived_name_list = [item.name for item in definitions]
    if len(derived_name_list) != len(set(derived_name_list)):
        raise ValueError("自定义列名称不能重复")
    derived_names = set(derived_name_list)
    logs: list[dict] = []
    warnings: list[str] = []

    for definition in definitions:
        if definition.name in original_columns:
            raise ValueError(f"自定义列不能覆盖原始列: {definition.name}")
        chained = sorted(set(definition.source_columns) & derived_names)
        if chained:
            raise ValueError(f"自定义列不能引用其他自定义列: {chained}")
        missing = sorted(set(definition.source_columns) - original_columns)
        if missing:
            raise ValueError(f"自定义列 {definition.name!r} 引用的原始列不存在: {missing}")
        references = set(formula_references(definition.formula))
        expected = set(definition.source_columns)
        if references != expected:
            omitted = sorted(expected - references)
            unexpected = sorted(references - expected)
            raise ValueError(
                f"自定义列 {definition.name!r} 的公式与来源列不一致"
                f"；未使用={omitted}，未登记={unexpected}"
            )
        non_numeric = [
            column for column in definition.source_columns
            if not pd.api.types.is_numeric_dtype(df[column])
        ]
        if non_numeric:
            raise ValueError(f"自定义列只能引用数值型原始列: {non_numeric}")

        source_complete = df[definition.source_columns].notna().all(axis=1)
        computed = evaluate_formula(
            df,
            definition.formula,
            allowed_columns=definition.source_columns,
            require_brackets=True,
        )
        computed = (
            pd.to_numeric(computed, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .round(8)
        )
        invalid_operation_count = int((source_complete & computed.isna()).sum())
        missing_count = int(computed.isna().sum())
        if int(computed.notna().sum()) == 0:
            raise ValueError(f"自定义列 {definition.name!r} 没有任何有效计算结果")
        if invalid_operation_count:
            warnings.append(
                f"自定义列 {definition.name!r} 有 {invalid_operation_count} 行因除零、溢出或无效运算转为缺失值"
            )
        result[definition.name] = computed
        logs.append({
            "operation": "derive_column",
            "name": definition.name,
            "formula": definition.formula,
            "source_columns": list(definition.source_columns),
            "decimal_places": 8,
            "missing_result_count": missing_count,
            "invalid_operation_count": invalid_operation_count,
        })
    return result, logs, warnings


def _evaluate_node(node: ast.AST, env: dict[str, pd.Series]):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise UnsafeFormulaError("只允许数值常量")
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in env:
            raise UnsafeFormulaError(f"未知列名或非法标识符: {node.id}")
        return env[node.id]

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPERATORS.get(type(node.op))
        if op is None:
            raise UnsafeFormulaError(f"不允许的运算符: {type(node.op).__name__}")
        left = _evaluate_node(node.left, env)
        right = _evaluate_node(node.right, env)
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPERATORS.get(type(node.op))
        if op is None:
            raise UnsafeFormulaError(f"不允许的一元运算符: {type(node.op).__name__}")
        return op(_evaluate_node(node.operand, env))

    # 明确拒绝函数调用、属性访问、下标、推导式和导入等全部其他语法。
    raise UnsafeFormulaError(f"公式中不允许使用 {type(node).__name__}")
