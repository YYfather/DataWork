"""重建 Vue 前端并写入 Python 包静态目录。"""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

if not shutil.which("npm"):
    raise SystemExit("未找到 npm。请安装 Node.js LTS。")
subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)
subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True)
