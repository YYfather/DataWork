#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_ID="datawork_v1.5.0_to_v1.7.0_core_audit_manova_combinations"
TARGET_VERSION="1.7.0"
DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
SERVICE_NAME="${DATAWORK_SUPERVISOR_NAME:-}"
PATCH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PAYLOAD_DIR="$PATCH_DIR/payload"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_DIR="$BACKUP_ROOT/${PATCH_ID}_$(date +%Y%m%d_%H%M%S)"
BACKUP_MARKER="$APP_DIR/updates/.last_v17_core_manova_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
ROOT_FILES=(
  "README.md"
  "VERSION"
  "pyproject.toml"
)
ACCEPTED_VERSIONS=(1.5.0)

log() { printf '[DataWork 1.5.0→1.7.0 热补丁] %s\n' "$*"; }
fail() { printf '[DataWork 1.5.0→1.7.0 热补丁] 错误：%s\n' "$*" >&2; exit 1; }
normalized_sha() { tr -d '\r' < "$1" | sha256sum | awk '{print $1}'; }

manifest_matches() {
  local manifest="$1" expected="" relative="" actual=""
  while read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$APP_DIR/$relative" ]] || return 1
    actual="$(normalized_sha "$APP_DIR/$relative")"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest"
}

known_delete_paths_absent() {
  local relative=""
  while IFS= read -r relative; do
    [[ -n "$relative" ]] || continue
    [[ ! -e "$APP_DIR/$relative" ]] || return 1
  done < "$PATCH_DIR/DELETE_PATHS.txt"
}

