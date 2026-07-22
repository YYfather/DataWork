#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

echo "========================================"
echo "       DataWork macOS 本地安装"
echo "========================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3.11 或更高版本。"
  echo "下载地址：https://www.python.org/downloads/macos/"
  echo
  read "?按回车键关闭窗口……"
  exit 1
fi

python3 scripts/setup_datawork.py --legacy-excel

echo
echo "安装完成。以后请双击“启动 DataWork.command”。"
read "?按回车键关闭窗口……"
