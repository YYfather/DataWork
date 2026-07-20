#!/bin/zsh
set -e
SCRIPT_DIR="${0:A:h}"
cd "${SCRIPT_DIR:h}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m datawork.web "$@"
else
  exec python3 -m datawork.web "$@"
fi
