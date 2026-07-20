"""在当前操作系统构建 DataWork Python sidecar。

PyInstaller 不支持可靠的跨系统交叉编译，因此 Windows、Linux、macOS 必须分别
在对应系统或 CI runner 上运行。构建结果与 Tauri ``externalBin`` 契约一致，
名称固定为 ``datawork-sidecar``（Windows 自动附加 .exe）。
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-frontend", action="store_true", help="复用包内已构建静态资源")
    parser.add_argument("--reuse-sidecar", action="store_true", help="复用 dist 中现有 sidecar，仅补做哈希、冒烟和 Tauri 复制")
    parser.add_argument("--skip-smoke", action="store_true", help="跳过生成后独立进程冒烟测试")
    parser.add_argument("--tauri-target", help="复制为 Tauri target triple sidecar，例如 x86_64-pc-windows-msvc")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frontend = ROOT / "frontend"
    static_index = ROOT / "datawork" / "web" / "static" / "index.html"
    if not args.skip_frontend:
        if shutil.which("npm"):
            run(["npm", "ci", "--no-audit", "--no-fund"], frontend)
            run(["npm", "run", "build"], frontend)
        elif not static_index.exists():
            raise SystemExit("未找到 npm，且不存在已构建的网页静态文件。")
    elif not static_index.exists():
        raise SystemExit("--skip-frontend 需要包内已有 datawork/web/static/index.html")

    suffix = ".exe" if sys.platform.startswith("win") else ""
    artifact = ROOT / "dist" / f"datawork-sidecar{suffix}"
    if not args.reuse_sidecar:
        try:
            import PyInstaller  # noqa: F401
        except ImportError as exc:
            raise SystemExit("缺少 PyInstaller。请先执行: pip install -e '.[desktop-build]'") from exc
        run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "packaging/datawork_web.spec"])
    if not artifact.exists():
        raise SystemExit(f"PyInstaller 未生成预期产物: {artifact}")
    hash_value = sha256(artifact)
    hash_path = artifact.with_suffix(artifact.suffix + ".sha256")
    hash_path.write_text(f"{hash_value}  {artifact.name}\n", encoding="utf-8")
    print(f"构建完成: {artifact}")
    print(f"SHA-256: {hash_value}")

    if not args.skip_smoke:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        run([
            sys.executable, str(ROOT / "scripts" / "smoke_sidecar.py"), str(artifact),
            "--expected-version", version,
        ])

    if args.tauri_target:
        target_name = f"datawork-sidecar-{args.tauri_target}{suffix}"
        destination = ROOT / "desktop" / "src-tauri" / "binaries" / target_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, destination)
        destination.with_suffix(destination.suffix + ".sha256").write_text(
            f"{hash_value}  {destination.name}\n", encoding="utf-8"
        )
        print(f"已准备 Tauri sidecar: {destination}")


if __name__ == "__main__":
    main()
