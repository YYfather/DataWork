#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
SERVICE_NAME="${DATAWORK_SUPERVISOR_NAME:-}"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v17_core_manova_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
ROOT_FILES=(
  "README.md"
  "VERSION"
  "pyproject.toml"
)

log() { printf '[DataWork 1.5.0→1.7.0 热补丁回滚] %s\n' "$*"; }
fail() { printf '[DataWork 1.5.0→1.7.0 热补丁回滚] 错误：%s\n' "$*" >&2; exit 1; }


supervisor_controllers() {
  printf '%s\n' \
    "$(command -v supervisorctl 2>/dev/null || true)" \
    "/usr/bin/supervisorctl" "/usr/local/bin/supervisorctl" \
    "/www/server/panel/pyenv/bin/supervisorctl" \
    "/www/server/panel/plugin/supervisor/supervisorctl" | awk 'NF && !seen[$0]++'
}

restart_service() {
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  while IFS= read -r controller; do
    [[ -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then
      return 0
    fi
    [[ -n "$target_pid" ]] || continue
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$("$controller" pid "$name" 2>/dev/null || true)"
      if [[ "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then
        SERVICE_NAME="$name"
        return 0
      fi
    done < <("$controller" status 2>/dev/null || true)
  done < <(supervisor_controllers)
  if [[ -n "$SERVICE_NAME" ]] && command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files "$SERVICE_NAME.service" --no-legend 2>/dev/null \
      | grep -q "$SERVICE_NAME.service"; then
    systemctl restart "$SERVICE_NAME.service"
    return 0
  fi
  return 1
}


[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ "$APP_DIR" == "$DEFAULT_APP_DIR" || -n "${DATAWORK_APP_DIR:-}" ]]   || fail "目标路径异常：$APP_DIR"
[[ -f "$BACKUP_MARKER" ]] || fail "没有找到本次热补丁的备份标记。"
BACKUP_DIR="$(tr -d '\r\n' < "$BACKUP_MARKER")"
case "$BACKUP_DIR" in
  "$BACKUP_ROOT"/*) ;;
  *) fail "备份路径不在允许目录内：$BACKUP_DIR" ;;
esac
[[ -d "$BACKUP_DIR/datawork" && -f "$BACKUP_DIR/root_files_present.txt" ]]   || fail "备份不完整：$BACKUP_DIR"

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
log "恢复完整程序备份：$BACKUP_DIR"
rm -rf -- "$APP_DIR/datawork"
cp -a "$BACKUP_DIR/datawork" "$APP_DIR/datawork"
for relative in "${ROOT_FILES[@]}"; do
  if grep -Fxq "$relative" "$BACKUP_DIR/root_files_present.txt"; then
    cp -a "$BACKUP_DIR/root/$relative" "$APP_DIR/$relative"
  else
    rm -f -- "$APP_DIR/$relative"
  fi
done
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${ROOT_FILES[@]}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done
rm -f -- "$BACKUP_MARKER"

if ! restart_service; then
  log "程序文件已恢复，但未识别到进程守护名称。"
  log "请在宝塔面板手动重启 DataWork。"
  exit 2
fi
for _ in $(seq 1 30); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    log "回滚完成，服务已恢复。保留备份目录供审计：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "文件已恢复，但服务未在 30 秒内通过健康检查。"
