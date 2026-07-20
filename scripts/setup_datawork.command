#!/bin/zsh
set -e
SCRIPT_DIR="${0:A:h}"
cd "${SCRIPT_DIR:h}"
exec python3 scripts/setup_datawork.py "$@"
