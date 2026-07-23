"""开发期 R/Python 对照：验证 V1.6 配对公式数学绝对值。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datawork.core.formula import evaluate_formula  # noqa: E402
from scripts.compare_all_methods_r import locate_rscript  # noqa: E402


R_SCRIPT = ROOT / "tests" / "reference" / "r" / "validate_pairing_abs_v16.R"
FORMULAS = {
    "abs_treatment": "abs([处理值])",
    "abs_control": "abs([对照值])",
    "abs_difference": "abs([处理值] - [对照值])",
    "abs_relative": "abs(([处理值] - [对照值]) / [对照值])",
}


def python_values() -> pd.DataFrame:
    operands = pd.DataFrame({
        "case_id": range(1, 7),
        "处理值": [-3.0, 2.0, 0.0, np.nan, 5.0, -7.0],
        "对照值": [1.0, -5.0, 0.0, 4.0, np.nan, -7.0],
    })
    result = operands.rename(
        columns={"处理值": "treatment", "对照值": "control"}
    ).copy()
    formula_frame = operands[["处理值", "对照值"]]
    for name, formula in FORMULAS.items():
        computed = evaluate_formula(
            formula_frame,
            formula,
            allowed_columns=["处理值", "对照值"],
            require_brackets=True,
            basic_arithmetic_only=True,
            allow_abs=True,
        )
        result[name] = pd.to_numeric(computed, errors="coerce").replace(
            [np.inf, -np.inf],
            np.nan,
        )
    return result


def compare(rscript: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="datawork_v16_abs_r_") as directory:
        output = Path(directory) / "pairing_abs.csv"
        completed = subprocess.run(
            [str(rscript), str(R_SCRIPT), str(output)],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )
        r_values = pd.read_csv(output)
    actual = python_values()
    columns = ["treatment", "control", *FORMULAS]
    failures: list[str] = []
    for column in columns:
        if not np.allclose(
            actual[column].to_numpy(dtype=float),
            r_values[column].to_numpy(dtype=float),
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        ):
            failures.append(column)
    return {
        "r_version": completed.stdout.strip(),
        "cases": len(actual),
        "formulas": len(FORMULAS),
        "passed": not failures,
        "failures": failures,
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
        print(
            f"V1.6 abs R/Python 对照：{result['cases']} 个案例，"
            f"{result['formulas']} 个公式，失败={result['failures']}"
        )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
