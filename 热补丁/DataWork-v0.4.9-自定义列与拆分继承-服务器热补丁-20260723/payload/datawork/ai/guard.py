"""AI Guard — AI 输出校验：Pydantic Schema + 规则二次审核 + 数值一致性检查。

Phase B: validates AI-generated statistical reports against canonical result JSON
and hard-coded constraint rules (R1, R2, R4, R9).
"""

from __future__ import annotations

import re
import json
import math
from typing import Optional

from ..rules.constraints import check_report_for_violations


def validate_statistical_values(text: str, result_json: str) -> list[str]:
    """检查 AI 文本中的 F、p 和偏 η² 是否与 canonical result 一致。"""
    violations: list[str] = []
    try:
        result = json.loads(result_json) if isinstance(result_json, str) else result_json
    except json.JSONDecodeError:
        return ["[Guard] canonical_result.json 无法解析"]

    expected_values = _extract_stat_values_from_json(result).get("omnibus_tests", [])
    f_pattern = re.compile(
        r'F\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)\s*=\s*([\d.]+)',
        re.IGNORECASE,
    )
    for match in f_pattern.finditer(text):
        df1, df2, f_value = map(float, match.groups())
        candidates = [
            test for test in expected_values
            if _close(df1, test.get("df_num"), 0.02)
            and _close(df2, test.get("df_den"), 0.02)
        ]
        candidate = min(
            candidates,
            key=lambda test: abs(f_value - float(test.get("f_value", float("inf")))),
            default=None,
        )
        if candidate is None:
            violations.append(
                f"[Guard R9] 报告出现未在统计结果中找到的自由度组合: F({df1:g},{df2:g})"
            )
            continue

        expected_f = candidate.get("f_value")
        if expected_f is not None and not _close(f_value, expected_f, max(0.01, abs(float(expected_f)) * 0.005)):
            violations.append(
                f"[Guard R9] F 值不匹配: 报告 F({df1:g},{df2:g})={f_value}, 实际 F={expected_f}"
            )

        segment = text[match.end(): match.end() + 180]
        p_match = re.search(r'\bp\s*([=<>≤≥])\s*(\.?\d+(?:\.\d+)?)', segment, re.IGNORECASE)
        if p_match and candidate.get("p_value") is not None:
            operator, raw = p_match.groups()
            reported_p = float(raw if not raw.startswith('.') else f"0{raw}")
            expected_p = float(candidate["p_value"])
            p_ok = (
                _close(reported_p, expected_p, max(0.0005, abs(expected_p) * 0.02))
                if operator == "="
                else expected_p < reported_p if operator in {"<", "≤"}
                else expected_p > reported_p
            )
            if not p_ok:
                violations.append(
                    f"[Guard R9] p 值不匹配: 报告 p{operator}{reported_p:g}, 实际 p={expected_p}"
                )

        eta_match = re.search(r'[η\u03b7]\s*[²2]\s*p?\s*=\s*(\.?\d+(?:\.\d+)?)', segment)
        if eta_match and candidate.get("eta_sq_p") is not None:
            raw = eta_match.group(1)
            reported_eta = float(raw if not raw.startswith('.') else f"0{raw}")
            if segment[eta_match.end():].lstrip().startswith("%"):
                reported_eta /= 100
            expected_eta = float(candidate["eta_sq_p"])
            if not _close(reported_eta, expected_eta, max(0.001, abs(expected_eta) * 0.02)):
                violations.append(
                    f"[Guard R9] 偏 η² 不匹配: 报告 η²p={reported_eta}, 实际 η²p={expected_eta}"
                )
    return violations


