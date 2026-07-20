"""AI 辅助实验设计推断 — 规则推断 + AI 复核。"""

from __future__ import annotations

from typing import Optional

from ..io.profiler import DataProfile
from ..ai.provider import LLMProvider, create_provider
from ..ai.prompts import (
    variable_inference_prompt,
    VariableRoleResponse,
    VariableRoleSuggestion,
)


async def ai_enhance_roles(
    profile: DataProfile,
    provider: Optional[LLMProvider] = None,
) -> VariableRoleResponse:
    """
    用 AI 复核和增强规则引擎的角色推断结果。

    Args:
        profile: 规则引擎生成的数据画像
        provider: LLM Provider（None = 自动检测）

    Returns:
        AI 的角色推断结果，置信度加权合并到 profile 的 rules_inferred_role
    """
    if provider is None:
        provider = create_provider()

    if provider is None:
        # AI 不可用，只返回规则引擎结果
        return _rules_only_response(profile)

    # 构建列信息
    columns_info = []
    for col in profile.columns:
        columns_info.append({
            "name": col.name,
            "dtype": col.dtype,
            "n_unique": col.n_unique,
            "missing_rate": col.missing_rate,
            "sample_values": col.unique_values[:5],
            "rules_inferred_role": col.inferred_role,
        })

    warnings = []
    if profile.percent_columns_found:
        warnings.append(f"含 '%' 的列已自动转为数值: {profile.percent_columns_found}")
    if profile.wide_to_long_hint:
        warnings.append(profile.wide_to_long_hint)

    messages = variable_inference_prompt(columns_info, profile.n_rows, warnings)

    try:
        response = await provider.generate_structured(
            messages,
            schema=VariableRoleResponse,
            temperature=0.2,
        )
    except Exception as e:
        # AI 调用失败，降级
        return _rules_only_response(profile, error=str(e))

    if response.parsed is None:
        return _rules_only_response(profile, error=response.error or "AI 解析失败")

    return response.parsed


def _rules_only_response(profile: DataProfile, error: str = "") -> VariableRoleResponse:
    """只用规则引擎结果构建响应。"""
    variables = []
    for col in profile.columns:
        variables.append(VariableRoleSuggestion(
            column=col.name,
            suggested_role=col.inferred_role,
            confidence=col.role_confidence,
            reasoning=f"规则推断: {col.note}" if col.note else "规则推断",
        ))

    return VariableRoleResponse(
        variables=variables,
        notes=[f"[规则引擎] AI 不可用: {error}" if error else "[规则引擎] AI 不可用，使用纯规则推断"],
        questions=[],
        wide_format_hint=profile.wide_to_long_hint or "",
    )


def merge_roles(
    rules_response: VariableRoleResponse,
    ai_response: Optional[VariableRoleResponse],
) -> list[dict]:
    """
    合并规则引擎和 AI 的推断结果，返回统一的角色列表。

    合并策略：AI 置信度 > 规则的 → 采用 AI；否则保留规则。
    返回 [{column, role, confidence, source, reasoning}]
    """
    rules_map = {v.column: v for v in rules_response.variables}
    merged = []

    if ai_response is None or ai_response is AI_DISABLED_SENTINEL:
        # 只用规则
        for v in rules_response.variables:
            merged.append({
                "column": v.column,
                "role": v.suggested_role,
                "confidence": v.confidence,
                "source": "rules",
                "reasoning": v.reasoning,
            })
        return merged

    ai_map = {v.column: v for v in ai_response.variables}

    for col_name, rv in rules_map.items():
        av = ai_map.get(col_name)
        if av and av.confidence > rv.confidence:
            merged.append({
                "column": col_name,
                "role": av.suggested_role,
                "confidence": av.confidence,
                "source": "ai",
                "reasoning": av.reasoning,
            })
        else:
            merged.append({
                "column": col_name,
                "role": rv.suggested_role,
                "confidence": rv.confidence,
                "source": "rules",
                "reasoning": rv.reasoning,
            })

    return merged


# 哨兵值
AI_DISABLED_SENTINEL = object()
