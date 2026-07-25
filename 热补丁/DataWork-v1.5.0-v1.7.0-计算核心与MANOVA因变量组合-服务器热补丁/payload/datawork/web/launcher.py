"""跨平台本地网页启动器。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 DataWork 本地网页应用")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址；局域网部署可使用 0.0.0.0")
    parser.add_argument("--port", default=8765, type=int, help="监听端口")
    parser.add_argument("--no-browser", action="store_true", help="不要自动打开浏览器")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    parser.add_argument("--workspace", help="自定义工作区目录；等价于 DATAWORK_HOME")
    parser.add_argument(
        "--allow-remote-ai", action="store_true",
        help="允许局域网/远程客户端调用 AI；仅应在已有认证与访问控制时启用",
    )
    args = parser.parse_args()
    if args.workspace:
        os.environ["DATAWORK_HOME"] = str(Path(args.workspace).expanduser().resolve())
    os.environ["DATAWORK_BIND_HOST"] = args.host
    if args.allow_remote_ai:
        os.environ["DATAWORK_ALLOW_REMOTE_AI"] = "1"

    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{browser_host}:{args.port}"
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        "datawork.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
