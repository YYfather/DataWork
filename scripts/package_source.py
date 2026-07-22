#!/usr/bin/env python3
"""生成清洁的 DataWork 完整源码 ZIP 和 SHA-256 清单。"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    ".venv", "venv", "node_modules", "build", "dist", "发布包", "target", "wheelhouse",
    "datawork.egg-info", ".audit", ".test-runtime", ".tmp", ".cache",
}
EXCLUDED_DIR_PREFIXES = (".pytest-", ".tmp-")
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".tsbuildinfo"}
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", "SOURCE_MANIFEST_SHA256.txt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    parser.add_argument("--name", help="输出目录/ZIP 基名；默认 DataWork-v<VERSION>-Full-Source")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if any(part.startswith(EXCLUDED_DIR_PREFIXES) for part in relative.parts):
            continue
        if relative.parts[:3] == ("desktop", "src-tauri", "binaries"):
            continue
        if not path.is_file() or path.name in EXCLUDED_NAMES:
            continue
        if path.name.startswith(".ui-"):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def main() -> int:
    args = parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    base = args.name or f"DataWork-v{version}-Full-Source"
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    final_dir = output_dir / base
    zip_path = output_dir / f"{base}.zip"
    zip_hash_path = output_dir / f"{base}.zip.sha256"

    files = included_files()
    with tempfile.TemporaryDirectory(prefix="datawork-source-") as temp:
        staging = Path(temp) / base
        staging.mkdir(parents=True)
        for source in files:
            relative = source.relative_to(ROOT)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        manifest_lines = []
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                manifest_lines.append(f"{sha256(path)}  {path.relative_to(staging).as_posix()}")
        (staging / "SOURCE_MANIFEST_SHA256.txt").write_text(
            "\n".join(manifest_lines) + "\n", encoding="utf-8"
        )

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.copytree(staging, final_dir)
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(base) / path.relative_to(staging))

    digest = sha256(zip_path)
    zip_hash_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(f"source directory: {final_dir}")
    print(f"source zip: {zip_path}")
    print(f"sha256: {digest}")
    print(f"files: {len(files) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
