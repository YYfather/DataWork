#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${DATAWORK_APP_DIR:-/www/wwwroot/1490473838.cn/datework}"
STATIC_DIR="$APP_DIR/datawork/web/static"
BACKUP_ROOT="$APP_DIR/updates/backups"
BACKUP_MARKER="$APP_DIR/updates/.last_v15_notice_hotfix_backup"

log() { printf '[DataWork V1.5 公告热补丁回滚] %s\n' "$*"; }
fail() { printf '[DataWork V1.5 公告热补丁回滚] 错误：%s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 || "${DATAWORK_ALLOW_NON_ROOT_TEST:-0}" == "1" ]]   || fail "请使用 root 用户运行。"
[[ -f "$BACKUP_MARKER" ]] || fail "没有找到本公告热补丁的备份标记。"
backup_dir="$(tr -d '\r\n' < "$BACKUP_MARKER")"
case "$backup_dir" in
  "$BACKUP_ROOT"/datawork_v1.5_pairing_test_notice_20260723_*) ;;
  *) fail "备份路径不在预期目录内，已停止。" ;;
esac
[[ -d "$backup_dir/static" ]] || fail "备份网页目录不存在：$backup_dir/static"

owner="$(stat -c '%U' "$APP_DIR")"
group="$(stat -c '%G' "$APP_DIR")"
replaced="$backup_dir/replaced_static_$(date +%Y%m%d_%H%M%S)"
mv "$STATIC_DIR" "$replaced"
cp -a "$backup_dir/static" "$STATIC_DIR"
chown -R "$owner:$group" "$STATIC_DIR"
rm -f -- "$BACKUP_MARKER"

log "已恢复公告热补丁安装前的网页资源。"
log "被替换的公告版资源保留在：$replaced"
log "请在浏览器按 Ctrl+F5 强制刷新。"
