"""浏览器级核验：专业分组、自定义列和模式切换自动整理。"""

from __future__ import annotations

from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "reference" / "r" / "derived_split_factor.csv"


def main() -> None:
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto("http://127.0.0.1:8765", wait_until="networkidle")
        if page.locator(".session-gate").is_visible():
            page.locator(".session-gate button").click()
            page.locator(".session-gate").wait_for(state="detached", timeout=10000)
        page.locator('input[type="file"]').first.set_input_files(str(DATA))
        page.get_by_role("button", name="读取并检查数据").click()
        page.get_by_text("建立分析计划", exact=True).wait_for(timeout=30000)
        mode_buttons = page.locator("#analysis-method .analysis-mode-switch button")
        mode_buttons.nth(1).click()

        for label in ("数据准备与拆分", "模型与检验", "比较与结果", "批量任务"):
            assert page.get_by_text(label, exact=False).count() > 0, f"缺少专业分组: {label}"

        data_group = page.locator("details.calibration-panel").first
        data_group.locator("summary").click()
        editor = data_group.locator(".derived-column-editor")
        editor.get_by_placeholder("例如：增长率").fill("平均指标")
        editor.get_by_role("button", name="x1", exact=True).click()
        editor.get_by_role("button", name="+", exact=True).click()
        editor.get_by_role("button", name="x2", exact=True).click()
        editor.get_by_role("button", name="添加并预览").click()
        page.get_by_text("平均指标", exact=True).first.wait_for(timeout=30000)
        derived_role = page.locator(".role-row", has_text="平均指标")
        derived_role.first.wait_for(timeout=30000)
        assert derived_role.count() == 1
        derived_text = derived_role.inner_text()
        assert "自定义因变量" in derived_text
        unavailable_buttons = derived_role.get_by_role("button", name="不可用", exact=True)
        assert unavailable_buttons.count() >= 1
        assert all(unavailable_buttons.nth(index).is_disabled() for index in range(unavailable_buttons.count()))
        inherited_button = derived_role.get_by_role("button", name="继承", exact=True)
        assert inherited_button.count() == 1 and inherited_button.is_disabled()

        factor_row = page.locator(".role-row", has=page.get_by_text("factor", exact=True))
        factor_row.first.wait_for(timeout=10000)
        factor_buttons = factor_row.locator("button.choice")
        assert factor_buttons.count() >= 3, "当前方法没有同时显示分类因素和拆分角色"
        if factor_buttons.nth(1).get_attribute("aria-pressed") != "true":
            factor_buttons.nth(1).click()
        if "active" not in (factor_buttons.last.get_attribute("class") or ""):
            factor_buttons.last.click()
        factor_row.get_by_text("分类因素 + 自定义拆分", exact=True).wait_for(timeout=10000)
        assert "分析附加拆分：factor" in derived_role.inner_text()

        split_card = page.locator(".split-rule-card", has=page.get_by_text("factor", exact=True))
        split_card.first.wait_for(timeout=10000)
        first_group = split_card.locator(".split-custom-group").first
        first_group.get_by_role("button", name="A", exact=True).click()
        first_group.get_by_role("button", name="B", exact=True).click()
        split_card.get_by_role("button", name="添加分组", exact=False).click()
        second_group = split_card.locator(".split-custom-group").nth(1)
        second_group.get_by_role("button", name="C", exact=True).click()
        second_group.get_by_role("button", name="D", exact=True).click()
        assert "至少需要" not in split_card.inner_text()

        dialog_seen = {"value": False}
        def accept_dialog(dialog):
            dialog_seen["value"] = True
            assert "自动整理" in dialog.message
            dialog.accept()

        page.once("dialog", accept_dialog)
        mode_buttons.nth(0).click()
        assert dialog_seen["value"]
        mode_buttons.nth(0).wait_for(state="visible")
        page.wait_for_function("document.querySelector('#analysis-method .analysis-mode-switch button')?.classList.contains('active')")
        instant_editor = page.locator("#analysis-roles .derived-column-editor")
        instant_editor.first.wait_for(state="detached", timeout=10000)
        assert instant_editor.count() == 0
        assert page.locator(".role-row", has_text="平均指标").count() == 0

        with tempfile.TemporaryDirectory(prefix="datawork_ui_verify_") as directory:
            page.screenshot(path=str(Path(directory) / "verified.png"), full_page=True)
        browser.close()

    if console_errors:
        raise AssertionError("浏览器控制台错误: " + " | ".join(console_errors))
    print("专业分组、自定义列预览和简洁模式自动整理均通过浏览器核验")


if __name__ == "__main__":
    main()
