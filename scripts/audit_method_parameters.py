#!/usr/bin/env python3
"""执行注册表中高级参数的非默认变体。

该命令直接通过 AnalysisService 执行真实统计引擎。支持按方法或索引分片，便于
CI/受限环境并行审查；multi_select 参数会逐项测试，并额外测试一个兼容的多选组合。
"""
from __future__ import annotations

import argparse
from itertools import product
import runpy
import sys
import warnings

import numpy as np
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datawork.application.analysis_service import AnalysisService  # noqa: E402
from datawork.core.method_registry import list_methods  # noqa: E402
from datawork.core.plan import AnalysisPlan  # noqa: E402


def _variants(spec: Any) -> list[Any]:
    if spec.kind == "select":
        return [value for value, _label in spec.options]
    if spec.kind == "multi_select":
        singles = [[value] for value, _label in spec.options]
        compatible = [value for value, _label in spec.options if value not in {"none", "auto", "dunnett"}]
        if len(compatible) >= 2:
            singles.append(compatible[:2])
        return singles
    if spec.kind == "boolean":
        return [not bool(spec.default)]
    if spec.kind == "integer":
        return [int(spec.minimum if spec.minimum is not None else int(spec.default) + 1)]
    if spec.kind == "number":
        return [float(spec.minimum if spec.minimum is not None else float(spec.default) + 0.1)]
    # 文本/自由列表参数依赖具体数据，交由专项测试覆盖。
    return []


def _contains(value: Any, target: str) -> bool:
    if isinstance(value, (list, tuple, set)):
        return target in {str(item) for item in value}
    return str(value) == target


def _balanced_factorial_frame(
    frame: Any,
    fixed_factors: list[str],
    dependent_variables: list[str],
) -> Any:
    """Build an estimable two-replicate full factorial fixture for high-order audits."""

    combinations = list(product((0, 1), repeat=len(fixed_factors)))
    repeated = [combination for combination in combinations for _ in range(2)]
    audit = frame.iloc[:0].copy().reindex(range(len(repeated)))
    for index, factor in enumerate(fixed_factors):
        audit[factor] = [f"L{combination[index]}" for combination in repeated]
    rng = np.random.default_rng(409 + len(fixed_factors))
    signal = np.asarray([
        sum((index + 1) * level for index, level in enumerate(combination))
        for combination in repeated
    ], dtype=float)
    for index, dependent in enumerate(dependent_variables):
        audit[dependent] = 10.0 + (index + 1) * signal / max(len(fixed_factors), 1)
        audit[dependent] += rng.normal(0.0, 0.35 + index * 0.05, len(audit))
    return audit


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", default=[], help="仅审查指定方法，可重复")
    parser.add_argument("--parameter", action="append", default=[], help="仅审查指定参数，可重复")
    parser.add_argument("--start", type=int, default=0, help="从筛选后方法列表的 0 基索引开始")
    parser.add_argument("--limit", type=int, default=0, help="最多审查多少个方法，0 表示全部")
    parser.add_argument("--list", action="store_true", help="只列出可审查方法")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    namespace = runpy.run_path(str(ROOT / "tests/unit/test_interaction_matrix.py"))
    case = namespace["case"]
    service = AnalysisService()
    methods = list(list_methods(runnable_only=True))
    if args.method:
        requested = set(args.method)
        methods = [item for item in methods if item.name in requested]
        missing = requested - {item.name for item in methods}
        if missing:
            print("Unknown methods:", ", ".join(sorted(missing)), file=sys.stderr)
            return 2
    methods = methods[max(args.start, 0):]
    if args.limit > 0:
        methods = methods[:args.limit]
    if args.list:
        for index, method in enumerate(methods, start=max(args.start, 0)):
            print(index, method.name)
        return 0

    failures: list[tuple[str, str, object, str]] = []
    checked = 0
    for method_index, method in enumerate(methods, start=1):
        frame, kwargs = case(method.name)
        base_parameters = dict(kwargs.get("method_parameters", {}))
        method_checked = 0
        for spec in method.parameters:
            if args.parameter and spec.key not in set(args.parameter):
                continue
            for value in _variants(spec):
                parameters = {**base_parameters, spec.key: value}
                variant_frame = frame.copy()
                variant_kwargs = dict(kwargs)
                if spec.key == "factor_model_order":
                    order = int(value)
                    fixed = list(variant_kwargs.get("fixed_factors", []))
                    while len(fixed) < order:
                        name = f"_audit_factor_{len(fixed) + 1}"
                        # 在每个现有因素单元内尽量均衡分配新因素水平。
                        if fixed:
                            variant_frame[name] = (
                                variant_frame.groupby(fixed, observed=True).cumcount() % 2
                            ).map({0: "L0", 1: "L1"})
                        else:
                            variant_frame[name] = np.where(np.arange(len(variant_frame)) % 2 == 0, "L0", "L1")
                        fixed.append(name)
                    variant_kwargs["fixed_factors"] = fixed
                    variant_kwargs["emm_factors"] = [item for item in variant_kwargs.get("emm_factors", []) if item in fixed]
                    variant_frame = _balanced_factorial_frame(
                        variant_frame,
                        fixed,
                        list(variant_kwargs.get("dependent_variables", [])),
                    )
                    if len(fixed) > order:
                        variant_kwargs.update({
                            "factor_combinations_enabled": True,
                            "factor_combination_min_order": order,
                            "factor_combination_max_order": order,
                        })
                if method.name == "chi_square_independence" and spec.key == "p_value_method" and value != "asymptotic":
                    parameters["n_resamples"] = 99
                if spec.key in {"posthoc_method", "posthoc_methods"} and _contains(value, "dunnett"):
                    controls: list[str] = []
                    for factor in list(variant_kwargs.get("fixed_factors", [])):
                        levels = variant_frame[factor].dropna().astype(str).unique().tolist()
                        if levels:
                            controls.append(f"{factor}={levels[0]}")
                    if controls:
                        parameters["control_group"] = ";".join(controls)
                raw = {**variant_kwargs, "method": method.name, "method_parameters": parameters}
                checked += 1
                method_checked += 1
                try:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        result = service.run(variant_frame, AnalysisPlan(**raw))
                    runtime_warnings = [
                        str(item.message) for item in caught if issubclass(item.category, RuntimeWarning)
                    ]
                    if runtime_warnings:
                        failures.append((method.name, spec.key, value, "; ".join(runtime_warnings[:3])))
                    if result is None:
                        failures.append((method.name, spec.key, value, "returned None"))
                except Exception as exc:  # noqa: BLE001 - 审查器需要记录全部失败
                    failures.append((method.name, spec.key, value, f"{type(exc).__name__}: {exc}"))
        print(f"[{method_index}/{len(methods)}] {method.name}: {method_checked} variants")

    print(f"Advanced parameter variants checked: {checked}")
    if failures:
        for failure in failures:
            print("FAIL", failure)
        return 1
    print("All advanced parameter variants passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
