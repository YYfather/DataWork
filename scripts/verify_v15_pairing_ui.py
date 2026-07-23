"""浏览器级核验：V1.5 配对编辑、角色限制、分层预检和即时执行。"""

from __future__ import annotations

from pathlib import Path
import os
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "reference" / "r" / "agronomy_example_2.csv"
BASE_URL = os.environ.get("DATAWORK_UI_TEST_URL", "http://127.0.0.1:8765")


def main() -> None:
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(BASE_URL, wait_until="networkidle")
        if page.locator(".session-gate").is_visible():
            page.locator(".session-gate button").click()
            page.locator(".session-gate").wait_for(state="detached", timeout=10000)

        health = page.evaluate(
            """async () => await (await fetch('/api/health')).json()"""
        )
        assert health["version"] == "1.5.0"
        features = health["features"]
        assert features["pairing_workflow"] is True
        assert features["dependent_variable_groups"] is True

        page.locator('input[type="file"]').first.set_input_files(str(DATA))
        page.get_by_role("button", name="读取并检查数据").click()
        page.get_by_text("建立分析计划", exact=True).wait_for(timeout=30000)
        page.locator("#analysis-method select").select_option("one_sample_ttest")
        mode_buttons = page.locator("#analysis-method .analysis-mode-switch button")
        mode_buttons.nth(1).click()

        data_details = page.locator("details.calibration-panel").first
        if data_details.get_attribute("open") is None:
            data_details.locator("summary").click()
        editor = data_details.locator(".pairing-editor")
        editor.wait_for(timeout=10000)
        editor.locator('.pairing-toggle input[type="checkbox"]').check()
        editor.locator(".pairing-grid select").first.select_option(
            label="脱叶剂喷施时间"
        )
        editor.get_by_role("button", name="添加映射").click()
        mapping = editor.locator(".mapping-row").first
        mapping.locator("select").nth(0).select_option("T1")
        mapping.locator("select").nth(1).select_option("CK1")

        match_block = editor.locator(".pairing-block").filter(has_text="匹配标签")
        for label in ("年份", "品种", "种植模式"):
            match_block.get_by_role("button", name=label, exact=True).click()

        editor.get_by_placeholder("例如：ΔDR7").fill("NDR7")
        editor.locator(".pair-derived-builder select").select_option(
            label="7d脱叶率"
        )
        editor.get_by_placeholder("[处理值] - [对照值]").fill("[对照值]")
        editor.get_by_role("button", name="添加计算列").click()
        editor.locator(".pair-derived-list", has_text="NDR7").wait_for(timeout=10000)

        for column in ("7d脱叶率", "14d脱叶率", "21d脱叶率"):
            row = page.locator(".role-row", has=page.get_by_text(column, exact=True))
            if row.count():
                dependent_button = row.locator('button.choice[aria-pressed]').first
                if dependent_button.count() and dependent_button.get_attribute("aria-pressed") == "true":
                    dependent_button.click()

        generated_row = page.locator(".role-row", has=page.get_by_text("NDR7", exact=True))
        generated_row.wait_for(timeout=10000)
        generated_row.locator('button.choice[aria-pressed]').first.click()
        inherited = generated_row.get_by_role("button", name="继承", exact=True)
        assert inherited.count() == 1 and inherited.is_disabled()
        assert "配对因变量" in generated_row.inner_text()

        page.get_by_role("button", name="检查并执行分析").click()
        dialog = page.get_by_role("dialog", name="分析前检查")
        dialog.wait_for(timeout=30000)
        dialog.get_by_text("第 1 级：处理—对照配对与新列", exact=True).wait_for()
        assert "216" in dialog.inner_text()
        assert "36" in dialog.inner_text()
        dialog.get_by_text("第 2 级：任务展开计划", exact=True).wait_for()
        assert "最终任务" in dialog.inner_text()
        assert dialog.locator(".preflight-status.ready").count() == 1

        dialog.get_by_role("button", name="确认并开始分析").click()
        page.locator("#instant-analysis-result").wait_for(timeout=60000)
        assert page.locator("#instant-analysis-result").is_visible()

        with tempfile.TemporaryDirectory(prefix="datawork_v15_ui_") as directory:
            page.screenshot(
                path=str(Path(directory) / "v15-pairing-verified.png"),
                full_page=True,
            )
        browser.close()

    if console_errors:
        raise AssertionError("浏览器控制台错误: " + " | ".join(console_errors))
    print("V1.5 配对编辑、角色限制、分层预检和即时执行均通过浏览器核验")


if __name__ == "__main__":
    main()
