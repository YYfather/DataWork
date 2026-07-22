#!/usr/bin/env python3
"""用真实浏览器验证多标签页在线检测与关闭释放。"""

from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18903/"


def status(session_id: str) -> dict[str, object]:
    request = Request(
        BASE_URL.rstrip("/") + "/api/session/status",
        headers={"X-DataWork-Session": session_id},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    clients: list[str] = []

    def capture_client(request) -> None:
        if request.url.endswith("/api/session"):
            client_id = request.headers.get("x-datawork-client")
            if client_id:
                clients.append(client_id)

    first = context.new_page()
    first.on("request", capture_client)
    first.goto(BASE_URL)
    first.wait_for_load_state("networkidle")
    session_id = first.evaluate("localStorage.getItem('datawork.session.v1')")
    assert session_id

    second = context.new_page()
    second.on("request", capture_client)
    second.goto(BASE_URL)
    second.wait_for_load_state("networkidle")
    assert len(set(clients)) == 2, clients
    assert status(session_id)["connected_pages"] == 2

    first.close()
    time.sleep(1)
    after_first = status(session_id)
    assert after_first["active"] is True
    assert after_first["connected_pages"] == 1

    second.close()
    time.sleep(1)
    after_last = status(session_id)
    assert after_last["active"] is False
    assert after_last["active_users"] == 0
    browser.close()

print("浏览器在线检测验证通过：双标签只占一席，逐页关闭正确，最后一页立即释放。")
