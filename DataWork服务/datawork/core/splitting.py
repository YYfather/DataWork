"""批量拆分的唯一执行入口，供预检、校验和正式分析共同使用。"""

from __future__ import annotations

from itertools import product
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .plan import AnalysisPlan, SplitRule


SPLIT_TASK_WARNING_THRESHOLD = 200
SPLIT_TASK_HARD_LIMIT = 1000


def projected_split_group_count(frame: pd.DataFrame, plan: "AnalysisPlan") -> int:
    """Return the Cartesian split size without materializing any subsets."""
    if not plan.split_by:
        return 1
    rules = {rule.column: rule for rule in plan.split_rules}
    count = 1
    for column in plan.split_by:
        rule = rules.get(column)
        count *= len(rule.groups) if rule is not None else int(frame[column].nunique(dropna=True))
    return count


def build_split_groups(
    frame: pd.DataFrame,
    plan: "AnalysisPlan",
    *,
    include_empty: bool = False,
) -> list[tuple[dict[str, str], pd.DataFrame]]:
    """按旧式原值拆分或专业显式规则生成命名子集。"""
    if not plan.split_by:
        return [({}, frame)]
    rules = {rule.column: rule for rule in plan.split_rules}
    if not rules and not include_empty:
        grouped = frame.dropna(subset=plan.split_by).groupby(plan.split_by, dropna=True, sort=True)
        items: list[tuple[dict[str, str], pd.DataFrame]] = []
        for keys, subset in grouped:
            values = keys if isinstance(keys, tuple) else (keys,)
            items.append(({column: str(values[index]) for index, column in enumerate(plan.split_by)}, subset))
        return items

    dimensions: list[tuple[str, list[tuple[str, pd.Series]]]] = []
    for column in plan.split_by:
        rule = rules.get(column)
        if rule is None:
            levels = sorted(frame[column].dropna().unique().tolist(), key=lambda value: str(value))
            dimensions.append((column, [(str(level), frame[column].eq(level)) for level in levels]))
        else:
            dimensions.append((column, _rule_masks(frame[column], rule)))

    projected_groups = projected_split_group_count(frame, plan)
    if projected_groups > SPLIT_TASK_HARD_LIMIT:
        raise ValueError(
            f"当前拆分设置会生成 {projected_groups} 个组合，超过安全上限 "
            f"{SPLIT_TASK_HARD_LIMIT}；请减少拆分列或分组数量"
        )

    items = []
    for combination in product(*(groups for _, groups in dimensions)):
        labels = {dimensions[index][0]: item[0] for index, item in enumerate(combination)}
        mask = pd.Series(True, index=frame.index)
        for _, group_mask in combination:
            mask &= group_mask
        subset = frame.loc[mask]
        if include_empty or not subset.empty:
            items.append((labels, subset))
    return items


def _rule_masks(series: pd.Series, rule: "SplitRule") -> list[tuple[str, pd.Series]]:
    if rule.kind == "categorical":
        comparable = series.astype("string")
        return [(group.label, comparable.isin(group.values).fillna(False)) for group in rule.groups]
    numeric = pd.to_numeric(series, errors="coerce")
    masks: list[tuple[str, pd.Series]] = []
    for group in rule.groups:
        mask = numeric.notna()
        if group.lower is not None:
            mask &= numeric.ge(group.lower) if group.include_lower else numeric.gt(group.lower)
        if group.upper is not None:
            mask &= numeric.le(group.upper) if group.include_upper else numeric.lt(group.upper)
        masks.append((group.label, mask.fillna(False)))
    return masks
