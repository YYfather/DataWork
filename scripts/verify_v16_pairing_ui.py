"""浏览器级核验：V1.6 配对列连续新增、复制、编辑、绝对值和预检审核。"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "reference" / "r" / "agronomy_example_2.csv"
BASE_URL = os.environ.get("DATAWORK_UI_TEST_URL", "http://127.0.0.1:8765")


def main() -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
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
        if page.locator(".session-gate").is_visible():
            page.locator(".session-gate button").click()
            page.locator(".session-gate").wait_for(state="detached", timeout=10000)
        notice = page.get_by_role("alertdialog")
        if notice.count() and notice.is_visible():
            notice.get_by_role("button", name="我已了解，谨慎使用").click()

        health = page.evaluate(
            """async () => await (await fetch('/api/health')).json()"""
        )
        assert health.get("features", {}).get("pairing_abs") is True, health

        page.locator('input[type="file"]').first.set_input_files(str(DATA))
        page.get_by_role("button", name="读取并检查数据").click()
        page.get_by_text("建立分析计划", exact=True).wait_for(timeout=30000)
        page.locator("#analysis-method select").select_option("one_sample_ttest")
        page.locator("#analysis-method .analysis-mode-switch button").nth(1).click()

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

        builder = editor.locator(".pair-derived-builder")
        name_input = builder.get_by_placeholder("例如：ΔDR7")
        source_select = builder.locator("select").nth(0)
        decimal_select = builder.locator("select").nth(1)
        preset_select = builder.locator("select").nth(2)
        unit_input = builder.get_by_placeholder("选择常用项或自行输入")
        formula_input = builder.get_by_placeholder("[处理值] - [对照值]")

        name_input.fill("AbsDelta7")
        source_select.select_option(label="7d脱叶率")
        unit_input.fill("绝对量（保留原始尺度）")
        decimal_select.select_option("3")
        preset_select.select_option(label="处理—对照绝对差")
        assert formula_input.input_value() == "abs([处理值] - [对照值])"
        assert unit_input.input_value() == "绝对量（保留原始尺度）"
        editor.get_by_role("button", name="添加计算列").click()
        editor.locator(".pair-derived-list", has_text="AbsDelta7").wait_for()

        # 添加后继承全部参数，名称自动聚焦并全选。
        assert name_input.input_value() == "AbsDelta7"
        assert source_select.input_value() == "7d脱叶率"
        assert formula_input.input_value() == "abs([处理值] - [对照值])"
        assert unit_input.input_value() == "绝对量（保留原始尺度）"
        assert decimal_select.input_value() == "3"
        selection = name_input.evaluate(
            "element => [element.selectionStart, element.selectionEnd, element.value.length]"
        )
        assert selection == [0, len("AbsDelta7"), len("AbsDelta7")]

        name_input.fill("AbsDelta14")
        source_select.select_option(label="14d脱叶率")
        editor.get_by_role("button", name="添加计算列").click()
        assert editor.locator(".pair-derived-list article").count() == 2

        # “以此新增”复制参数但不进入编辑；清空只清草稿。
        first_row = editor.locator(".pair-derived-list article").nth(0)
        first_row.get_by_role("button", name="以此新增").click()
        assert name_input.input_value() == "AbsDelta7"
        assert source_select.input_value() == "7d脱叶率"
        editor.get_by_role("button", name="清空重新填写").click()
        assert name_input.input_value() == ""
        assert source_select.input_value() == ""
        assert formula_input.input_value() == ""
        assert unit_input.input_value() == ""
        assert decimal_select.input_value() == "8"
        assert editor.locator(".pair-derived-list article").count() == 2

        # 编辑保留原列身份，保存后不会意外新增第三列。
        first_row.get_by_role("button", name="编辑").click()
        name_input.fill("AbsDelta7Renamed")
        editor.get_by_role("button", name="保存计算列").click()
        assert editor.locator(".pair-derived-list article").count() == 2
        editor.get_by_text("AbsDelta7Renamed", exact=True).wait_for()

        # 模板不覆盖单位；竖线输入在保存时规范为 abs(...)。
        unit_input.fill("自定义单位")
        preset_select.select_option(label="处理值")
        assert unit_input.input_value() == "自定义单位"
        name_input.fill("BarDelta")
        source_select.select_option(label="21d脱叶率")
        formula_input.fill("|[处理值] - [对照值]|")
        editor.get_by_role("button", name="添加计算列").click()
        bar_row = editor.locator(".pair-derived-list article").filter(
            has_text="BarDelta"
        )
        assert "abs([处理值] - [对照值])" in bar_row.inner_text()

        # 只选择一个配对列作为因变量，核验后端规范化公式与单位进入预检。
        for column in ("7d脱叶率", "14d脱叶率", "21d脱叶率"):
            row = page.locator(".role-row", has=page.get_by_text(column, exact=True))
            if row.count():
                button = row.locator('button.choice[aria-pressed]').first
                if button.count() and button.get_attribute("aria-pressed") == "true":
                    button.click()
        generated_row = page.locator(
            ".role-row",
            has=page.get_by_text("AbsDelta7Renamed", exact=True),
        )
        generated_row.wait_for(timeout=10000)
        generated_row.locator('button.choice[aria-pressed]').first.click()
        page.get_by_role("button", name="检查并执行分析").click()
        dialog = page.get_by_role("dialog", name="分析前检查")
        dialog.wait_for(timeout=30000)
        dialog.get_by_text("查看配对计算列").click()
        assert "AbsDelta7Renamed" in dialog.inner_text()
        assert "abs([处理值] - [对照值])" in dialog.inner_text()
        assert "绝对量（保留原始尺度）" in dialog.inner_text()
        assert "无效/缺失" in dialog.inner_text()
        browser.close()

    if console_errors or page_errors:
        raise AssertionError(
            "浏览器错误: "
            + " | ".join([*console_errors, *page_errors])
        )
    print("V1.6 配对列连续新增、复制、编辑、abs 规范化和预检审核均通过")


if __name__ == "__main__":
    main()
