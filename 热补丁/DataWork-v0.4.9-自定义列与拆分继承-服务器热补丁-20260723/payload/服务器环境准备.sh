#!/usr/bin/env bash
# DataWork 宝塔环境准备脚本（1490473838.cn/datework）
# 用法：上传 DataWork服务 后，以 root 执行：
#   cd /www/wwwroot/1490473838.cn/datework
#   chmod 750 服务器环境准备.sh
#   ./服务器环境准备.sh
# 指定解释器示例：PYTHON_BIN=/usr/bin/python3.11 ./服务器环境准备.sh

set -Eeuo pipefail
IFS=$'\n\t'
umask 027

SITE_ROOT="/www/wwwroot/1490473838.cn"
APP_DIR="$SITE_ROOT/datework"
SERVICE_USER="${DATAWORK_SERVICE_USER:-www}"
PYTHON_BIN="${PYTHON_BIN:-}"

say() {
    printf '[DataWork] %s\n' "$*"
}

fail() {
    printf '[DataWork] 错误：%s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "请以 root 身份执行；宝塔终端通常默认可使用 root。"
fi

[[ -f "$APP_DIR/bt_start.py" ]] || fail "未找到 $APP_DIR/bt_start.py；请先将“DataWork服务”完整上传到 datework 目录。"
[[ -f "$APP_DIR/requirements.txt" ]] || fail "未找到 $APP_DIR/requirements.txt；上传内容不完整。"

if [[ -z "$PYTHON_BIN" ]]; then
    for candidate in python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    done
fi

[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || fail "未找到 Python 3.11/3.12。请先安装，再执行：PYTHON_BIN=/实际/python3.11路径 ./服务器环境准备.sh"

version="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$version" in
    3.11|3.12) ;;
    *) fail "当前 Python 为 $version；请使用 Python 3.11 或 3.12。" ;;
esac

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    fail "未找到运行用户 $SERVICE_USER。若宝塔使用其他网站运行用户，请设置 DATAWORK_SERVICE_USER，例如：DATAWORK_SERVICE_USER=www ./服务器环境准备.sh"
fi

PYTHON_TARGET="$(readlink -f "$PYTHON_BIN")"
if [[ "$PYTHON_TARGET" == /root/* ]]; then
    command -v setfacl >/dev/null 2>&1 || fail "Python 位于 /root，缺少 ACL 工具。请先安装 acl 软件包后重试。"
    say "Python 位于 root 的 uv 运行时；仅授权 $SERVICE_USER 穿越 /root"
    setfacl -m "u:$SERVICE_USER:--x" /root
fi

say "使用 Python $version：$PYTHON_BIN"
say "创建或复用虚拟环境：$APP_DIR/.venv"
"$PYTHON_BIN" -m venv "$APP_DIR/.venv"

say "安装 Python 依赖（需要服务器可访问 PyPI 或已配置镜像）"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

say "允许 $SERVICE_USER 读取和执行虚拟环境"
chgrp -R "$SERVICE_USER" "$APP_DIR/.venv"
chmod -R g+rX "$APP_DIR/.venv"

say "创建数据目录并授权给 $SERVICE_USER"
install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"

if [[ -f "$APP_DIR/workspace_auth.json" && ! -f "$APP_DIR/data/workspace_auth.json" ]]; then
    install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 600 \
        "$APP_DIR/workspace_auth.json" "$APP_DIR/data/workspace_auth.json"
    say "已安装所有者工作区密码摘要"
fi

say "验证应用依赖"
cd "$APP_DIR"
runuser -u "$SERVICE_USER" -- env \
    DATAWORK_HOME="$APP_DIR/data" \
    DATAWORK_BIND_HOST="127.0.0.1" \
    "$APP_DIR/.venv/bin/python" -c \
    "from datawork.web.app import create_app; app=create_app(); print('DataWork', app.version, '环境与工作区认证已就绪')"

cat <<EOF

[DataWork] 环境准备完成。接下来请在宝塔继续：
1. Supervisor 添加 datawork：
   运行目录：$APP_DIR
   启动命令：$APP_DIR/.venv/bin/python $APP_DIR/bt_start.py
   启动用户：$SERVICE_USER
2. 将包内“宝塔-Nginx-datework.conf”的三个 location 放入 1490473838.cn 的 HTTPS server 块。
3. 创建 /www/server/pass/datawork.htpasswd，执行 nginx -t 后重载 Nginx。

本脚本没有启动服务、没有修改 Nginx，也没有开放 8765 端口。
EOF
