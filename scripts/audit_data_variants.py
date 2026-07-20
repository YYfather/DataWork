#!/usr/bin/env python3
"""Fuzz representative method datasets with common interaction/data failures."""
from __future__ import annotations

import argparse
import math
import runpy
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

namespace = runpy.run_path(str(ROOT / "tests/unit/test_interaction_matrix.py"))
case = namespace["case"]
list_methods = namespace["list_methods"]
PreflightService = namespace["PreflightService"]
AnalysisService = namespace["AnalysisService"]
AnalysisPlan = namespace["AnalysisPlan"]


def _nonfinite_paths(value: object, path: str = "result") -> list[str]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (float, np.floating)):
        return [path] if not math.isfinite(float(value)) else []
    if isinstance(value, dict):
        return [
            found
            for key, item in value.items()
            for found in _nonfinite_paths(item, f"{path}.{key}")
        ]
    if isinstance(value, (list, tuple)):
        return [
            found
            for index, item in enumerate(value)
            for found in _nonfinite_paths(item, f"{path}[{index}]")
        ]
    return []


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", default=[])
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    preflight = PreflightService()
    service = AnalysisService()
    rng = np.random.default_rng(941)
    problems: list[tuple[str, str, str, str, str]] = []
    ready_count = 0
    checked = 0

    methods = list(list_methods(runnable_only=True))
    if args.method:
        requested = set(args.method)
        methods = [item for item in methods if item.name in requested]
        missing_methods = requested - {item.name for item in methods}
        if missing_methods:
            print("Unknown methods:", ", ".join(sorted(missing_methods)), file=sys.stderr)
            return 2
    methods = methods[max(args.start, 0):]
    if args.limit > 0:
        methods = methods[:args.limit]
    if args.list:
        for index, method in enumerate(methods, start=max(args.start, 0)):
            print(index, method.name)
        return 0

    for method_index, method in enumerate(methods, start=1):
        base, kwargs = case(method.name)
        variants: list[tuple[str, pd.DataFrame, dict]] = [("baseline", base.copy(), dict(kwargs))]
        selected = list(dict.fromkeys(
            kwargs.get("dependent_variables", [])
            + kwargs.get("fixed_factors", [])
            + kwargs.get("covariates", [])
            + kwargs.get("random_factors", [])
            + ([kwargs["subject_id"]] if kwargs.get("subject_id") else [])
            + ([kwargs["repeated_factor"]] if kwargs.get("repeated_factor") else [])
        ))

        missing = base.copy()
        for column in selected:
            if column in missing and len(missing) > 8:
                indices = rng.choice(missing.index, size=max(1, len(missing) // 8), replace=False)
                missing.loc[indices, column] = np.nan
        variants.append(("missingness", missing, dict(kwargs)))
        variants.append(("tiny", base.head(min(4, len(base))).copy(), dict(kwargs)))
        if len(base):
            variants.append(("duplicate_row", pd.concat([base, base.iloc[[0]]], ignore_index=True), dict(kwargs)))
        if kwargs.get("fixed_factors"):
            frame = base.copy()
            frame[kwargs["fixed_factors"][0]] = "constant"
            variants.append(("constant_factor", frame, dict(kwargs)))
        if kwargs.get("dependent_variables"):
            frame = base.copy()
            frame[kwargs["dependent_variables"][0]] = 1
            variants.append(("constant_dv", frame, dict(kwargs)))
            frame = base.copy()
            frame[kwargs["dependent_variables"][0]] = "text"
            variants.append(("text_dv", frame, dict(kwargs)))
        if method.supports_batch and len(base) >= 8:
            frame = base.copy()
            frame["_split"] = "main"
            frame.loc[frame.index[-2:], "_split"] = "tiny"
            batch_kwargs = dict(kwargs)
            batch_kwargs["split_by"] = ["_split"]
            variants.append(("batch_tiny", frame, batch_kwargs))
        if kwargs.get("dependent_variables"):
            overlap_kwargs = dict(kwargs)
            overlap_kwargs["split_by"] = [kwargs["dependent_variables"][0]]
            variants.append(("role_overlap", base.copy(), overlap_kwargs))

        method_ready = 0
        method_checked = 0
        for label, frame, variant_kwargs in variants:
            method_checked += 1
            checked += 1
            raw = {**variant_kwargs, "method": method.name}
            try:
                report = preflight.inspect(frame, raw)
            except Exception as exc:  # noqa: BLE001 - release audit captures all crashes
                problems.append((method.name, label, "preflight_crash", type(exc).__name__, str(exc)))
                continue
            if report.ready:
                ready_count += 1
                method_ready += 1
                try:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        result = service.run(frame, AnalysisPlan(**raw))
                    runtime_warnings = [
                        str(item.message)
                        for item in caught
                        if issubclass(item.category, RuntimeWarning)
                    ]
                    if runtime_warnings:
                        problems.append((
                            method.name,
                            label,
                            "runtime_warning",
                            "RuntimeWarning",
                            "; ".join(runtime_warnings[:3]),
                        ))
                    serialized = result.model_dump(mode="python") if hasattr(result, "model_dump") else result
                    nonfinite = _nonfinite_paths(serialized)
                    if nonfinite:
                        problems.append((
                            method.name,
                            label,
                            "nonfinite_result",
                            "NaNOrInfinity",
                            ", ".join(nonfinite[:8]),
                        ))
                except Exception as exc:  # noqa: BLE001
                    problems.append((method.name, label, "ready_but_execution_failed", type(exc).__name__, str(exc)))
        print(f"[{method_index}/{len(methods)}] {method.name}: {method_checked} variants, {method_ready} executable")

    print(f"Data variants checked: {checked}; executable variants: {ready_count}")
    if problems:
        for problem in problems:
            print("FAIL", problem)
        return 1
    print("All ready configurations executed; invalid configurations were blocked without crashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
