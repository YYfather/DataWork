#!/usr/bin/env bash
# 安全修改 DataWork 工作区密码：密码不会出现在命令历史中。

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

APP_DIR="/www/wwwroot/1490473838.cn/datework"
CONFIG="$APP_DIR/data/workspace_auth.json"

[[ "${EUID}" -eq 0 ]] || { printf '错误：请以 root 身份执行。\n' >&2; exit 1; }
[[ -x "$APP_DIR/.venv/bin/python" ]] || { printf '错误：未找到 DataWork Python 环境。\n' >&2; exit 1; }

read -r -s -p '请输入新的工作区密码：' PASSWORD
printf '\n'
read -r -s -p '请再次输入：' CONFIRM
printf '\n'
[[ -n "$PASSWORD" ]] || { printf '错误：密码不能为空。\n' >&2; exit 1; }
[[ "$PASSWORD" == "$CONFIRM" ]] || { printf '错误：两次密码不一致。\n' >&2; exit 1; }

DATA_OWNER="$(stat -c '%U' "$APP_DIR/data")"
DATA_GROUP="$(stat -c '%G' "$APP_DIR/data")"
printf '%s' "$PASSWORD" | "$APP_DIR/.venv/bin/python" -c '
import base64, hashlib, json, os, secrets, sys
from pathlib import Path
target = Path(sys.argv[1])
password = sys.stdin.buffer.read()
salt = secrets.token_bytes(24)
payload = {
    "algorithm": "pbkdf2_sha256",
    "iterations": 600000,
    "salt": base64.b64encode(salt).decode("ascii"),
    "digest": base64.b64encode(hashlib.pbkdf2_hmac("sha256", password, salt, 600000)).decode("ascii"),
    "cleanup_expired_sessions": True,
}
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, target)
' "$CONFIG"
unset PASSWORD CONFIRM
chown "$DATA_OWNER:$DATA_GROUP" "$CONFIG"
chmod 600 "$CONFIG"

printf '工作区密码摘要已更新。请在宝塔 Supervisor 中重启 datawork 后生效。\n'
