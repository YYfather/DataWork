#!/usr/bin/env python3
"""DataWork 发布前结构与版本一致性检查。"""
from __future__ import annotations

import argparse
import compileall
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datawork import __version__  # noqa: E402
from datawork.application.executors import list_executor_names  # noqa: E402
from datawork.core.method_registry import list_methods  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-compile", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    desktop = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    observed = {
        "VERSION": version,
        "datawork.__version__": __version__,
        "pyproject": re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1),
        "frontend": frontend["version"],
        "desktop": desktop["version"],
        "tauri": tauri["version"],
        "cargo": re.search(r'^version = "([^"]+)"', cargo, re.M).group(1),
    }
    for source, value in observed.items():
        if value != version:
            failures.append(f"版本不一致: {source}={value}, VERSION={version}")

    methods = list(list_methods(runnable_only=True))
    registered = {item.executor for item in methods}
    executors = list_executor_names()
    missing = sorted(name for name in registered if name not in executors)
    unused = sorted(name for name in executors if name not in registered)
    if missing:
        failures.append(f"注册方法缺少执行器: {missing}")
    if unused:
        failures.append(f"存在未注册执行器: {unused}")

    required = [
        "datawork/web/static/index.html",
        "datawork/report/templates/report_zh.md.j2",
        "packaging/datawork_web.spec",
        "scripts/desktop_entry.py",
        "desktop/src-tauri/tauri.conf.json",
        "desktop/src-tauri/src/lib.rs",
        "docs/PACKAGING.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/RELEASE_READINESS_AUDIT_0.4.9.md",
        "docs/DESKTOP_PACKAGING_PREPARATION_0.4.9.md",
        "docs/GOLDEN_DATASET_AUDIT_0.4.9.md",
        "docs/USABILITY_OPTIMIZATION_0.4.9.md",
        "golden_datasets/manifest.json",
        "scripts/run_golden_validation.py",
        "scripts/smoke_sidecar.py",
        "scripts/package_portable.py",
        "desktop/package-lock.json",
        "docs/MANOVA_FIXED_METHODS_AUDIT_0.4.7.md",
        "scripts/package_source.py",
    ]
    for relative in required:
        if not (ROOT / relative).exists():
            failures.append(f"缺少发布文件: {relative}")
    assets = list((ROOT / "datawork/web/static/assets").glob("*.js"))
    if not assets:
        failures.append("缺少前端生产 JS 资源")
    spec_text = (ROOT / "packaging/datawork_web.spec").read_text(encoding="utf-8")
    if 'name="datawork-sidecar"' not in spec_text:
        failures.append("PyInstaller 产物名称未与 Tauri sidecar 契约对齐")
    if "ROOT = Path(SPECPATH).parent" not in spec_text or "parent.parent" in spec_text:
        failures.append("PyInstaller spec 根目录计算错误")
    if "binaries/datawork-sidecar" not in json.dumps(tauri, ensure_ascii=False):
        failures.append("Tauri externalBin 未指向 datawork-sidecar")
    docs_version_checks = {
        "README.md": f"# DataWork {version}",
        "docs/USER_MANUAL.md": f"# DataWork {version} 用户使用手册",
        "docs/STATISTICAL_METHODS.md": f"（{version}）",
    }
    for relative, marker in docs_version_checks.items():
        if marker not in (ROOT / relative).read_text(encoding="utf-8"):
            failures.append(f"文档版本未更新: {relative}")

    if not args.no_compile and not compileall.compile_dir(ROOT / "datawork", quiet=1):
        failures.append("Python compileall 失败")

    print("Release readiness summary")
    print(f"  version: {version}")
    print(f"  runnable methods: {len(methods)}")
    print(f"  executors: {len(executors)}")
    print(f"  frontend assets: {len(assets)}")
    if failures:
        for item in failures:
            print("FAIL", item)
        return 1
    print("All structural release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
