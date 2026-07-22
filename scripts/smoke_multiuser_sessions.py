#!/usr/bin/env python3
"""用四个独立 Chromium 上下文验证三席位、隔离和超时释放。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18901/datework/")
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


API_CALL = """async ({path, method = 'GET', body = null}) => {
  const sessionId = localStorage.getItem('datawork.session.v1');
  const headers = {'X-DataWork-Session': sessionId};
  if (body !== null) headers['Content-Type'] = 'application/json';
  const response = await fetch(`./api/${path}`, {
    method, headers, body: body === null ? undefined : JSON.stringify(body)
  });
  let payload = null;
  try { payload = await response.json(); } catch {}
  return {status: response.status, payload};
}"""


def navigate(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        # AI/席位状态请求可能跨过 networkidle 窗口；关键 DOM 仍需独立通过验证。
        pass
    page.locator("main.shell").wait_for(state="visible", timeout=10000)


def main() -> int:
    args = parse_args()
    base_url = args.base_url
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        contexts = [
            browser.new_context(viewport={"width": 1360, "height": 900}, service_workers="block")
            for _ in range(4)
        ]
        pages = [context.new_page() for context in contexts]
        for index, page in enumerate(pages):
            page.on(
                "console",
                lambda message, index=index: console_errors.append(
                    f"page{index + 1}:{message.type}:{message.text}"
                ) if message.type == "error" else None,
            )

        for page in pages[:3]:
            navigate(page, base_url)
            page.locator(".session-status-card").wait_for(state="visible")

        pages[2].reload(wait_until="domcontentloaded")
        pages[2].locator(".session-status-card").wait_for(state="visible")
        assert "3/3" in pages[2].locator(".session-status-card").inner_text()

        navigate(pages[3], base_url)
        pages[3].locator(".session-gate-card").wait_for(state="visible")
        assert "当前使用人数已满" in pages[3].locator(".session-gate-card").inner_text()
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pages[3].screenshot(path=str(args.screenshot.resolve()), full_page=True)

        pages[3].wait_for_timeout(4000)
        for page in pages[1:3]:
            response = page.evaluate(API_CALL, {"path": "projects"})
            assert response["status"] == 200
        pages[3].wait_for_timeout(4500)

        kicked = pages[0].evaluate(API_CALL, {"path": "projects"})
        assert kicked["status"] == 440
        assert kicked["payload"]["error"]["code"] == "session_expired"

        with pages[3].expect_navigation(wait_until="domcontentloaded"):
            pages[3].get_by_role("button", name="重新加入").click()
        pages[3].locator(".session-status-card").wait_for(state="visible")
        assert "3/3" in pages[3].locator(".session-status-card").inner_text()

        created = pages[1].evaluate(
            API_CALL,
            {"path": "projects", "method": "POST", "body": {"name": "浏览器二", "description": "隔离验证"}},
        )
        assert created["status"] == 201
        isolated = pages[2].evaluate(API_CALL, {"path": "projects"})
        assert isolated == {"status": 200, "payload": []}

        labels = [
            page.locator(".session-status-card strong").inner_text()
            for page in pages[1:]
        ]
        for context in contexts:
            context.close()
        browser.close()

    print(json.dumps({
        "capacity": 3,
        "fourth_user_rejected": True,
        "idle_session_status": 440,
        "replacement_admitted": True,
        "workspace_isolated": True,
        "active_labels": labels,
        "console_errors": console_errors,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
