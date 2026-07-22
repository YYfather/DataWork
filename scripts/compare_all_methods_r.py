#!/usr/bin/env python3
"""Development-only R/Python numerical cross-check for every runnable method."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datawork.application.analysis_service import AnalysisService  # noqa: E402
from datawork.core.method_registry import canonical_method_name, list_methods  # noqa: E402
from datawork.core.plan import AnalysisPlan  # noqa: E402


DEFAULT_RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\Rscript.exe")
R_SCRIPT = ROOT / "tests" / "reference" / "r" / "validate_all_methods.R"
MANIFEST = ROOT / "golden_datasets" / "manifest.json"
R_DEPENDENCIES = ("jsonlite", "car", "DescTools", "exact2x2", "nnet", "MASS", "nlme")

ANOVA_METHODS = {
    "oneway_anova", "welch_anova", "twoway_anova", "threeway_anova",
    "ancova", "repeated_measures_anova", "mixed_anova", "multifactor_anova",
}
MANOVA_METHODS = {"oneway_manova", "twoway_manova", "threeway_manova", "multifactor_manova"}
LOOSER_TOLERANCES = {
    "linear_mixed_model": 3e-4,
    "multinomial_logistic_regression": 2e-4,
    "ordinal_logistic_regression": 2e-4,
    "barnard_exact": 5e-4,
    "boschloo_exact": 2e-3,
    "breslow_day": 2e-4,
}


def locate_rscript(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
    elif DEFAULT_RSCRIPT.exists():
        candidate = DEFAULT_RSCRIPT
    else:
        located = shutil.which("Rscript")
        if not located:
            raise FileNotFoundError("未找到 Rscript；请使用 --rscript 指定开发解释器")
        candidate = Path(located).resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Rscript 不存在: {candidate}")
    return candidate


def selected_cases() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    selected: list[dict] = []
    seen: set[str] = set()
    for case in manifest["cases"]:
        method = canonical_method_name(case["method"])
        if case["method"] == "factorial_anova" or method in seen:
            continue
        seen.add(method)
        selected.append(case)
    runnable = {item.name for item in list_methods(runnable_only=True)}
    missing = sorted(runnable - seen)
    extra = sorted(seen - runnable)
    if missing or extra:
        raise AssertionError(f"R 对照覆盖与注册方法不一致；缺少={missing}，额外={extra}")
    return selected


def python_metric(case: dict) -> dict[str, float]:
    frame = pd.read_csv(ROOT / "golden_datasets" / case["dataset"])
    plan = AnalysisPlan(method=case["method"], **case["plan"])
    payload = AnalysisService().run(frame, plan).model_dump(mode="json")
    method = canonical_method_name(case["method"])
    if method == "descriptive_statistics":
        variable = case["plan"]["dependent_variables"][0]
        row = next(item for item in payload["descriptive_stats"] if item["variable"] == variable)
        return {"statistic": float(row["mean"]), "p_value": math.nan, "df_num": math.nan, "df_den": math.nan}
    if method == "linear_mixed_model":
        covariate = case["plan"]["covariates"][0]
        candidates = {covariate, f'Q("{covariate}")'}
        row = next(item for item in payload["coefficients"] if item["term"] in candidates)
        return {"statistic": float(row["estimate"]), "p_value": math.nan, "df_num": math.nan, "df_den": math.nan}
    if method in MANOVA_METHODS:
        row = next(item for item in payload["omnibus_tests"] if item.get("statistic_name") == "Pillai 轨迹")
        return {
            "statistic": float(row["statistic_value"]), "p_value": float(row["p_value"]),
            "df_num": float(row["df_num"]), "df_den": float(row["df_den"]),
        }
    if method in ANOVA_METHODS:
        row = payload["omnibus_tests"][0]
        return {
            "statistic": float(row["f_value"]), "p_value": float(row["p_value"]),
            "df_num": float(row["df_num"]), "df_den": float(row["df_den"]),
        }
    row = payload["primary_tests"][0]
    return {
        "statistic": float(row["statistic_value"]),
        "p_value": (
            math.nan if method == "cohen_kappa"
            else float(row["p_value"]) if row.get("p_value") is not None else math.nan
        ),
        "df_num": float(row["df_num"]) if row.get("df_num") is not None else math.nan,
        "df_den": float(row["df_den"]) if row.get("df_den") is not None else math.nan,
    }


def read_r_metrics(path: Path) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result[row["method"]] = {
                key: float(row[key]) if row.get(key, "") not in {"", "NA"} else math.nan
                for key in ("statistic", "p_value", "df_num", "df_den")
            }
    return result


def close_enough(method: str, field: str, actual: float, expected: float) -> bool:
    if math.isnan(actual) and math.isnan(expected):
        return True
    if math.isnan(actual) != math.isnan(expected):
        return False
    tolerance = LOOSER_TOLERANCES.get(method, 2e-6)
    if field.startswith("df_"):
        tolerance = 1e-7
    return bool(np.isclose(actual, expected, rtol=tolerance, atol=tolerance, equal_nan=True))


def compare(rscript: Path) -> dict:
    cases = selected_cases()
    with tempfile.TemporaryDirectory(prefix="datawork_all_methods_r_") as directory:
        output = Path(directory) / "r_metrics.csv"
        completed = subprocess.run(
            [str(rscript), str(R_SCRIPT), str(ROOT), str(MANIFEST), str(output)],
            cwd=ROOT, check=True, text=True, capture_output=True, encoding="utf-8",
        )
        r_metrics = read_r_metrics(output)
    failures: list[dict] = []
    compared_fields = 0
    for case in cases:
        method = canonical_method_name(case["method"])
        if method not in r_metrics:
            failures.append({"method": method, "field": "coverage", "message": "R 未输出该方法"})
            continue
        python_values = python_metric(case)
        for field, python_value in python_values.items():
            r_value = r_metrics[method][field]
            if math.isnan(python_value) and math.isnan(r_value):
                continue
            compared_fields += 1
            if not close_enough(method, field, python_value, r_value):
                failures.append({
                    "method": method, "field": field,
                    "python": python_value, "r": r_value,
                })
    return {
        "r_version": completed.stdout.splitlines()[0] if completed.stdout else "",
        "methods": len(cases), "compared_fields": compared_fields,
        "passed": not failures, "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rscript")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = compare(locate_rscript(args.rscript))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["r_version"])
        print(f"R/Python 方法覆盖：{result['methods']}；比较字段：{result['compared_fields']}；失败：{len(result['failures'])}")
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
