#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_ID="datawork_v1.5_pairing_workflow_20260723"
TARGET_VERSION="1.5.0"
DEFAULT_APP_DIR="/www/wwwroot/1490473838.cn/datework"
APP_DIR="${DATAWORK_APP_DIR:-$DEFAULT_APP_DIR}"
SERVICE_NAME="${DATAWORK_SUPERVISOR_NAME:-}"
PATCH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PAYLOAD_DIR="$PATCH_DIR/payload"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_DIR="$BACKUP_ROOT/${PATCH_ID}_$(date +%Y%m%d_%H%M%S)"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_pairing_hotfix_backup"
HEALTH_URL="http://127.0.0.1:8765/api/health"
OPENAPI_URL="http://127.0.0.1:8765/openapi.json"
ROOT_FILES=(
  "README.md"
  "VERSION"
  "pyproject.toml"
)
ACCEPTED_VERSIONS=(0.4.9 1.0.0)

log() { printf '[DataWork V1.5 热补丁] %s\n' "$*"; }
fail() { printf '[DataWork V1.5 热补丁] 错误：%s\n' "$*" >&2; exit 1; }
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
[[ "$VERSION_ALLOWED" -eq 1 ]]   || fail "服务器版本 $CURRENT_VERSION 不在本补丁支持范围（0.4.9 / 1.0.0）。"

BASELINE_NAME="$(match_known_baseline || true)"
if [[ -z "$BASELINE_NAME" ]]; then
  if [[ "${DATAWORK_ALLOW_BASELINE_MISMATCH:-0}" != "1" ]]; then
    fail "服务器程序文件与三套已审核基线均不一致。安装已停止，未覆盖任何文件。"
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

log "覆盖 V1.5 运行源码；保留 .venv、data、updates、数据库和用户配置……"
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

log "使用现有虚拟环境执行 V1.5 离线功能烟雾测试……"
(
  cd "$APP_DIR"
  PYTHONDONTWRITEBYTECODE=1 DATAWORK_HOME="$APP_DIR/data"     "$APP_DIR/.venv/bin/python" - <<'PY'
import pandas as pd
import datawork
from datawork.application.analysis_service import AnalysisService
from datawork.application.preflight_service import PreflightService
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan

assert datawork.__version__ == "1.5.0"
frame = pd.DataFrame([
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 20.0},
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 10.0},
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 22.0},
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 11.0},
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "T1", "value": 24.0},
    {"year": 2025, "variety": "V1", "mode": "M1", "spray": "CK1", "value": 12.0},
])
plan = AnalysisPlan.model_validate({
    "interface_mode": "professional",
    "method": "one_sample_ttest",
    "dependent_variables": ["NDR"],
    "pairing": {
        "group_column": "spray",
        "mappings": [{"treatment": "T1", "control": "CK1"}],
        "match_columns": ["year", "variety", "mode"],
        "pair_id_column": None,
        "derived_columns": [
            {
                "id": "ndr",
                "name": "NDR",
                "source_column": "value",
                "formula": "[对照值]",
                "unit": "百分点",
                "decimal_places": 8,
            }
        ],
    },
})
prepared, logs, warnings = AnalysisService.prepare_frame(frame, plan)
assert prepared["NDR"].tolist() == [10.0, 11.0, 12.0]
assert not warnings
audit = next(item for item in logs if item["operation"] == "pairing")
assert audit["successful_pairs"] == 3
report = PreflightService().inspect(frame, plan.model_dump(mode="json"))
assert report.ready
assert report.pairing_summary["successful_pairs"] == 3
AnalysisService().execute(frame, plan)
assert len(list_methods(runnable_only=True)) == 47
print("offline_v15_smoke=passed")
PY
)

if ! restart_service; then
  log "文件、哈希和离线测试均已完成，但未识别到进程守护名称。"
  log "请在宝塔进程守护管理器中手动重启 DataWork，再执行："
  log "curl -fsS $HEALTH_URL"
  exit 2
fi

log "等待 V1.5 服务恢复……"
for _ in $(seq 1 30); do
  if health_json="$(curl -fsS "$HEALTH_URL" 2>/dev/null)"     && printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c       'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.5.0"; assert p["features"]["pairing_workflow"] is True; assert p["features"]["dependent_variable_groups"] is True'     && curl -fsS "$OPENAPI_URL" | grep -q '/api/preflight'; then
    log "更新成功：服务版本、V1.5 能力和预检接口均已加载。"
    log "备份位置：$BACKUP_DIR"
    exit 0
  fi
  sleep 1
done
fail "服务未在 30 秒内通过 V1.5 健康检查；请查看进程日志，必要时运行 ./回滚本次热补丁.sh。"
