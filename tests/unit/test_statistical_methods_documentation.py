from __future__ import annotations

import re
from pathlib import Path

from datawork.core.method_registry import list_methods


ROOT = Path(__file__).resolve().parents[2]
METHOD_ID_PATTERN = re.compile(r"\*\*方法 ID\*\*：`([^`]+)`")


def test_statistical_methods_document_every_runnable_method_and_dependencies() -> None:
    document = (ROOT / "docs" / "STATISTICAL_METHODS.md").read_text(encoding="utf-8")
    documented = set(METHOD_ID_PATTERN.findall(document))
    runnable = {method.name for method in list_methods(runnable_only=True)}
    dependency_matrix = document.split("### 统计方法—主要后端矩阵", 1)[1].split("### 项目组升级与复核规则", 1)[0]
    mapped = set(re.findall(r"（`([a-z][a-z0-9_]*)`）", dependency_matrix))

    assert runnable == documented, f"统计方法正文差异：缺少 {sorted(runnable - documented)}；多余 {sorted(documented - runnable)}"
    assert runnable == mapped, f"依赖矩阵差异：缺少 {sorted(runnable - mapped)}；多余 {sorted(mapped - runnable)}"
    assert "项目组：计算核心与依赖包对照" in document
    for dependency in ("pandas>=2.0", "numpy>=1.26", "scipy>=1.11", "statsmodels>=0.14", "patsy"):
        assert dependency in document


def test_readme_links_computation_core_dependency_manual() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[统计方法与计算核心依赖手册（含项目组方法—依赖矩阵）](docs/STATISTICAL_METHODS.md)" in readme
