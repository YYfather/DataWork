#!/usr/bin/env bash
set -Eeuo pipefail

umask 022
PATCH_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${DATAWORK_APP_DIR:-/www/wwwroot/1490473838.cn/datework}"
STATIC_DIR="$APP_DIR/datawork/web/static"
PAYLOAD_DIR="$PATCH_DIR/payload/datawork/web/static"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_notice_hotfix_backup"
HEALTH_URL="${DATAWORK_HEALTH_URL:-http://127.0.0.1:8765/api/health}"
PAGE_URL="${DATAWORK_PAGE_URL:-http://127.0.0.1:8765/}"
OLD_ASSETS=(
  "assets/index-BpjhpLDa.css"
  "assets/index-DR4Uk53p.js"
)

log() { printf '[DataWork V1.5 公告热补丁] %s\n' "$*"; }
fail() { printf '[DataWork V1.5 公告热补丁] 错误：%s\n' "$*" >&2; exit 1; }

manifest_matches() {
  local root="$1" manifest_file="$2" expected="" relative="" actual=""
  while read -r expected relative; do
    [[ -n "$expected" && -n "$relative" ]] || continue
    [[ -f "$root/$relative" ]] || return 1
    actual="$(sha256sum "$root/$relative" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || return 1
  done < "$manifest_file"
}

[[ "$(id -u)" -eq 0 || "${DATAWORK_ALLOW_NON_ROOT_TEST:-0}" == "1" ]]   || fail "请使用 root 用户运行。"
[[ -d "$APP_DIR" && -d "$STATIC_DIR" ]] || fail "未找到 DataWork：$APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]] || fail "未找到服务器现有 Python 虚拟环境。"
[[ -f "$APP_DIR/VERSION" ]] || fail "缺少 VERSION 文件。"
[[ "$(tr -d '[:space:]' < "$APP_DIR/VERSION")" == "1.5.0" ]]   || fail "本补丁只适用于已运行 V1.5.0 的服务器。"

log "校验补丁包完整性……"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS.txt >/dev/null)   || fail "补丁包 SHA-256 校验失败。"

if manifest_matches "$STATIC_DIR" "$PATCH_DIR/TARGET_SHA256.txt"; then
  log "公告版前端已经安装，无需重复执行。"
  exit 0
fi

manifest_matches "$STATIC_DIR" "$PATCH_DIR/BASELINE_SHA256.txt"   || fail "当前网页静态文件不是已审核的 V1.5 基线；未覆盖任何文件。"

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="$BACKUP_ROOT/datawork_v1.5_pairing_test_notice_20260723_$timestamp"
mkdir -p "$backup_dir"
cp -a "$STATIC_DIR" "$backup_dir/static"
printf '%s\n' "$backup_dir" > "$BACKUP_MARKER"
chmod 0600 "$BACKUP_MARKER"
log "已备份当前网页资源到：$backup_dir"

owner="$(stat -c '%U' "$APP_DIR")"
group="$(stat -c '%G' "$APP_DIR")"
while IFS= read -r -d '' source; do
  relative="${source#$PAYLOAD_DIR/}"
  install -D -m 0644 "$source" "$STATIC_DIR/$relative"
done < <(find "$PAYLOAD_DIR" -type f -print0)

for relative in "${OLD_ASSETS[@]}"; do
  rm -f -- "$STATIC_DIR/$relative"
done
find "$STATIC_DIR" -type d -empty -delete
chown -R "$owner:$group" "$STATIC_DIR"

manifest_matches "$STATIC_DIR" "$PATCH_DIR/TARGET_SHA256.txt"   || fail "覆盖后的网页文件哈希不一致；请运行 ./回滚公告热补丁.sh。"
for relative in "${OLD_ASSETS[@]}"; do
  [[ ! -e "$STATIC_DIR/$relative" ]]     || fail "旧前端资源仍存在；请运行 ./回滚公告热补丁.sh。"
done

health_json="$(curl -fsS "$HEALTH_URL")"   || fail "V1.5 健康接口不可访问；网页文件已更新，可运行回滚脚本恢复。"
printf '%s' "$health_json" | "$APP_DIR/.venv/bin/python" -c   'import json,sys; p=json.load(sys.stdin); assert p["status"]=="ok"; assert p["version"]=="1.5.0"; assert p["features"]["pairing_workflow"] is True; assert p["features"]["dependent_variable_groups"] is True'   || fail "后端未处于完整 V1.5 状态；请运行 ./回滚公告热补丁.sh。"
page_html="$(curl -fsS "$PAGE_URL")"   || fail "服务器网页入口不可访问；请运行 ./回滚公告热补丁.sh。"
grep -q 'index-Cnt-pWU9.js' <<< "$page_html"   || fail "服务器尚未返回公告版网页入口；请运行 ./回滚公告热补丁.sh。"

log "更新成功：V1.5 配对功能测试公告与 V1.5 版本显示已上线。"
log "无需重启 Python；请在浏览器按 Ctrl+F5 强制刷新。"
log "备份位置：$backup_dir"
