#!/usr/bin/env python3
"""Run the frozen DataWork golden-dataset suite.

The expected values in ``golden_datasets/manifest.json`` are generated with
SciPy/statsmodels or explicit formulas, not with DataWork execution functions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datawork.application.analysis_service import AnalysisService  # noqa: E402
from datawork.core.plan import AnalysisPlan  # noqa: E402


@dataclass
class Failure:
    case_id: str
    check: dict[str, Any]
    actual: Any
    message: str


def _select(payload: dict[str, Any], check: dict[str, Any]) -> Any:
    collection_name = check["collection"]
    collection = payload.get(collection_name)
    if collection is None:
        raise KeyError(f"missing collection {collection_name!r}")
    if check["field"] == "__len__":
        return len(collection)
    if not isinstance(collection, list):
        raise TypeError(f"collection {collection_name!r} is not a list")
    if "index" in check:
        item = collection[int(check["index"])]
    else:
        match = check.get("match", {})
        matched = [
            item for item in collection
            if all(item.get(key) == value for key, value in match.items())
        ]
        if len(matched) != 1:
            raise LookupError(
                f"expected one match in {collection_name!r} for {match!r}; found {len(matched)}"
            )
        item = matched[0]
    return item.get(check["field"])


def _matches(actual: Any, expected: Any, atol: float, rtol: float) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool) or isinstance(expected, str):
        return actual == expected
    if isinstance(expected, (int, float)):
        try:
            actual_float = float(actual)
        except (TypeError, ValueError):
            return False
        expected_float = float(expected)
        if math.isnan(expected_float):
            return math.isnan(actual_float)
        if math.isinf(expected_float):
            return math.isinf(actual_float) and math.copysign(1, actual_float) == math.copysign(1, expected_float)
        return math.isclose(actual_float, expected_float, abs_tol=atol, rel_tol=rtol)
    return actual == expected


def validate_suite(root: Path = ROOT, case_ids: set[str] | None = None) -> tuple[int, int, list[Failure]]:
    manifest_path = root / "golden_datasets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    service = AnalysisService()
    failures: list[Failure] = []
    checks_run = 0

    selected_cases = [case for case in manifest["cases"] if not case_ids or case["case_id"] in case_ids]
    for case in selected_cases:
        case_id = case["case_id"]
        data_path = root / "golden_datasets" / case["dataset"]
        digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
        if digest != case["dataset_sha256"]:
            failures.append(Failure(case_id, {}, digest, "dataset SHA-256 mismatch"))
            continue
        frame = pd.read_csv(data_path)
        try:
            plan = AnalysisPlan(method=case["method"], **case["plan"])
            result = service.run(frame, plan)
            payload = result.model_dump(mode="json")
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(Failure(case_id, {}, None, f"execution failed: {type(exc).__name__}: {exc}"))
            continue
        for check in case["checks"]:
            checks_run += 1
            try:
                actual = _select(payload, check)
            except Exception as exc:
                failures.append(Failure(case_id, check, None, f"selection failed: {exc}"))
                continue
            if not _matches(actual, check["expected"], float(check.get("atol", 1e-8)), float(check.get("rtol", 1e-7))):
                failures.append(Failure(case_id, check, actual, "value mismatch"))

    return len(selected_cases), checks_run, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--case", action="append", default=[], help="run only the named case_id; may be repeated")
    args = parser.parse_args()
    case_ids = set(args.case) or None
    case_count, check_count, failures = validate_suite(case_ids=case_ids)
    if case_ids and case_count != len(case_ids):
        known = {case["case_id"] for case in json.loads((ROOT / "golden_datasets/manifest.json").read_text(encoding="utf-8"))["cases"]}
        missing = sorted(case_ids - known)
        if missing:
            print(f"Unknown golden case(s): {', '.join(missing)}", file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps({
            "cases": case_count,
            "checks": check_count,
            "passed": not failures,
            "failures": [failure.__dict__ for failure in failures],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Golden cases: {case_count}; checks: {check_count}; failures: {len(failures)}")
        for failure in failures[:50]:
            print(f"- {failure.case_id}: {failure.message}; actual={failure.actual!r}; check={failure.check!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
