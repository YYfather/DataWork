"""显著性紧凑字母分组（Compact Letter Display, CLD）。

CLD 只从完整的成对显著性关系生成：
- 显著差异的两组不得共享字母；
- 未显著差异的两组至少共享一个字母。

Dunnett 等仅覆盖部分比较的方法不能据此构造完整 CLD，调用方应保留成对比较表，
而不是补造未检验组对的关系。
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, Mapping, Sequence

from .result import ContrastResult, EMMeans, SignificanceLetterGroup


def _letter_name(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa。"""
    value = index
    chars: list[str] = []
    while True:
        value, remainder = divmod(value, 26)
        chars.append(chr(ord("a") + remainder))
        if value == 0:
            break
        value -= 1
    return "".join(reversed(chars))


def _absorb(columns: Iterable[frozenset[str]]) -> list[frozenset[str]]:
    unique: list[frozenset[str]] = []
    for column in columns:
        if column and column not in unique:
            unique.append(column)
    return [
        column for column in unique
        if not any(column < other for other in unique)
    ]


def compact_letter_sets(
    group_means: Mapping[str, float],
    pair_significance: Mapping[frozenset[str], bool],
) -> dict[str, str]:
    """根据完整两两显著性矩阵生成字母集合。"""
    groups = list(group_means)
    if len(groups) < 2:
        return {group: "a" for group in groups}
    expected = {frozenset(pair) for pair in combinations(groups, 2)}
    if set(pair_significance) != expected:
        missing = len(expected - set(pair_significance))
        raise ValueError(f"CLD 需要完整成对比较矩阵，当前缺少 {missing} 个组对")

    columns: list[frozenset[str]] = [frozenset(groups)]
    significant_pairs = [pair for pair, significant in pair_significance.items() if significant]
    significant_pairs.sort(key=lambda pair: tuple(sorted(pair)))
    for pair in significant_pairs:
        left, right = tuple(pair)
        updated: list[frozenset[str]] = []
        for column in columns:
            if left in column and right in column:
                updated.extend([column - {left}, column - {right}])
            else:
                updated.append(column)
        columns = _absorb(updated)

    # 让最高均值所在列优先获得 a，输出更符合农业论文习惯。
    columns.sort(
        key=lambda column: (
            -max(float(group_means[group]) for group in column),
            -len(column),
            tuple(sorted(column)),
        )
    )
    labels = {column: _letter_name(index) for index, column in enumerate(columns)}
    group_tokens = {
        group: tuple(labels[column] for column in columns if group in column)
        for group in groups
    }
    output = {group: "".join(tokens) for group, tokens in group_tokens.items()}

    # 防御性验证，按完整字母标签而不是字符逐个比较，兼容 aa/ab 等扩展标签。
    for pair, significant in pair_significance.items():
        left, right = tuple(pair)
        shared = bool(set(group_tokens[left]) & set(group_tokens[right]))
        if significant and shared:
            raise RuntimeError(f"CLD 内部错误：显著组对 {left}/{right} 共享字母")
        if not significant and not shared:
            raise RuntimeError(f"CLD 内部错误：非显著组对 {left}/{right} 未共享字母")
    return output


def cld_from_emm_contrasts(
    emmeans: Sequence[EMMeans],
    contrasts: Sequence[ContrastResult],
    *,
    factor: str,
    method: str,
    outcome: str = "",
    context: str = "",
) -> list[SignificanceLetterGroup]:
    """从按 EMM 全部两两组合顺序生成的对比构造 CLD。"""
    if len(emmeans) < 2 or len(contrasts) != len(emmeans) * (len(emmeans) - 1) // 2:
        return []
    group_means = {item.group: float(item.mean) for item in emmeans}
    pair_significance: dict[frozenset[str], bool] = {}
    for (left, right), contrast in zip(combinations(emmeans, 2), contrasts):
        pair_significance[frozenset({left.group, right.group})] = bool(contrast.significant)
    letters = compact_letter_sets(group_means, pair_significance)
    ranked = sorted(emmeans, key=lambda item: (-float(item.mean), item.group))
    return [
        SignificanceLetterGroup(
            outcome=outcome,
            factor=factor,
            context=context,
            method=method,
            group=item.group,
            mean=float(item.mean),
            letters=letters[item.group],
            levels=dict(item.levels),
        )
        for item in ranked
    ]


def cld_from_posthoc_results(
    group_means: Mapping[str, float],
    comparisons: Sequence[object],
    *,
    factor: str,
    method: str,
    outcome: str = "",
    context: str = "",
) -> list[SignificanceLetterGroup]:
    """从包含 group1/group2/significant 的完整事后比较结果生成 CLD。"""
    expected_count = len(group_means) * (len(group_means) - 1) // 2
    if len(group_means) < 2 or len(comparisons) != expected_count:
        return []
    pair_significance = {
        frozenset({str(getattr(item, "group1")), str(getattr(item, "group2"))}): bool(getattr(item, "significant"))
        for item in comparisons
    }
    letters = compact_letter_sets(group_means, pair_significance)
    return [
        SignificanceLetterGroup(
            outcome=outcome,
            factor=factor,
            context=context,
            method=method,
            group=group,
            mean=float(mean),
            letters=letters[group],
            levels={factor: group},
        )
        for group, mean in sorted(group_means.items(), key=lambda item: (-float(item[1]), item[0]))
    ]
