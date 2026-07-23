"""Deterministic expansion helpers shared by validation, preflight and execution."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Literal

from .method_registry import get_method

if TYPE_CHECKING:
    from .plan import AnalysisPlan


@dataclass(frozen=True)
class OutcomeTask:
    """One outcome dimension in an expanded analysis plan."""

    name: str | None
    variables: tuple[str, ...]
    mode: Literal["none", "single", "joint_all", "manual_groups", "combinations"]
    canonical_name: str | None = None


def outcome_tasks(plan: "AnalysisPlan") -> list[OutcomeTask]:
    """Return the exact outcome tasks without changing legacy semantics."""
    spec = get_method(plan.method)
    if spec.dependent_mode == "none":
        return [OutcomeTask(name=None, variables=(), mode="none")]
    if plan.dependent_task_mode == "manual_groups":
        return [
            OutcomeTask(
                name=group.name,
                variables=tuple(group.dependent_variables),
                mode="manual_groups",
                canonical_name=" + ".join(group.dependent_variables),
            )
            for group in plan.dependent_variable_groups
        ]
    if plan.dependent_task_mode == "combinations":
        if (
            plan.dependent_combination_min_size is None
            or plan.dependent_combination_max_size is None
        ):
            raise ValueError("因变量组合大小未完成规范化")
        tasks: list[OutcomeTask] = []
        for size in range(
            plan.dependent_combination_min_size,
            plan.dependent_combination_max_size + 1,
        ):
            for items in combinations(plan.dependent_variables, size):
                canonical = " + ".join(items)
                tasks.append(OutcomeTask(
                    name=plan.dependent_combination_labels.get(canonical, canonical),
                    variables=tuple(items),
                    mode="combinations",
                    canonical_name=canonical,
                ))
        return tasks
    if spec.dependent_mode == "joint":
        return [OutcomeTask(
            name=None,
            variables=tuple(plan.dependent_variables),
            mode="joint_all",
            canonical_name=" + ".join(plan.dependent_variables),
        )]
    return [
        OutcomeTask(
            name=dependent,
            variables=(dependent,),
            mode="single",
            canonical_name=dependent,
        )
        for dependent in plan.dependent_variables
    ]


def outcome_task_labels(
    task: OutcomeTask,
    *,
    include_single: bool = False,
    include_joint_all: bool = False,
) -> dict[str, object]:
    """Return stable batch dimensions for one outcome task."""
    columns = " | ".join(task.variables)
    if task.mode == "manual_groups":
        return {
            "dependent_group": task.name or task.canonical_name or columns,
            "dependent_variables": columns,
        }
    if task.mode == "combinations":
        labels: dict[str, object] = {
            "dependent_combination": task.name or task.canonical_name or columns,
            "dependent_columns": columns,
            "dependent_combination_size": len(task.variables),
        }
        if task.name and task.canonical_name and task.name != task.canonical_name:
            labels["dependent_combination_columns"] = task.canonical_name
        return labels
    if task.mode == "single" and include_single and task.variables:
        return {"dependent_variable": task.variables[0]}
    if task.mode == "joint_all" and include_joint_all and task.variables:
        return {"dependent_variables": columns}
    return {}


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