def validate_all_reported_numbers(text: str, result_json: str) -> list[str]:
    """Reject standalone report numbers that cannot be traced to canonical output."""
    try:
        result = json.loads(result_json) if isinstance(result_json, str) else result_json
    except json.JSONDecodeError:
        return ["[Guard] canonical_result.json 无法解析"]

    expected: list[float] = [95.0]  # Conventional confidence-level label, not a fitted value.

    numeric_label_pattern = re.compile(
        r"^\s*([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(?:年|年度|组|水平)?\s*$"
    )

    number_token_pattern = re.compile(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")
    label_context_tokens = {
        "group", "level", "fixed_level", "subset_key", "subset_info",
        "contrast", "context", "label", "factor_combination", "split_key", "task_key",
        "category", "categories", "value", "values", "order", "time_point", "period",
    }

    # 先发现结果中承担“因素/拆分维度”角色的动态字段名。多因素描述表常直接
    # 使用原始列名作为键（例如 {"年份": "2024", "品种": "A"}），仅靠
    # group/level 等固定英文键会漏掉这些数值型标签。
    label_field_names: set[str] = set()
    factor_collection_keys = {
        "between_factors", "within_factors", "fixed_factors", "factor_cols",
        "factor_columns", "categorical_factors", "split_cols", "split_by",
        "emm_factors", "row_levels", "column_levels", "group_order",
    }

    def discover_label_fields(node: object) -> None:
        if isinstance(node, dict):
            role = str(node.get("role", "")).lower()
            name = node.get("name")
            if name is not None and role in {"between", "within", "factor", "categorical", "split"}:
                label_field_names.add(str(name).lower())
            levels = node.get("levels")
            if isinstance(levels, dict):
                label_field_names.update(str(key).lower() for key in levels)
            subset_info = node.get("subset_info")
            if isinstance(subset_info, dict):
                label_field_names.update(
                    str(key).lower() for key in subset_info if str(key).lower() != "task_id"
                )
            for key, value in node.items():
                if str(key).lower() in factor_collection_keys:
                    if isinstance(value, (list, tuple, set)):
                        label_field_names.update(str(item).lower() for item in value)
                    elif isinstance(value, str):
                        label_field_names.add(value.lower())
                discover_label_fields(value)
        elif isinstance(node, list):
            for value in node:
                discover_label_fields(value)

    discover_label_fields(result)

    def add_numeric_label(value: object, *, composite: bool = False) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            expected.append(float(value))
            return
        if not isinstance(value, str):
            return
        match = numeric_label_pattern.fullmatch(value)
        if match:
            try:
                expected.append(float(match.group(1)))
            except ValueError:
                pass
            return
        if composite:
            # 组合标签可能是“年份=2024｜品种=XLZ48”或“2024 vs 2025”。
            for token in number_token_pattern.findall(value):
                try:
                    expected.append(float(token))
                except ValueError:
                    pass

    def visit(node: object, key_hint: str = "") -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)) and math.isfinite(float(node)):
            expected.append(float(node))
        elif isinstance(node, dict):
            expected.append(float(len(node)))
            for key, value in node.items():
                # 对象键在统计结果中承担标签作用，可包含年份等数字型水平。
                add_numeric_label(key, composite=True)
                child_hint = f"{key_hint}.{str(key).lower()}" if key_hint else str(key).lower()
                visit(value, child_hint)
        elif isinstance(node, list):
            expected.append(float(len(node)))
            for value in node:
                visit(value, key_hint)
        elif isinstance(node, str):
            path_parts = {part for part in key_hint.split(".") if part}
            is_label_context = (
                any(token in key_hint for token in label_context_tokens)
                or bool(path_parts & label_field_names)
                or "deterministic_reference" in path_parts
            )
            add_numeric_label(node, composite=is_label_context)

    visit(result)
    # 允许把 canonical 中 0–1 范围的比例或效应量换算成百分数表达。
    expected.extend(value * 100 for value in list(expected) if 0 <= value <= 1)
    number_pattern = re.compile(r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])")
    violations: list[str] = []
    seen: set[str] = set()
    for match in number_pattern.finditer(text):
        raw = match.group(0)
        reported = float(raw)
        mantissa = re.split(r"[eE]", raw, maxsplit=1)[0]
        decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
        tolerance = max(5e-7, 0.5 * (10 ** -decimals)) + 1e-12
        prefix = text[max(0, match.start() - 12):match.start()]
        if re.search(r"\bp\s*[<≤>]\s*$", prefix, re.IGNORECASE) and reported in {0.05, 0.01, 0.001, 0.0001}:
            # 阈值式 p 值已由统计模式守卫核对方向，不应被逐值相等规则误判。
            continue
        if any(abs(reported - value) <= tolerance for value in expected):
            continue
        if raw not in seen:
            seen.add(raw)
            violations.append(f"[Guard R9] 报告数值 {raw} 未在统计结果中找到可追溯来源")
    return violations


