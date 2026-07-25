"""DataWork 宝塔服务器启动入口：仅监听本机，由反向代理提供外部访问。"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.getenv("DATAWORK_PORT", "8765"))


def main() -> None:
    os.environ.setdefault("DATAWORK_HOME", str(ROOT / "data"))
    os.environ["DATAWORK_BIND_HOST"] = HOST
    uvicorn.run(
        "datawork.web.app:app",
        host=HOST,
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
