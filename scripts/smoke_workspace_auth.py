#!/usr/bin/env python3
"""浏览器验证所有者工作区登录、服务端拦截和共享持久目录。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18902/datework/")
    parser.add_argument("--password", required=True)
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
        pass
    page.locator("main.shell").wait_for(state="visible", timeout=10000)
    page.locator(".session-status-card").wait_for(state="visible", timeout=10000)


def login(page, password: str) -> None:
    page.get_by_role("button", name="🔒 项目工作区").click()
    page.locator(".workspace-auth-card").wait_for(state="visible")
    page.get_by_label("工作区密码").fill(password)
    page.get_by_role("button", name="验证并进入").click()
    page.locator(".workspace-layout").wait_for(state="visible", timeout=15000)


def main() -> int:
    args = parse_args()
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        first_context = browser.new_context(viewport={"width": 1360, "height": 900}, service_workers="block")
        second_context = browser.new_context(viewport={"width": 1360, "height": 900}, service_workers="block")
        first = first_context.new_page()
        second = second_context.new_page()
        for index, page in enumerate((first, second), start=1):
            page.on(
                "console",
                lambda message, index=index: console_errors.append(
                    f"page{index}:{message.type}:{message.text}"
                ) if message.type == "error" else None,
            )

        navigate(first, args.base_url)
        unauthorized = first.evaluate(API_CALL, {"path": "projects"})
        assert unauthorized["status"] == 401
        assert unauthorized["payload"]["error"]["code"] == "workspace_auth_required"

        first.get_by_role("button", name="🔒 项目工作区").click()
        modal = first.locator(".workspace-auth-card")
        modal.wait_for(state="visible")
        assert "所有者工作区认证" in modal.inner_text()
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            first.screenshot(path=str(args.screenshot.resolve()), full_page=True)

        first.get_by_label("工作区密码").fill("definitely-wrong")
        first.get_by_role("button", name="验证并进入").click()
        first.locator(".workspace-auth-error").wait_for(state="visible")
        assert "密码不正确" in first.locator(".workspace-auth-error").inner_text()

        first.get_by_label("工作区密码").fill(args.password)
        first.get_by_role("button", name="验证并进入").click()
        first.locator(".workspace-layout").wait_for(state="visible", timeout=15000)
        assert "所有者持久存储" in first.locator(".workspace-storage-card").inner_text()
        created = first.evaluate(
            API_CALL,
            {"path": "projects", "method": "POST", "body": {"name": "浏览器认证项目", "description": "owner"}},
        )
        assert created["status"] == 201

        navigate(second, args.base_url)
        second_unauthorized = second.evaluate(API_CALL, {"path": "projects"})
        assert second_unauthorized["status"] == 401
        login(second, args.password)
        second.get_by_role("button", name="浏览器认证项目").wait_for(state="visible")
        assert "所有者工作区已解锁" in second.locator(".session-status-card").inner_text()

        first_context.close()
        second_context.close()
        browser.close()

    print(json.dumps({
        "unauthorized_api_blocked": True,
        "wrong_password_rejected": True,
        "owner_login_succeeded": True,
        "owner_workspace_shared_across_browsers": True,
        "console_errors": console_errors,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
