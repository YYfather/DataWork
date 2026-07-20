"""DataWork 跨平台首次安装器。"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"


def run(command: list[str]) -> None:
    print("+", " ".join(map(str, command)))
    subprocess.run(command, cwd=ROOT, check=True)


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 DataWork 本地环境并安装依赖")
    parser.add_argument("--dev", action="store_true", help="安装测试工具")
    parser.add_argument("--legacy-ui", action="store_true", help="安装旧版 Streamlit 界面")
    parser.add_argument("--legacy-excel", action="store_true", help="安装旧版 XLS 支持")
    parser.add_argument("--desktop-build", action="store_true", help="安装 PyInstaller 构建工具")
    parser.add_argument("--recreate", action="store_true", help="删除并重建现有 .venv")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        raise SystemExit(
            f"DataWork 需要 Python 3.11 或更高版本；当前为 {sys.version.split()[0]}。"
        )

    if args.recreate and VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    if not VENV_DIR.exists():
        print(f"创建虚拟环境: {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    python = venv_python()
    if not python.exists():
        raise SystemExit(f"虚拟环境创建失败，未找到: {python}")

    extras: list[str] = []
    for enabled, name in [
        (args.dev, "dev"),
        (args.legacy_ui, "legacy-ui"),
        (args.legacy_excel, "legacy-excel"),
        (args.desktop_build, "desktop-build"),
    ]:
        if enabled:
            extras.append(name)

    install_target = str(ROOT)
    if extras:
        install_target += f"[{','.join(extras)}]"

    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "-e", install_target])
    print("\n安装完成。现在可运行:")
    if sys.platform == "win32":
        print(r"  scripts\run_datawork.bat")
    elif sys.platform == "darwin":
        print("  scripts/run_datawork.command")
    else:
        print("  ./scripts/run_datawork.sh")


if __name__ == "__main__":
    main()
