#!/usr/bin/env python3
"""按平台生成 DataWork 中文发布包和 SHA-256 校验文件。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import stat
import zipfile

from package_source import included_files


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "dist" / "platform-release"
RUNTIME_ROOT_FILES = ("VERSION", "pyproject.toml", "README.md")
IGNORED_PARTS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "dist", "build", "node_modules",
}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_files() -> list[Path]:
    files = [ROOT / name for name in RUNTIME_ROOT_FILES]
    for path in (ROOT / "datawork").rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.is_file() and path.suffix.lower() not in IGNORED_SUFFIXES:
            files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(ROOT).as_posix())


def entry_mode(name: str) -> int:
    if name.endswith((".sh", ".command")):
        return stat.S_IFREG | 0o755
    return stat.S_IFREG | 0o644


def write_zip_entry(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = entry_mode(name) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


def build_zip(
    destination: Path,
    root_name: str,
    entries: dict[str, bytes],
    *,
    manifest_name: str = "SHA256SUMS.txt",
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    manifest = "".join(
        f"{sha256_bytes(payload)}  {name}\n"
        for name, payload in sorted(entries.items())
    ).encode("utf-8")
    packaged_entries = dict(entries)
    packaged_entries[manifest_name] = manifest

    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
    ) as archive:
        for name, payload in sorted(packaged_entries.items()):
            write_zip_entry(archive, f"{root_name}/{name}", payload)

    digest = sha256_file(destination)
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8",
    )
    print(f"已生成：{destination}")
    print(f"SHA-256：{digest}")


def files_as_entries(files: list[Path]) -> dict[str, bytes]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_bytes()
        for path in files
    }


def build_source_package(output_dir: Path, version: str) -> None:
    entries = files_as_entries(included_files())
    entries["使用说明.txt"] = f"""DataWork {version} 完整源码包
===========================

本包包含 DataWork 的完整可审计源码，不包含虚拟环境、依赖缓存、构建缓存、
用户数据、API 密钥、Windows 可执行文件和历史发布产物。

常用入口：
- Windows 安装包：datework_window_setup.exe
- macOS 命令包：datework_macos_command.zip
- Linux 服务器包：datework_linux_server.zip
- 开发与本地运行说明：README.md
- 跨平台打包说明：docs/RELEASE_DEPLOYMENT_GUIDE.md

源码文件校验值记录在 SOURCE_MANIFEST_SHA256.txt。
""".encode("utf-8")
    build_zip(
        output_dir / "datework_source.zip",
        "datework_source",
        entries,
        manifest_name="SOURCE_MANIFEST_SHA256.txt",
    )


def build_macos_package(output_dir: Path) -> None:
    entries = files_as_entries(runtime_files())
    entries["scripts/setup_datawork.py"] = (ROOT / "scripts" / "setup_datawork.py").read_bytes()
    macos_root = ROOT / "deploy" / "macos"
    for path in sorted(macos_root.iterdir()):
        if path.is_file():
            entries[path.name] = path.read_bytes()
    build_zip(
        output_dir / "datework_macos_command.zip",
        "datework_macos_command",
        entries,
    )


def build_linux_package(output_dir: Path) -> None:
    entries = files_as_entries(runtime_files())
    linux_root = ROOT / "deploy" / "linux-server"
    for path in sorted(linux_root.iterdir()):
        if path.is_file():
            entries[path.name] = path.read_bytes()
    build_zip(
        output_dir / "datework_linux_server.zip",
        "datework_linux_server",
        entries,
    )


def locate_windows_setup(explicit: Path | None, output_dir: Path) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise SystemExit(f"Windows 安装包不存在：{candidate}")
        return candidate

    candidates = [
        path for path in (ROOT / "dist" / "release").glob("*中文安装版.exe")
        if path.name != "datework_window_setup.exe"
    ]
    candidates.extend(
        path for path in output_dir.glob("*中文安装版.exe")
        if path.name != "datework_window_setup.exe"
    )
    candidates = sorted(set(path.resolve() for path in candidates), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise SystemExit(
            "未找到已构建的中文 Windows Setup。请使用 --windows-setup 指定 NSIS 安装包，"
            "或使用 --skip-windows 仅生成其他平台包。"
        )
    return candidates[-1]


def build_windows_package(output_dir: Path, source: Path) -> None:
    destination = output_dir / "datework_window_setup.exe"
    output_dir.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    digest = sha256_file(destination)
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8",
    )
    print(f"已生成：{destination}")
    print(f"SHA-256：{digest}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成按平台拆分的 DataWork 中文发布包")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--windows-setup", type=Path, help="已有的中文 NSIS Setup EXE")
    parser.add_argument("--skip-windows", action="store_true", help="不生成 Windows Setup 别名")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    if not args.skip_windows:
        source = locate_windows_setup(args.windows_setup, output_dir)
        build_windows_package(output_dir, source)
    build_macos_package(output_dir)
    build_linux_package(output_dir)
    build_source_package(output_dir, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
