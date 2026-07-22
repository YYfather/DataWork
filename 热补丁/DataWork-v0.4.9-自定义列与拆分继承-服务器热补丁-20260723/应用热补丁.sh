#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_ID="datawork_0.4.9_derived_split_20260723"
DEFAULT_SITE_ROOT="/www/wwwroot/1490473838.cn"
DEFAULT_APP_DIR="$DEFAULT_SITE_ROOT/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
SERVICE_NAME="${DATAWORK_SUPERVISOR_NAME:-}"
PATCH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PAYLOAD_DIR="$PATCH_DIR/payload"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_DIR="$BACKUP_ROOT/${PATCH_ID}_$(date +%Y%m%d_%H%M%S)"
BACKUP_MARKER="$APP_DIR/updates/.last_derived_split_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
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

log() { printf '[DataWork 自定义列热补丁] %s
' "$*"; }
fail() { printf '[DataWork 自定义列热补丁] 错误：%s
' "$*" >&2; exit 1; }
normalized_sha() { tr -d '\r' < "$1" | sha256sum | awk '{print $1}'; }

manifest_matches() {
  local manifest="$1" relative expected actual
  while IFS='  ' read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$APP_DIR/$relative" ]] || return 1
    actual="$(normalized_sha "$APP_DIR/$relative")"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest"
}

supervisor_controllers() {
  printf '%s
'     "$(command -v supervisorctl 2>/dev/null || true)"     "/usr/bin/supervisorctl" "/usr/local/bin/supervisorctl"     "/www/server/panel/pyenv/bin/supervisorctl"     "/www/server/panel/plugin/supervisor/supervisorctl" | awk 'NF && !seen[$0]++'
}

restart_service() {
  local controller="" target_pid="" name="" state="" controller_pid=""
  target_pid="$(pgrep -fo "$APP_DIR/bt_start.py" 2>/dev/null || true)"
  while IFS= read -r controller; do
    [[ -x "$controller" ]] || continue
    if [[ -n "$SERVICE_NAME" ]] && "$controller" restart "$SERVICE_NAME"; then return 0; fi
    [[ -n "$target_pid" ]] || continue
    while read -r name state _; do
      [[ "$state" == "RUNNING" ]] || continue
      controller_pid="$($controller pid "$name" 2>/dev/null || true)"
      if [[ "$controller_pid" == "$target_pid" ]] && "$controller" restart "$name"; then
        SERVICE_NAME="$name"; return 0
      fi
    done < <("$controller" status 2>/dev/null || true)
  done < <(supervisor_controllers)
  if [[ -n "$SERVICE_NAME" ]] && command -v systemctl >/dev/null 2>&1     && systemctl list-unit-files "$SERVICE_NAME.service" --no-legend 2>/dev/null | grep -q "$SERVICE_NAME.service"; then
    systemctl restart "$SERVICE_NAME.service"; return 0
  fi
  return 1
}

[[ "$(id -u)" -eq 0 ]] || fail "请使用 root 用户运行。"
[[ "$APP_DIR" == "/www/wwwroot/1490473838.cn/datework" || -n "${DATAWORK_APP_DIR:-}" ]]   || fail "目标路径异常：$APP_DIR"
[[ -d "$APP_DIR/datawork" && -f "$APP_DIR/VERSION" ]] || fail "目标不是完整 DataWork 服务：$APP_DIR"
[[ "$(tr -d '[:space:]' < "$APP_DIR/VERSION")" == "0.4.9" ]] || fail "本补丁仅适用于 DataWork 0.4.9。"
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "未找到现有虚拟环境 Python：$APP_DIR/.venv/bin/python"
[[ -d "$APP_DIR/data" ]] || fail "缺少运行数据目录：$APP_DIR/data"
[[ -d "$PAYLOAD_DIR/datawork/web/static/assets" ]] || fail "补丁 payload 不完整。"

log "校验补丁自身 SHA-256……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt)

if manifest_matches "$PATCH_DIR/TARGET_GUARDS_SHA256.txt"   && [[ ! -e "$APP_DIR/datawork/ui.py" ]]   && [[ ! -e "$APP_DIR/datawork/web/static/assets/index-CPsr4TFv.js" ]]   && [[ ! -e "$APP_DIR/datawork/web/static/assets/index-mCJiNXhg.css" ]]; then
  log "目标已经是本热补丁版本，无需重复安装。"
  exit 0
fi

if ! manifest_matches "$PATCH_DIR/BASELINE_GUARDS_SHA256.txt"; then
  if [[ "${DATAWORK_ALLOW_BASELINE_MISMATCH:-0}" != "1" ]]; then
    fail "服务器程序文件与已审核基线不一致。为防止覆盖未知修改，安装已停止；如已人工核对，可设置 DATAWORK_ALLOW_BASELINE_MISMATCH=1 后重试。"
  fi
  log "警告：已按显式授权跳过基线不一致保护。"
fi

APP_OWNER="$(stat -c '%U' "$APP_DIR/datawork")"
APP_GROUP="$(stat -c '%G' "$APP_DIR/datawork")"
mkdir -p "$BACKUP_DIR/root"
log "完整备份当前程序到：$BACKUP_DIR"
cp -a "$APP_DIR/datawork" "$BACKUP_DIR/datawork"
: > "$BACKUP_DIR/root_files_present.txt"
for relative in "${ROOT_FILES[@]}"; do
  if [[ -f "$APP_DIR/$relative" ]]; then
    cp -a "$APP_DIR/$relative" "$BACKUP_DIR/root/$relative"
    printf '%s
' "$relative" >> "$BACKUP_DIR/root_files_present.txt"
  fi
done
printf '%s
' "$BACKUP_DIR" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"

log "覆盖最新运行源码；保留 .venv、data、updates 和全部用户数据……"
while IFS= read -r -d '' source; do
  relative="${source#$PAYLOAD_DIR/}"
  install -D -m 0644 "$source" "$APP_DIR/$relative"
done < <(find "$PAYLOAD_DIR/datawork" -type f -print0)
for relative in "${ROOT_FILES[@]}"; do
  [[ -f "$PAYLOAD_DIR/$relative" ]] || continue
  mode=0644; [[ "$relative" == *.sh ]] && mode=0755
  install -m "$mode" "$PAYLOAD_DIR/$relative" "$APP_DIR/$relative"
done
while IFS= read -r relative; do
  [[ "$relative" == datawork/* && "$relative" != *'..'* ]] || fail "删除清单包含非法路径：$relative"
  rm -f -- "$APP_DIR/$relative"
done < "$PATCH_DIR/DELETE_PATHS.txt"
find "$APP_DIR/datawork" -type d -name __pycache__ -prune -exec rm -rf -- {} +
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${ROOT_FILES[@]}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done

log "使用现有虚拟环境执行离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data" "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
from datawork.application.analysis_service import AnalysisService
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan

frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "z": ["A", "A", "B"]})
plan = AnalysisPlan(
    interface_mode="professional", method="one_sample_ttest",
    dependent_variables=["custom"], split_by=["z"],
    derived_columns=[{"name": "custom", "formula": "[x] / 3", "source_columns": ["x"]}],
)
prepared, logs, warnings = AnalysisService.prepare_frame(frame, plan)
assert prepared["custom"].tolist() == [0.33333333, 0.66666667, 1.0]
assert logs[0]["decimal_places"] == 8 and not warnings
assert len(list_methods(runnable_only=True)) == 47
print("offline_smoke=passed")
PY
)

if ! restart_service; then
  log "文件和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，然后执行：curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待服务恢复……"
for _ in $(seq 1 30); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1     && curl -fsS "$OPENAPI_URL" | grep -q 'derived-preview'; then
    log "更新成功：服务健康，且自定义列预览接口已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过健康检查。请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