match_known_baseline() {
  local manifest=""
  for manifest in "$PATCH_DIR"/BASELINES/*.sha256; do
    [[ -f "$manifest" ]] || continue
    if manifest_matches "$manifest"; then
      basename "$manifest" .sha256
      return 0
    fi
  done
  return 1
}


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
[[ -d "$APP_DIR/datawork" && -f "$APP_DIR/VERSION" ]]   || fail "目标不是完整 DataWork 服务：$APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]]   || fail "未找到现有虚拟环境 Python：$APP_DIR/.venv/bin/python"
[[ -d "$APP_DIR/data" ]] || fail "缺少运行数据目录：$APP_DIR/data"
[[ -d "$PAYLOAD_DIR/datawork/web/static/assets" ]]   || fail "补丁 payload 不完整。"

log "校验热补丁自身 SHA-256……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt)

CURRENT_VERSION="$(tr -d '[:space:]' < "$APP_DIR/VERSION")"
if manifest_matches "$PATCH_DIR/TARGET_SHA256.txt"   && known_delete_paths_absent   && [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
  log "服务器已经是本热补丁目标版本，无需重复安装。"
  exit 0
fi

VERSION_ALLOWED=0
for candidate in "${ACCEPTED_VERSIONS[@]}"; do
  [[ "$CURRENT_VERSION" == "$candidate" ]] && VERSION_ALLOWED=1
done
[[ "$VERSION_ALLOWED" -eq 1 ]]   || fail "服务器版本 $CURRENT_VERSION 不在本补丁支持范围（仅 1.5.0）。"

BASELINE_NAME="$(match_known_baseline || true)"
if [[ -z "$BASELINE_NAME" ]]; then
  if [[ "${DATAWORK_ALLOW_BASELINE_MISMATCH:-0}" != "1" ]]; then
    fail "服务器程序文件与 1.5.0 网站部署基线不一致。安装已停止，未覆盖任何文件。"
  fi
  BASELINE_NAME="explicitly-authorized-unknown"
  log "警告：已按显式授权跳过基线哈希保护。"
else
  log "识别服务器基线：$BASELINE_NAME"
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
    printf '%s\n' "$relative" >> "$BACKUP_DIR/root_files_present.txt"
  fi
done
printf '%s\n' "$CURRENT_VERSION" > "$BACKUP_DIR/original_version.txt"
printf '%s\n' "$BASELINE_NAME" > "$BACKUP_DIR/recognized_baseline.txt"
printf '%s\n' "$BACKUP_DIR" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"

log "覆盖 V1.7 运行源码；保留 .venv、data、updates、数据库和用户配置……"
while IFS= read -r -d '' source; do
  relative="${source#$PAYLOAD_DIR/}"
  install -D -m 0644 "$source" "$APP_DIR/$relative"
done < <(find "$PAYLOAD_DIR/datawork" -type f -print0)
for relative in "${ROOT_FILES[@]}"; do
  [[ -f "$PAYLOAD_DIR/$relative" ]] || continue
  install -m 0644 "$PAYLOAD_DIR/$relative" "$APP_DIR/$relative"
done
while IFS= read -r relative; do
  [[ -n "$relative" ]] || continue
  [[ "$relative" == datawork/* && "$relative" != *'..'* ]]     || fail "删除清单包含非法路径：$relative"
  rm -f -- "$APP_DIR/$relative"
done < "$PATCH_DIR/DELETE_PATHS.txt"
find "$APP_DIR/datawork" -type d -name __pycache__ -prune -exec rm -rf -- {} +
chown -R "$APP_OWNER:$APP_GROUP" "$APP_DIR/datawork"
for relative in "${ROOT_FILES[@]}"; do
  [[ -e "$APP_DIR/$relative" ]] && chown "$APP_OWNER:$APP_GROUP" "$APP_DIR/$relative"
done

manifest_matches "$PATCH_DIR/TARGET_SHA256.txt"   || fail "覆盖后目标文件哈希不一致；请立即运行 ./回滚本次热补丁.sh。"
known_delete_paths_absent   || fail "旧运行文件未清理干净；请立即运行 ./回滚本次热补丁.sh。"

log "使用现有虚拟环境执行 V1.7 离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data"     "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
import datawork
from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import MethodStatus, list_methods
from datawork.core.plan import AnalysisPlan

assert datawork.__version__ == "1.7.0"
methods = [item for item in list_methods() if item.visible and item.is_runnable]
assert len(methods) == 47
assert all(item.status is MethodStatus.IMPLEMENTED for item in methods)

frame = pd.DataFrame({
    "group": ["A"] * 8 + ["B"] * 8,
    "y1": [1.0, 1.4, 1.8, 2.1, 2.5, 2.9, 3.2, 3.7, 4.2, 4.7, 5.1, 5.6, 6.0, 6.5, 7.0, 7.4],
    "y2": [3.2, 2.8, 3.6, 3.1, 4.0, 3.7, 4.4, 4.1, 5.0, 5.8, 5.3, 6.2, 5.9, 6.8, 6.4, 7.3],
    "y3": [5.1, 5.7, 4.8, 6.2, 5.5, 6.5, 5.9, 6.8, 7.1, 6.6, 7.8, 7.3, 8.4, 7.9, 8.8, 8.2],
    "y4": [2.4, 2.0, 2.9, 3.3, 2.7, 3.8, 3.1, 4.2, 4.8, 5.4, 4.9, 6.0, 5.6, 6.7, 6.1, 7.2],
})
plan = AnalysisPlan(
    interface_mode="professional",
    method="oneway_manova",
    dependent_variables=["y1", "y2", "y3", "y4"],
    fixed_factors=["group"],
    dependent_task_mode="combinations",
    dependent_combination_min_size=2,
    dependent_combination_max_size=2,
    cross_model_p_adjust="holm",
)
report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
assert report.ready
assert report.batch_summary["dependent_combination_count"] == 6
assert report.batch_summary["expanded_task_count"] == 6
result = AnalysisService().run(frame, plan)
assert len(result.results) == 6
assert all(item.result is not None and not item.error for item in result.results)
print("offline_v17_smoke=passed")
PY
)

if ! restart_service; then
  log "文件、哈希和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，再执行："
  log "curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待 V1.7 服务恢复……"
for _ in $(seq 1 30); do
  if health_json="$(curl -fsS "$HEALTH_URL" 2>/dev/null)"     && printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c       'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.7.0"; f=p["features"]; assert f["pairing_workflow"] is True; assert f["pairing_abs"] is True; assert f["dependent_variable_groups"] is True; assert f["dependent_variable_combinations"] is True'     && curl -fsS "$OPENAPI_URL" | grep -q '/api/preflight'; then
    log "更新成功：版本、V1.7 组合能力和预检接口均已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过 V1.7 健康检查；请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
