"""开发期 R 对照：验证派生列、专业拆分和 Python ANOVA 核心。"""

from __future__ import annotations

import argparse
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

from datawork.application.analysis_service import AnalysisService
from datawork.core.formula import apply_derived_columns
from datawork.core.plan import AnalysisPlan, DerivedColumn


REFERENCE = ROOT / "tests" / "reference" / "r"
DEFAULT_RSCRIPT = Path(r"C:\Program Files\R\R-4.6.1\bin\Rscript.exe")


def _rscript(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
    elif DEFAULT_RSCRIPT.exists():
        candidate = DEFAULT_RSCRIPT
    else:
        located = shutil.which("Rscript")
        if not located:
            raise FileNotFoundError("未找到 Rscript；可使用 --rscript 指定开发解释器")
        candidate = Path(located).resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Rscript 不存在: {candidate}")
    return candidate


def _assert_close(label: str, actual, expected, tolerance: float = 1e-8) -> None:
    if not np.isclose(float(actual), float(expected), rtol=tolerance, atol=tolerance, equal_nan=True):
        raise AssertionError(f"{label}: Python={actual!r}, R={expected!r}")


def _load_agronomy_source(source: Path) -> pd.DataFrame:
    raw = pd.read_csv(source).iloc[:, :7].copy()
    raw.columns = ["year", "variety", "spray", "mode", "DR7", "DR14", "DR21"]
    for column in ("DR7", "DR14", "DR21"):
        raw[column] = pd.to_numeric(raw[column].astype(str).str.replace("%", "", regex=False), errors="coerce") / 100
    for column in ("year", "variety", "spray", "mode"):
        raw[column] = raw[column].astype(str).str.strip()
    return raw.dropna(subset=["DR7", "DR14", "DR21"]).reset_index(drop=True)


def _agronomy_pair_columns() -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = []
    for day in ("7", "14", "21"):
        definitions.extend([
            {"id": f"ndr-{day}", "name": f"NDR{day}", "source_column": f"DR{day}", "formula": "[对照值]", "unit": "比例", "decimal_places": 8},
            {"id": f"delta-{day}", "name": f"Delta{day}", "source_column": f"DR{day}", "formula": "[处理值] - [对照值]", "unit": "百分点差", "decimal_places": 8},
        ])
    return definitions


def _agronomy_plan(method: str) -> AnalysisPlan:
    outcomes = [f"{kind}{day}" for day in ("7", "14", "21") for kind in ("NDR", "Delta")]
    is_manova = method == "twoway_manova"
    return AnalysisPlan(
        interface_mode="professional",
        method=method,
        dependent_variables=outcomes,
        dependent_variable_groups=(
            [{"name": f"{day}d", "dependent_variables": [f"NDR{day}", f"Delta{day}"]} for day in ("7", "14", "21")]
            if is_manova else []
        ),
        fixed_factors=["variety", "spray"],
        split_by=["year"],
        pairing={
            "group_column": "spray",
            "mappings": [
                {"treatment": "T1", "control": "CK1"},
                {"treatment": "T2", "control": "CK2"},
                {"treatment": "T3", "control": "CK3"},
            ],
            "match_columns": ["year", "variety", "mode"],
            "pair_id_column": None,
            "derived_columns": _agronomy_pair_columns(),
        },
        ss_type=3,
        method_parameters=(
            {
                "multivariate_test": "wilks", "primary_multivariate_test": "wilks",
                "follow_up_mode": "none", "posthoc_scope": "branch_all",
                "covariance_test": False, "normality_test": False,
                "correlation_diagnostics": False,
            }
            if is_manova else {"posthoc_methods": ["none"]}
        ),
        diagnostic_plots=False,
    )


def _prepare_agronomy_frame(source: Path) -> pd.DataFrame:
    paired, audit, warnings = AnalysisService.prepare_frame(
        _load_agronomy_source(source), _agronomy_plan("twoway_anova")
    )
    if warnings:
        raise AssertionError(f"测试数据2不应产生无效派生值: {warnings}")
    if not audit or audit[0].get("successful_pairs") != 108:
        raise AssertionError(f"V1.5 配对审计不正确: {audit}")
    return paired.rename(columns={"__dw_pair_sequence": "rep_id"})


def _normalized_effect(value: str) -> str:
    return str(value).replace(" × ", ":").replace("×", ":").replace(" ", "")


def _compare_agronomy(rscript: Path) -> None:
    source = REFERENCE / "agronomy_example_2.csv"
    source_frame = _load_agronomy_source(source)
    frame = _prepare_agronomy_frame(source)
    outcomes = [f"{kind}{day}" for day in ("7", "14", "21") for kind in ("NDR", "Delta")]

    with tempfile.TemporaryDirectory(prefix="datawork_r_agronomy_") as directory:
        output = Path(directory)
        subprocess.run(
            [str(rscript), str(REFERENCE / "validate_agronomy_example_2.R"), str(source), str(output)],
            check=True, cwd=ROOT,
        )

        keys = ["year", "variety", "spray", "mode", "rep_id"]
        python_derived = frame[keys + outcomes].sort_values(keys).reset_index(drop=True)
        r_derived = pd.read_csv(output / "agronomy_derived.csv", dtype={"year": str}).sort_values(keys).reset_index(drop=True)
        if python_derived[keys].astype(str).to_dict("records") != r_derived[keys].astype(str).to_dict("records"):
            raise AssertionError("农业数据 CK/T 配对键与 R 不一致")
        if not np.allclose(
            python_derived[outcomes].to_numpy(dtype=float), r_derived[outcomes].to_numpy(dtype=float),
            rtol=1e-12, atol=1e-12, equal_nan=True,
        ):
            raise AssertionError("农业数据 NDR/Delta 派生值与 R 不一致")

        anova_execution = AnalysisService().execute(source_frame, _agronomy_plan("twoway_anova"))
        r_anova = pd.read_csv(output / "agronomy_anova.csv", dtype={"year": str})
        r_anova["effect_key"] = r_anova["effect"].map(_normalized_effect)
        r_anova = r_anova.set_index(["year", "outcome", "effect_key"])
        compared_anova = 0
        for item in anova_execution.result.results:
            if item.error or item.result is None:
                raise AssertionError(f"Python 双因素 ANOVA 批次失败: {item.error}")
            year = str(item.subset_info["year"])
            outcome = str(item.subset_info["dependent_variable"])
            for test in item.result.omnibus_tests:
                expected = r_anova.loc[(year, outcome, _normalized_effect(test.effect))]
                label = f"ANOVA {year}/{outcome}/{test.effect}"
                _assert_close(f"{label} df_num", test.df_num, expected["df_num"])
                _assert_close(f"{label} df_den", test.df_den, expected["df_den"])
                _assert_close(f"{label} F", test.f_value, expected["f_value"], 1e-7)
                _assert_close(f"{label} p", test.p_value, expected["p_value"], 1e-7)
                compared_anova += 1
        if compared_anova != 36:
            raise AssertionError(f"预期比较 36 个 ANOVA 效应，实际 {compared_anova}")

        r_manova = pd.read_csv(output / "agronomy_manova.csv", dtype={"year": str})
        r_manova["effect_key"] = r_manova["effect"].map(_normalized_effect)
        r_manova = r_manova.set_index(["year", "day", "effect_key"])
        compared_manova = 0
        execution = AnalysisService().execute(source_frame, _agronomy_plan("twoway_manova"))
        if len(execution.result.results) != 6:
            raise AssertionError(f"预期 3 个联合因变量组 × 2 个年份 = 6 个任务，实际 {len(execution.result.results)}")
        for item in execution.result.results:
            if item.error or item.result is None:
                raise AssertionError(f"Python MANOVA 批次失败: {item.error}")
            year = str(item.subset_info["year"])
            day_label = str(item.subset_info["dependent_group"])
            for test in item.result.omnibus_tests:
                expected = r_manova.loc[(year, day_label, _normalized_effect(test.effect))]
                label = f"MANOVA {year}/{day_label}/{test.effect}"
                _assert_close(f"{label} Wilks", test.statistic_value, expected["statistic_value"], 1e-7)
                _assert_close(f"{label} df_num", test.df_num, expected["df_num"], 1e-7)
                _assert_close(f"{label} df_den", test.df_den, expected["df_den"], 1e-7)
                _assert_close(f"{label} F", test.f_value, expected["f_value"], 1e-7)
                _assert_close(f"{label} p", test.p_value, expected["p_value"], 1e-7)
                compared_manova += 1
        if compared_manova != 18:
            raise AssertionError(f"预期比较 18 个 MANOVA 效应，实际 {compared_manova}")

        version = (output / "r_version.txt").read_text(encoding="utf-8").strip()
        print(version)
        print("测试数据2：R 与 Python 的 108 组配对派生值、36 个 Type III ANOVA 效应和 18 个 Wilks MANOVA 效应一致")


def compare(rscript: Path) -> None:
    source = REFERENCE / "derived_split_factor.csv"
    frame = pd.read_csv(source)
    definitions = [
        DerivedColumn(name="平均值", formula="([x1] + [x2]) / 2", source_columns=["x1", "x2"]),
        DerivedColumn(name="比率", formula="[x2] / [x1]", source_columns=["x2", "x1"]),
    ]
    python_frame, _log, warnings = apply_derived_columns(frame, definitions)
    if not warnings:
        raise AssertionError("除零测试应产生派生列警告")

    with tempfile.TemporaryDirectory(prefix="datawork_r_reference_") as directory:
        output = Path(directory)
        subprocess.run(
            [str(rscript), str(REFERENCE / "validate_derived_split_factor.R"), str(source), str(output)],
            check=True,
            cwd=ROOT,
        )
        r_derived = pd.read_csv(output / "derived_values.csv")
        for column in ("平均值", "比率"):
            if not np.allclose(
                python_frame[column].to_numpy(dtype=float),
                r_derived[column].to_numpy(dtype=float),
                rtol=1e-10,
                atol=1e-10,
                equal_nan=True,
            ):
                raise AssertionError(f"派生列 {column} 与 R 不一致")

        plan = AnalysisPlan(
            interface_mode="professional",
            dependent_variables=["outcome"],
            fixed_factors=["factor"],
            split_by=["factor"],
            split_rules=[{
                "column": "factor", "kind": "categorical",
                "groups": [
                    {"label": "前组", "values": ["A", "B"]},
                    {"label": "后组", "values": ["C", "D"]},
                ],
            }],
            derived_columns=[item.model_dump(mode="json") for item in definitions],
            method="oneway_anova",
        )
        execution = AnalysisService().execute(frame, plan)
        r_summary = pd.read_csv(output / "split_summary.csv").set_index("split_group")
        r_anova = pd.read_csv(output / "anova_results.csv").set_index("split_group")
        for item in execution.result.results:
            label = str(item.subset_info["factor"])
            subset = python_frame.loc[
                python_frame["factor"].isin(["A", "B"] if label == "前组" else ["C", "D"])
            ]
            expected_summary = r_summary.loc[label]
            if len(subset) != int(expected_summary["n"]):
                raise AssertionError(f"{label} 样本量不一致")
            if subset["factor"].nunique() != int(expected_summary["factor_levels"]):
                raise AssertionError(f"{label} 因素水平数不一致")
            _assert_close(f"{label} outcome_mean", subset["outcome"].mean(), expected_summary["outcome_mean"])
            _assert_close(f"{label} derived_mean", subset["平均值"].mean(), expected_summary["derived_mean"])
            if item.result is None or not item.result.omnibus_tests:
                raise AssertionError(f"{label} 缺少 Python ANOVA 结果")
            test = item.result.omnibus_tests[0]
            expected_anova = r_anova.loc[label]
            _assert_close(f"{label} df_num", test.df_num, expected_anova["df_num"])
            _assert_close(f"{label} df_den", test.df_den, expected_anova["df_den"])
            _assert_close(f"{label} F", test.f_value, expected_anova["f_value"])
            _assert_close(f"{label} p", test.p_value, expected_anova["p_value"])
        print((output / "r_version.txt").read_text(encoding="utf-8").strip())
        print("R 与 Python 派生列、拆分摘要和 ANOVA 结果一致")
    _compare_agronomy(rscript)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rscript", help="Rscript.exe 路径；省略时优先使用已确认的 R 4.6.1 路径")
    args = parser.parse_args()
    compare(_rscript(args.rscript))


if __name__ == "__main__":
    main()