def _close(value: float, expected: object, tolerance: float) -> bool:
    try:
        return abs(float(value) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return False


def _extract_stat_values_from_json(result: dict) -> dict:
    """递归提取单次、工作区信封和批量结果中的总体检验。"""
    extracted: list[dict] = []
    seen: set[tuple] = set()

    def visit(node: object) -> None:
        if isinstance(node, dict):
            required = {"df_num", "df_den", "f_value", "p_value"}
            if required.issubset(node):
                item = {
                    "effect": node.get("effect", ""),
                    "df_num": node.get("df_num"),
                    "df_den": node.get("df_den"),
                    "f_value": node.get("f_value"),
                    "p_value": node.get("p_value"),
                    "eta_sq_p": node.get("eta_sq_p"),
                }
                signature = tuple(item.get(key) for key in ("effect", "df_num", "df_den", "f_value", "p_value"))
                if signature not in seen:
                    seen.add(signature)
                    extracted.append(item)
            elif (
                str(node.get("statistic_name", "")).upper() == "F"
                and node.get("statistic_value") is not None
                and node.get("df_num") is not None
                and node.get("df_den") is not None
            ):
                item = {
                    "effect": node.get("effect", ""),
                    "df_num": node.get("df_num"),
                    "df_den": node.get("df_den"),
                    "f_value": node.get("statistic_value"),
                    "p_value": node.get("p_value"),
                    "eta_sq_p": None,
                }
                signature = tuple(item.get(key) for key in ("effect", "df_num", "df_den", "f_value", "p_value"))
                if signature not in seen:
                    seen.add(signature)
                    extracted.append(item)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return {"omnibus_tests": extracted}


def validate_ai_method_against_rules(
    ai_method: str,
    design_has_repeated_measures: bool,
    research_goal: str,
) -> list[str]:
    """
    校验 AI 推荐的方法是否违反规则引擎。

    ai_method: AI 推荐的方法名 (e.g. "twoway_anova")
    """
    violations = []

    # R1: 重复测量 + 变化类目标 → 不能用简单 ANOVA
    if design_has_repeated_measures:
        dynamic_keywords = ["变化", "轨迹", "幅度", "趋势", "提高", "下降"]
        if any(kw in research_goal for kw in dynamic_keywords):
            if ai_method in ("oneway_anova", "ttest", "cross_sectional_anova"):
                violations.append(
                    f"[R1] 检测到重复测量结构 + 变化类研究目标，"
                    f"AI 推荐 '{ai_method}' 被规则引擎拒绝。请使用混合模型或重复测量 ANOVA。"
                )

    # R4: 简单方法不适用复杂设计
    # (其他规则在 CLI 流程中检查)

    return violations


def is_ai_statistical_value(text: str) -> bool:
    """
    快速检测 AI 是否自行生成了统计数值（R9）。
    只检查 AI 是否自行"编造"了数值组合，在没有提供结果 JSON 的情况下。
    """
    # 检测 F(df, df) = value, p = value 模式
    pattern = re.compile(r'[Ff]\s*\(\s*\d+', re.IGNORECASE)
    return bool(pattern.search(text))


def guard_ai_output(
    ai_text: str,
    result_json: Optional[str] = None,
    method_type: str = "",
    design_has_repeated_measures: bool = False,
    research_goal: str = "",
    ai_method: str = "",
    strict_numeric: bool = False,
) -> dict:
    """
    综合 AI 输出校验入口。

    Returns: {passed: bool, violations: [str], warnings: [str]}
    """
    all_violations = []
    all_warnings = []

    # 1. 数值一致性检查 (R9)
    if result_json:
        num_violations = validate_statistical_values(ai_text, result_json)
        all_violations.extend(num_violations)
        if strict_numeric:
            all_violations.extend(validate_all_reported_numbers(ai_text, result_json))

    # 2. 报告违规词检查 (R2)
    if method_type == "cross_sectional":
        report_violations = check_report_for_violations(ai_text, method_type)
        all_violations.extend(report_violations)

    # 3. 方法合规检查
    if ai_method and research_goal:
        method_violations = validate_ai_method_against_rules(
            ai_method, design_has_repeated_measures, research_goal
        )
        all_violations.extend(method_violations)

    # 4. 自编数值检查 (R9)
    if not result_json and is_ai_statistical_value(ai_text):
        all_warnings.append(
            "[R9] AI 输出中检测到疑似自编的统计数值。"
            "请确保这些数值来自统计引擎。"
        )

    return {
        "passed": len(all_violations) == 0,
        "violations": all_violations,
        "warnings": all_warnings,
    }
