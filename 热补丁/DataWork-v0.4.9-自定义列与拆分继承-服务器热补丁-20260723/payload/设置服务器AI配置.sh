#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
PATCH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

fail() {
  printf '[DataWork AI 配置] 错误：%s\n' "$*" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "虚拟环境 Python 不可执行：$APP_DIR/.venv/bin/python"
[[ -f "$PATCH_DIR/configure_server_ai.py" ]] || fail "缺少 configure_server_ai.py"

APP_OWNER="$(stat -c '%U' "$APP_DIR/data")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/data")"

PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" \
  "$PATCH_DIR/configure_server_ai.py" --app-dir "$APP_DIR"

CONFIG_DIR="$APP_DIR/data/server_ai"
chown -R "$APP_OWNER:$APP_GROUP" "$CONFIG_DIR"
chmod 0700 "$CONFIG_DIR"
find "$CONFIG_DIR" -maxdepth 1 -type f -exec chmod 0600 {} +

printf '[DataWork AI 配置] 已设置所有者为 %s:%s，目录权限 700，文件权限 600。\n' "$APP_OWNER" "$APP_GROUP"
printf '[DataWork AI 配置] 配置立即生效，一般无需再次重启。请刷新网页后查看 AI 设置。\n'
