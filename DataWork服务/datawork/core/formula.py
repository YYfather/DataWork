"""受限的派生变量表达式计算器。"""

from __future__ import annotations

import ast
import operator

import pandas as pd


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


def evaluate_formula(df: pd.DataFrame, formula: str) -> pd.Series:
    """仅允许列名、数值常量、括号和基本算术运算。"""
    if not formula or not formula.strip():
        raise ValueError("公式不能为空")

    expression = formula.strip()
    env: dict[str, pd.Series] = {}

    # 列名可能包含中文、空格或以数字开头，因此先替换为合法占位符。
    for index, column in enumerate(sorted(map(str, df.columns), key=len, reverse=True)):
        token = f"__col_{index}"
        if column in expression:
            expression = expression.replace(column, token)
            env[token] = pd.to_numeric(df[column], errors="coerce")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"公式语法错误: {exc.msg}") from exc

    result = _evaluate_node(tree.body, env)
    if isinstance(result, pd.Series):
        return result.reindex(df.index)
    if isinstance(result, (int, float)):
        return pd.Series(result, index=df.index, dtype="float64")
    raise UnsafeFormulaError("公式结果必须是数值列")


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
