#!/usr/bin/env python3
"""Headless browser audit for DataWork's instant-analysis and workspace flows.

The script embeds the production Vue bundle, routes API calls to FastAPI's
TestClient, and checks loading overlays, preflight guidance, stale-result
invalidation, AI floating-window drag, resize and close behavior, structured errors, workspace saving,
run/report flows, accessible button labels, and JavaScript page errors.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from datawork.web.app import create_app  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover - release environments may omit browser tooling
    print(f"Playwright is not installed: {exc}")
    raise SystemExit(2)


def production_html() -> str:
    static = ROOT / "datawork/web/static"
    css_file = next((static / "assets").glob("*.css"), None)
    js_file = next((static / "assets").glob("*.js"), None)
    if css_file is None or js_file is None:
        raise RuntimeError("Production frontend assets are missing. Run scripts/build_frontend.py first.")
    css = css_file.read_text(encoding="utf-8")
    js = js_file.read_text(encoding="utf-8").replace("</script", "<\\/script")
    return (
        '<!doctype html><html><head><base href="http://datawork.test/">'
        '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{css}</style></head><body><div id=\"app\"></div>"
        f'<script type="module">{js}</script></body></html>'
    )


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="datawork-ui-audit-"))
    client = TestClient(create_app(workspace_root=workspace))
    csv_bytes = b"group,value,batch,\nA,1,B1,\nA,2,B2,\nA,3,B1,\nB,4,B2,\nB,5,B1,\nB,6,B2,\n"
    profile = client.post("/api/profile", files={"file": ("sample.csv", csv_bytes, "text/csv")}).json()
    ready_plan = {"method": "welch_ttest", "dependent_variables": ["value"], "fixed_factors": ["group"]}
    blocked_plan = {"method": "twoway_anova", "dependent_variables": ["value"], "fixed_factors": ["group"]}
    ready_preflight = client.post(
        "/api/preflight", files={"file": ("sample.csv", csv_bytes, "text/csv")},
        data={"plan_json": json.dumps(ready_plan)},
    ).json()
    blocked_preflight = client.post(
        "/api/preflight", files={"file": ("sample.csv", csv_bytes, "text/csv")},
        data={"plan_json": json.dumps(blocked_plan)},
    ).json()
    analyzed = client.post(
        "/api/analyze", files={"file": ("sample.csv", csv_bytes, "text/csv")},
        data={"plan_json": json.dumps(ready_plan)},
    ).json()
    if not ready_preflight.get("ready") or blocked_preflight.get("ready"):
        raise RuntimeError("Preflight fixtures are not in the expected states")

    project = client.post("/api/projects", json={"name": "E2E 项目", "description": "交互审查"}).json()
    client.post(
        f"/api/projects/{project['id']}/datasets",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
        data={"name": "E2E 数据"},
    ).raise_for_status()

    state = {"preflight_count": 0, "profile_error": False}
    api_errors: list[str] = []
    html = production_html()
    csv_path = workspace / "sample.csv"
    csv_path.write_bytes(csv_bytes)
    page_errors: list[str] = []

    def fulfill_json(route, payload, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

    def proxy(route) -> None:
        request = route.request
        parsed = urlsplit(request.url)
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        if parsed.path == "/api/profile":
            time.sleep(0.12)
            if state["profile_error"]:
                fulfill_json(
                    route,
                    {"detail": "测试数据格式错误", "error": {"code": "file_format_error", "message": "测试数据格式错误"}},
                    422,
                )
            else:
                fulfill_json(route, profile)
            return
        if parsed.path == "/api/preflight":
            # 保留足够长的可见窗口，避免高速 CI 中阶段提示一闪而过造成假失败。
            time.sleep(0.30)
            state["preflight_count"] += 1
            fulfill_json(route, ready_preflight if state["preflight_count"] == 1 else blocked_preflight)
            return
        if parsed.path == "/api/analyze":
            time.sleep(0.12)
            fulfill_json(route, analyzed)
            return

        payload = json.loads(request.post_data) if request.post_data else None
        if request.method == "GET":
            response = client.get(path)
        elif request.method == "POST":
            response = client.post(path, json=payload) if payload is not None else client.post(path)
        elif request.method == "PUT":
            response = client.put(path, json=payload)
        else:
            response = client.request(request.method, path)
        if response.status_code >= 400:
            api_errors.append(f"{request.method} {path}: {response.status_code} {response.text}")
        route.fulfill(
            status=response.status_code,
            headers={key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-encoding", "transfer-encoding"}},
            body=response.content,
        )

    with sync_playwright() as playwright:
        executable = "/usr/bin/chromium" if Path("/usr/bin/chromium").exists() else None
        browser = playwright.chromium.launch(headless=True, executable_path=executable, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route("http://datawork.test/**", proxy)
        page.set_content(html, wait_until="domcontentloaded")
        page.get_by_text("服务已就绪").wait_for(state="visible", timeout=15000)
        page.locator(".workflow-strip").wait_for(state="visible")
        notice = page.get_by_role("alertdialog")
        if notice.count() and notice.is_visible():
            notice.get_by_role("button", name="我已了解，谨慎使用").click()

        # Instant analysis: loading stages, blank-column notice, preflight, result.
        page.locator("input[type=file]").set_input_files(str(csv_path))
        page.get_by_role("button", name="读取并检查数据").click()
        page.get_by_text("已自动排除 1 个").wait_for(state="visible")
        # Simple mode keeps the original split-by-value selector. Professional
        # mode adds explicit grouping without silently replacing that behavior.
        split_row = page.locator(".role-row").filter(has_text="batch")
        split_row.get_by_role("button", name="选择").last.click()
        page.get_by_text("通用批量模式已启用").wait_for(state="visible")
        page.get_by_role("button", name="专业模式").click()
        page.get_by_role("button", name="自定义分组").click()
        page.get_by_text("使用自定义分组").wait_for(state="visible")
        page.locator(".split-values-input").fill("B1,B2")
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="简洁模式").click()
        page.locator(".split-group-panel").wait_for(state="hidden")
        assert split_row.get_by_role("button", name="已选").is_visible()
        run_button = page.get_by_role("button", name="检查并执行分析")
        assert run_button.is_enabled()
        run_button.click()
        page.get_by_text("检查通过，可以开始分析").wait_for(state="visible")
        page.get_by_role("button", name="确认并开始分析").click()
        page.get_by_role("heading", name="分析结果").wait_for(state="visible", timeout=15000)

        # AI assistant is a non-blocking movable/resizable floating window.
        page.get_by_role("button", name="打开 AI 小助手").click()
        drawer = page.locator(".assistant-drawer")
        drawer.wait_for(state="visible")
        before = drawer.bounding_box()
        assert before
        header = drawer.locator(".assistant-simple-drag")
        header_box = header.bounding_box()
        assert header_box
        page.mouse.move(header_box["x"] + 100, header_box["y"] + 25)
        page.mouse.down()
        page.mouse.move(header_box["x"] + 45, header_box["y"] + 75, steps=5)
        page.mouse.up()
        moved = drawer.bounding_box()
        assert moved and (moved["x"] < before["x"] or moved["y"] > before["y"])

        resize_handle = drawer.get_by_role("button", name="调整 AI 小助手大小", exact=True)
        resize_box = resize_handle.bounding_box()
        assert resize_box
        page.mouse.move(resize_box["x"] + resize_box["width"] / 2, resize_box["y"] + resize_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(resize_box["x"] + resize_box["width"] / 2 + 70, resize_box["y"] + resize_box["height"] / 2 + 70, steps=5)
        page.mouse.up()
        resized = drawer.bounding_box()
        assert resized and resized["width"] > moved["width"] and resized["height"] > moved["height"]

        page.locator(".assistant-message-list").evaluate("(element) => element.scrollTop = element.scrollHeight")
        close_button = drawer.get_by_role("button", name="关闭 AI 小助手")
        assert close_button.is_visible()
        drawer.get_by_role("button", name="收起 AI 小助手").click()
        page.locator(".assistant-message-list").wait_for(state="hidden")
        drawer.get_by_role("button", name="展开 AI 小助手").click()
        page.locator(".assistant-message-list").wait_for(state="visible")
        close_button.click()
        drawer.wait_for(state="hidden")

        # Invalid plan: actionable preflight, return/focus target, stale result removed.
        page.locator("#analysis-method select").first.select_option("twoway_anova")
        assert page.get_by_role("heading", name="分析结果").count() == 0
        page.get_by_text("原分析结果已失效").wait_for(state="visible")
        page.get_by_role("button", name="检查并执行分析").click()
        page.get_by_text("还缺少").wait_for(state="visible")
        page.get_by_role("button", name="去补充").first.click()
        page.locator("#analysis-roles.preflight-focus").wait_for(state="visible")

        # Structured error: user-readable message, retry and dismiss actions.
        state["profile_error"] = True
        page.locator("input[type=file]").set_input_files(str(csv_path))
        page.get_by_role("button", name="读取并检查数据").click()
        page.get_by_text("测试数据格式错误").wait_for(state="visible")
        assert page.get_by_role("button", name="重新读取数据").is_visible()
        page.get_by_role("button", name="关闭提示").click()
        page.get_by_text("测试数据格式错误").wait_for(state="hidden")

        # Workspace: project/dataset, save, preflight, run, report.
        state["profile_error"] = False
        page.get_by_role("button", name="项目工作区").click()
        page.get_by_role("button", name="E2E 项目").click()
        page.get_by_role("heading", name="E2E 项目").wait_for()
        page.get_by_role("button", name="E2E 数据").click()
        page.get_by_role("heading", name="保存分析计划").wait_for()
        page.locator("#workspace-analysis-method select").first.select_option("one_sample_ttest")
        page.locator("#workspace-analysis-method .analysis-mode-switch button").nth(1).click()
        workspace_preparation = page.locator("#workspace-data-preparation")
        workspace_preparation.locator("summary").click()
        pairing_editor = workspace_preparation.locator(".pairing-editor")
        pairing_editor.locator('.pairing-toggle input[type="checkbox"]').check()
        pairing_editor.locator(".pairing-grid select").first.select_option("group")
        pairing_editor.get_by_role("button", name="添加映射").click()
        workspace_mapping = pairing_editor.locator(".mapping-row").first
        workspace_mapping.locator("select").nth(0).select_option("A")
        workspace_mapping.locator("select").nth(1).select_option("B")
        workspace_builder = pairing_editor.locator(".pair-derived-builder")
        workspace_builder.get_by_placeholder("例如：ΔDR7").fill("WorkspaceAbs")
        workspace_builder.locator("select").nth(0).select_option("value")
        workspace_builder.get_by_placeholder("选择常用项或自行输入").fill("绝对量（保留原始尺度）")
        workspace_builder.locator("select").nth(2).select_option("abs_treatment")
        pairing_editor.get_by_role("button", name="添加计算列").click()
        workspace_role_section = page.locator("#workspace-analysis-roles")
        original_workspace_role = workspace_role_section.locator(
            ".role-row", has=page.get_by_text("value", exact=True)
        )
        original_workspace_dv = original_workspace_role.locator(
            'button.choice[aria-pressed]'
        ).first
        if original_workspace_dv.get_attribute("aria-pressed") == "true":
            original_workspace_dv.click()
        generated_workspace_role = workspace_role_section.locator(
            ".role-row", has=page.get_by_text("WorkspaceAbs", exact=True)
        )
        generated_workspace_role.wait_for()
        generated_workspace_role.locator('button.choice[aria-pressed]').first.click()
        save_button = page.get_by_role("button", name="保存计划", exact=True)
        assert save_button.is_enabled()
        save_button.click()
        page.wait_for_timeout(500)
        assert not api_errors, api_errors
        workspace_run = page.locator(".history-list").get_by_role("button", name="运行").first
        workspace_run.wait_for(state="visible")
        page.wait_for_function("(element) => !element.disabled", arg=workspace_run.element_handle())
        workspace_run.click()
        page.get_by_text("检查通过，可以开始分析").wait_for(timeout=15000)
        workspace_dialog = page.get_by_role("dialog", name="分析前检查")
        workspace_dialog.get_by_text("查看配对计算列").click()
        assert "WorkspaceAbs" in workspace_dialog.inner_text()
        assert "abs([处理值])" in workspace_dialog.inner_text()
        assert "绝对量（保留原始尺度）" in workspace_dialog.inner_text()
        page.get_by_role("button", name="确认并运行计划").click()
        page.get_by_role("heading", name="最新运行").wait_for(timeout=15000)
        page.get_by_role("button", name="生成报告").first.click()
        page.get_by_text("下载报告 ZIP").wait_for(timeout=15000)

        unnamed_buttons = page.locator("button").evaluate_all(
            "elements => elements.filter(element => !(element.getAttribute('aria-label') || element.textContent.trim())).length"
        )
        assert unnamed_buttons == 0, f"Found {unnamed_buttons} buttons without accessible names"
        assert not page_errors, page_errors
        browser.close()

    print("Web interaction audit passed: instant analysis, errors, AI floating window, workspace, report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
