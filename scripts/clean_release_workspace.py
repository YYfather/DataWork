#!/usr/bin/env python3
"""Safely remove reproducible local artifacts before a DataWork release."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
ROOT_CACHE_NAMES = {
    ".audit",
    ".pytest_cache",
    ".test-runtime",
    ".tmp",
    "dist",
}
ROOT_CACHE_PREFIXES = (".pytest-", ".tmp-pytest-")
RECURSIVE_CACHE_NAMES = {"__pycache__", ".mypy_cache", ".ruff_cache", ".vite"}
GENERATED_FILE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".tsbuildinfo"}
REPRODUCIBLE_DEPENDENCY_DIRS = (
    ".r-validation-lib",
    "frontend/node_modules",
    "desktop/node_modules",
    "desktop/src-tauri/target",
)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="execute deletion; default is dry-run")
    parser.add_argument(
        "--dependencies",
        action="store_true",
        help="also remove reproducible R, Node.js and Rust dependency/build directories",
    )
    parser.add_argument(
        "--old-releases",
        action="store_true",
        help="remove the complete superseded local 发布包 directory",
    )
    return parser.parse_args()


def within_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def artifact_targets(*, include_dependencies: bool = False, include_old_releases: bool = False) -> list[Path]:
    targets: set[Path] = set()
    for child in ROOT.iterdir():
        if child.is_dir() and (
            child.name in ROOT_CACHE_NAMES
            or child.name.startswith(ROOT_CACHE_PREFIXES)
        ):
            targets.add(child)
        elif child.is_file() and child.name.startswith(".ui-"):
            targets.add(child)

    excluded_walk_roots = {".venv", "venv", "node_modules", "target", ".git"}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in excluded_walk_roots for part in relative.parts):
            continue
        if path.is_dir() and path.name in RECURSIVE_CACHE_NAMES:
            targets.add(path)
        elif path.is_file() and path.suffix.lower() in GENERATED_FILE_SUFFIXES:
            targets.add(path)

    binary_root = ROOT / "desktop" / "src-tauri" / "binaries"
    if binary_root.exists():
        targets.update(binary_root.glob("datawork-sidecar-*"))
    if include_dependencies:
        targets.update(ROOT / relative for relative in REPRODUCIBLE_DEPENDENCY_DIRS if (ROOT / relative).exists())
    if include_old_releases:
        release_root = ROOT / "发布包"
        if release_root.is_dir():
            targets.add(release_root)
    return sorted(targets, key=lambda item: (len(item.parts), item.as_posix()), reverse=True)


def path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    args = parse_args()
    targets = artifact_targets(
        include_dependencies=args.dependencies,
        include_old_releases=args.old_releases,
    )
    total = sum(path_size(path) for path in targets if path.exists())
    action = "REMOVE" if args.apply else "DRY-RUN"
    for path in targets:
        if not within_root(path):
            raise RuntimeError(f"refusing target outside workspace: {path}")
        print(f"{action} {path.relative_to(ROOT).as_posix()}")
    print(f"targets: {len(targets)}")
    print(f"bytes: {total}")
    if not args.apply:
        print("No files removed. Re-run with --apply after reviewing the targets.")
        return 0
    for path in targets:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    print("Release workspace artifacts removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
