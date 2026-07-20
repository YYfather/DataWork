#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

if command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/setup_datawork.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python scripts/setup_datawork.py "$@"
else
  echo "未找到 Python 3.11 或更高版本。" >&2
  exit 1
fi
