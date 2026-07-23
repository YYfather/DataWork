"""浏览器级核验：V1.7 MANOVA 因变量组合的即时分析与工作区全链路。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


BASE_URL = os.environ.get("DATAWORK_UI_TEST_URL", "http://127.0.0.1:8765")
ARTIFACT_DIR = Path(
    os.environ.get(
        "DATAWORK_UI_ARTIFACT_DIR",
        Path(tempfile.gettempdir()) / "datawork-v17-ui",
    )
)


CSV_TEXT = """group,y1,y2,y3,y4
A,1.0,3.2,5.1,2.4
A,1.4,2.8,5.7,2.0
A,1.8,3.6,4.8,2.9
A,2.1,3.1,6.2,3.3
A,2.5,4.0,5.5,2.7
A,2.9,3.7,6.5,3.8
A,3.2,4.4,5.9,3.1
A,3.7,4.1,6.8,4.2
B,4.2,5.0,7.1,4.8
B,4.7,5.8,6.6,5.4
B,5.1,5.3,7.8,4.9
B,5.6,6.2,7.3,6.0
B,6.0,5.9,8.4,5.6
B,6.5,6.8,7.9,6.7
B,7.0,6.4,8.8,6.1
B,7.4,7.3,8.2,7.2
"""


def acknowledge_release_notice(page: Page) -> None:
    notice = page.get_by_role("alertdialog")
    if notice.count() and notice.is_visible():
        notice.get_by_role("button", name="我已了解，谨慎使用").click()


def ensure_role(page: Page, column: str, role_index: int) -> None:
    row = page.locator(".role-row", has=page.get_by_text(column, exact=True)).first
    row.wait_for(timeout=10_000)
    button = row.locator('button.choice[aria-pressed]').nth(role_index)
    if button.get_attribute("aria-pressed") != "true":
        button.click()


def enable_combinations(page: Page, editor) -> None:
    dialog_messages: list[str] = []

    def accept(dialog) -> None:
        dialog_messages.append(dialog.message)
        dialog.accept()

    page.once("dialog", accept)
    editor.get_by_role("button", name="自动因变量组合").click()
    assert dialog_messages and "多个独立 MANOVA 模型" in dialog_messages[0]
    editor.locator(".combination-card").wait_for()
    text = editor.locator(".combination-estimate").inner_text()
    assert "候选因变量\n4" in text
    assert "因变量组合\n6" in text
    assert "Y1 + Y2 与 Y2 + Y1 只计算一次" in editor.inner_text()


def verify_instant(page: Page, csv_path: Path) -> None:
    page.locator('input[type="file"]').first.set_input_files(str(csv_path))
    page.get_by_role("button", name="读取并检查数据").click()
    page.get_by_text("建立分析计划", exact=True).wait_for(timeout=30_000)
    page.locator("#analysis-method select").select_option("oneway_manova")
    page.locator("#analysis-method .analysis-mode-switch button").nth(1).click()
    for column in ("y1", "y2", "y3", "y4"):
        ensure_role(page, column, 0)
    ensure_role(page, "group", 1)

    editor = page.locator(".outcome-group-editor").first
    enable_combinations(page, editor)
    editor.locator("details summary").click()
    editor.get_by_label("因变量组合名称 y1 + y2").fill("主要响应对")
    summary = page.locator("#instant-preflight-action")
    assert "共 6 个" in summary.inner_text()
    assert "最多 6 个" in summary.inner_text()

    page.get_by_role("button", name="检查并执行分析").click()
    preflight = page.get_by_role("dialog", name="分析前检查")
    preflight.wait_for(timeout=30_000)
    preflight.get_by_text("检查通过，可以开始分析", exact=True).wait_for(
        timeout=30_000
    )
    preflight_text = preflight.inner_text()
    assert "展开为 6 个任务" in preflight_text, preflight_text
    assert "Holm" in preflight_text, preflight_text
    preflight.locator("footer.preflight-actions button.primary").click()
    page.locator("#instant-analysis-result").wait_for(timeout=60_000)
    result_text = page.locator("#instant-analysis-result").inner_text()
    assert "主要响应对" in result_text
    assert "6" in result_text
    page.screenshot(path=str(ARTIFACT_DIR / "instant-combinations.png"), full_page=True)


def verify_workspace(page: Page, csv_path: Path) -> None:
    page.get_by_role("button", name="项目工作区").click()
    page.get_by_placeholder("新项目名称").fill("V1.7 因变量组合")
    page.get_by_role("button", name="创建项目").click()
    page.locator(".workspace-upload input[type='file']").set_input_files(str(csv_path))
    page.get_by_placeholder("数据集名称").fill("四响应 MANOVA")
    page.get_by_role("button", name="上传并建立指纹").click()
    page.locator("#workspace-analysis-roles").wait_for(timeout=30_000)

    page.locator("#workspace-analysis-method select").select_option("oneway_manova")
    page.locator("#workspace-analysis-method .analysis-mode-switch button").nth(1).click()
    workspace = page.locator("#workspace-analysis-roles")
    for column in ("y1", "y2", "y3", "y4"):
        row = workspace.locator(".role-row", has=page.get_by_text(column, exact=True)).first
        button = row.locator('button.choice[aria-pressed]').nth(0)
        if button.get_attribute("aria-pressed") != "true":
            button.click()
    group_row = workspace.locator(
        ".role-row", has=page.get_by_text("group", exact=True)
    ).first
    factor_button = group_row.locator('button.choice[aria-pressed]').nth(1)
    if factor_button.get_attribute("aria-pressed") != "true":
        factor_button.click()

    editor = workspace.locator(".outcome-group-editor")
    enable_combinations(page, editor)
    assert "预计最多 6 个任务" in workspace.inner_text()

    saved_payloads: list[dict] = []

    def capture_plan(request) -> None:
        if request.method == "POST" and "/plans" in request.url:
            saved_payloads.append(request.post_data_json)

    page.on("request", capture_plan)
    workspace.get_by_role("button", name="保存计划").click()
    page.locator("#workspace-run-plans").wait_for(timeout=30_000)
    assert saved_payloads
    plan = saved_payloads[-1]["plan"]
    assert plan["dependent_task_mode"] == "combinations"
    assert plan["dependent_combination_min_size"] == 2
    assert plan["dependent_combination_max_size"] == 2
    assert plan["cross_model_p_adjust"] == "holm"

    page.locator("#workspace-run-plans").get_by_role("button", name="运行").first.click()
    preflight = page.get_by_role("dialog", name="分析前检查")
    preflight.wait_for(timeout=30_000)
    preflight.get_by_text("检查通过，可以开始分析", exact=True).wait_for(
        timeout=30_000
    )
    preflight_text = preflight.inner_text()
    assert "展开为 6 个任务" in preflight_text, preflight_text
    preflight.locator("footer.preflight-actions button.primary").click()
    page.locator("#workspace-latest-result").wait_for(timeout=60_000)
    assert "6" in page.locator("#workspace-latest-result").inner_text()
    page.screenshot(path=str(ARTIFACT_DIR / "workspace-combinations.png"), full_page=True)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="datawork-v17-browser-") as temp_dir:
        csv_path = Path(temp_dir) / "manova-combinations.csv"
        csv_path.write_text(CSV_TEXT, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(BASE_URL, wait_until="networkidle")
            acknowledge_release_notice(page)
            health = page.evaluate(
                """async () => await (await fetch('/api/health')).json()"""
            )
            assert health["version"] == "1.7.0"
            assert health["features"]["dependent_variable_combinations"] is True
            verify_instant(page, csv_path)
            verify_workspace(page, csv_path)
            browser.close()

    if console_errors or page_errors:
        raise AssertionError(
            "浏览器错误: " + " | ".join([*console_errors, *page_errors])
        )
    print("V1.7 MANOVA 因变量组合的即时分析与工作区 6 任务全链路均通过")


if __name__ == "__main__":
    main()
