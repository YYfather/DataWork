#!/usr/bin/env bash
set -Eeuo pipefail

PATCH_ID="datawork_0.4.9_derived_split_20260723"
DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
SERVICE_NAME="${DATAWORK_SUPERVISOR_NAME:-}"
BACKUP_MARKER="$APP_DIR/updates/.last_derived_split_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
ROOT_FILES=(
  "README.md"
  "VERSION"
  "bt_start.py"
  "pyproject.toml"
  "requirements.txt"
  "宝塔面板部署说明.txt"
  "服务器环境准备.sh"
  "configure_server_ai.py"
  "设置工作区密码.sh"
  "设置服务器AI配置.sh"
)

log() { printf '[DataWork 自定义列热补丁回滚] %s
' "$*"; }
fail() { printf '[DataWork 自定义列热补丁回滚] 错误：%s
' "$*" >&2; exit 1; }

restart_service() {
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  for controller in "$(command -v supervisorctl 2>/dev/null || true)" /usr/bin/supervisorctl /usr/local/bin/supervisorctl /www/server/panel/pyenv/bin/supervisorctl /www/server/panel/plugin/supervisor/supervisorctl; do
    [[ -n "$controller" && -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then return 0; fi
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$($controller pid "$name" 2>/dev/null || true)"
      if [[ -n "$target_pid" && "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then return 0; fi
    done < <("$controller" status 2>/dev/null || true)
  done
  return 1
}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ -f "$BACKUP_MARKER" ]] || fail "未找到最近一次补丁备份记录：$BACKUP_MARKER"
BACKUP_DIR="$(head -n 1 "$BACKUP_MARKER")"
EXPECTED_PREFIX="$APP_DIR/updates/backups/${PATCH_ID}_"
[[ "$BACKUP_DIR" == "$EXPECTED_PREFIX"* && -d "$BACKUP_DIR/datawork" ]] || fail "备份路径无效：$BACKUP_DIR"

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
FAILED_DIR="$APP_DIR/updates/failed_${PATCH_ID}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$FAILED_DIR/root"
log "保留当前失败版本到：$FAILED_DIR"
mv "$APP_DIR/datawork" "$FAILED_DIR/datawork"
cp -a "$BACKUP_DIR/datawork" "$APP_DIR/datawork"

for relative in "${ROOT_FILES[@]}"; do
  if grep -Fxq "$relative" "$BACKUP_DIR/root_files_present.txt"; then
    [[ -f "$APP_DIR/$relative" ]] && cp -a "$APP_DIR/$relative" "$FAILED_DIR/root/$relative"
    cp -a "$BACKUP_DIR/root/$relative" "$APP_DIR/$relative"
  elif [[ -e "$APP_DIR/$relative" ]]; then
    mv "$APP_DIR/$relative" "$FAILED_DIR/root/$relative"
  fi
done
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"

if restart_service; then
  for _ in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      log "回滚成功，服务健康检查正常。"
      exit 0
    fi
    sleep 1
  done
  fail "文件已恢复，但服务未通过健康检查。"
fi
log "文件已恢复，请在宝塔进程守护管理器中手动重启 DataWork。"
exit 2
