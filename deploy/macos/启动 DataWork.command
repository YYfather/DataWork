#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "尚未完成安装。请先双击“安装 DataWork.command”。"
  read "?按回车键关闭窗口……"
  exit 1
fi

PORT="${DATAWORK_PORT:-8765}"
echo "正在启动 DataWork……"
echo "浏览器地址：http://127.0.0.1:${PORT}"
echo "关闭本窗口即可停止 DataWork。"
echo

exec .venv/bin/python -m datawork.web \
  --host 127.0.0.1 \
  --port "$PORT"
