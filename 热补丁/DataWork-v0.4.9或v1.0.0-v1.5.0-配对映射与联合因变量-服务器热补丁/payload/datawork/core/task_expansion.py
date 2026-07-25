"""Deterministic expansion helpers shared by validation, preflight and execution."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from .method_registry import get_method

if TYPE_CHECKING:
    from .plan import AnalysisPlan


@dataclass(frozen=True)
class OutcomeTask:
    """One outcome dimension in an expanded analysis plan."""

    name: str | None
    variables: tuple[str, ...]


def outcome_tasks(plan: "AnalysisPlan") -> list[OutcomeTask]:
    """Return the exact outcome tasks without changing legacy semantics."""
    spec = get_method(plan.method)
    if spec.dependent_mode == "none":
        return [OutcomeTask(name=None, variables=())]
    if plan.dependent_variable_groups:
        return [
            OutcomeTask(name=group.name, variables=tuple(group.dependent_variables))
            for group in plan.dependent_variable_groups
        ]
    if spec.dependent_mode == "joint":
        return [OutcomeTask(name=None, variables=tuple(plan.dependent_variables))]
    return [
        OutcomeTask(name=dependent, variables=(dependent,))
        for dependent in plan.dependent_variables
    ]


def factor_tasks(plan: "AnalysisPlan") -> list[list[str]]:
    """Return every fixed-factor model in stable plan order."""
    if not plan.factor_combinations_enabled:
        return [list(plan.fixed_factors)]
    if plan.factor_combination_min_order is None or plan.factor_combination_max_order is None:
        raise ValueError("因素组合阶数未完成规范化")
    return [
        list(items)
        for order in range(
            plan.factor_combination_min_order,
            plan.factor_combination_max_order + 1,
        )
        for items in combinations(plan.fixed_factors, order)
    ]
