import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("DATAWORK_UI_TEST_URL", "http://127.0.0.1:8765")
OUTPUT = ROOT / ".audit" / "ai-assistant-implementation-2026-07-20"
DATASET = ROOT / "golden_datasets" / "data" / "independent_groups.csv"


def mocked_guidance() -> dict:
    return {
        "source": "builtin",
        "guidance": {
            "suitability_status": "conditional",
            "suitability_label": "有条件适用",
            "suitability_reason": "方法与变量结构基本匹配，但需要先确认两组独立且分组只有两个水平。",
            "analysis_purpose": "比较两个独立组在当前分析变量上的差异。",
            "method_reason": "Welch t 检验允许两组方差不同，适合独立两组均值比较。",
            "expected_outcome": "输出组别描述统计、检验统计量、p 值、效应量和置信区间。",
            "design_review_summary": "当前计划需要核对独立性、分组水平和缺失。",
            "design_checks": ["确认两组样本彼此独立。", "确认分组列恰好包含两个有效水平。"],
            "recommended_actions": ["核对对象是否只出现在一个组。", "执行前检查每组有效样本数和异常值。"],
            "data_basis": ["当前数据集包含 20 行、2 列。", "分析变量：value。", "分类因素：group。"],
            "checks_before_run": ["确认变量角色。"],
            "limitations": ["观察性数据不能仅凭 p 值解释为因果关系。"],
            "alternatives": ["若两组来自同一对象，应改用配对 t 检验。"],
        },
    }


def mocked_step() -> dict:
    return {
        "source": "builtin",
        "explanation": {
            "title": "导入与检查数据",
            "purpose": "先确认字段、缺失、重复和列类型，再建立分析计划。",
            "what_to_check": ["检查缺失率和重复行。"],
            "next_actions": ["读取数据画像后选择统计方法。"],
            "key_risk": "错误的列类型会影响方法建议。",
        },
    }


OUTPUT.mkdir(parents=True, exist_ok=True)
requests: list[dict] = []
page_errors: list[str] = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def mock_assistant(route):
        payload = json.loads(route.request.post_data or "{}")
        requests.append({"url": route.request.url, "payload": payload})
        body = mocked_guidance() if route.request.url.endswith("analysis-plan") else mocked_step()
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False))

    page.route("**/api/ai/explain/**", mock_assistant)
    page.goto(BASE_URL, wait_until="networkidle")

    assert page.get_by_text("询问 AI：", exact=False).count() == 0
    assert page.get_by_role("button", name="打开 AI 小助手").count() == 1
    page.get_by_role("button", name="打开 AI 小助手").click()
    panel = page.get_by_role("complementary", name="AI 小助手")
    panel.wait_for(state="visible")
    page.screenshot(path=str(OUTPUT / "desktop-import-empty.png"), full_page=False)

    composer = page.get_by_label("自行提问")
    composer_box = composer.bounding_box()
    assert composer_box and composer_box["y"] + composer_box["height"] <= 720
    assert panel.get_by_text("快捷提问", exact=True).is_visible()
    assert panel.get_by_text("原始数据行默认不发送", exact=False).count() == 1
    panel.get_by_text("本次发送上下文", exact=True).click()
    assert panel.get_by_role("button", name="数据画像").is_disabled()
    assert panel.get_by_role("button", name="分析计划").is_disabled()
    assert panel.get_by_role("button", name="当前结果").is_disabled()
    panel.get_by_text("本次发送上下文", exact=True).click()

    panel.get_by_role("button", name="告诉我下一步").click()
    panel.get_by_text("先确认字段、缺失、重复和列类型", exact=False).wait_for()
    assert requests[-1]["payload"]["context"]["workflow_step"] == "import_data"
    assert "data_profile" not in requests[-1]["payload"]["context"]
    assert "selected_method" not in requests[-1]["payload"]["context"]

    page.get_by_role("button", name="关闭 AI 小助手").click()
    page.locator('input[type="file"]').set_input_files(str(DATASET))
    page.get_by_role("button", name="读取并检查数据").click()
    page.get_by_role("heading", name="建立分析计划").wait_for(timeout=15000)
    assert page.get_by_text("询问 AI：", exact=False).count() == 0
    page.get_by_role("button", name="打开 AI 小助手").click()
    page.get_by_text("本次发送上下文", exact=True).click()
    assert panel.get_by_role("button", name="数据画像").is_enabled()
    assert panel.get_by_role("button", name="分析计划").is_enabled()
    assert panel.get_by_role("button", name="当前结果").is_disabled()
    page.get_by_text("本次发送上下文", exact=True).click()
    panel.get_by_role("button", name="评估当前方法").click()
    panel.get_by_text("方法审查结论", exact=True).wait_for()
    assert panel.get_by_text("有条件适用", exact=True).is_visible()
    assert panel.get_by_role("heading", name="建议修改").is_visible()
    assert panel.get_by_role("heading", name="可比较的替代方法").is_visible()
    plan_payload = requests[-1]["payload"]["context"]
    assert plan_payload["selected_method"]
    assert plan_payload["data_profile"]
    page.screenshot(path=str(OUTPUT / "desktop-plan-answer.png"), full_page=False)

    page.get_by_role("button", name="展开 AI 小助手").click()
    expanded_box = panel.bounding_box()
    assert expanded_box and expanded_box["width"] >= 520 and expanded_box["height"] >= 680
    page.screenshot(path=str(OUTPUT / "desktop-expanded.png"), full_page=False)
    page.get_by_role("button", name="恢复悬浮尺寸").click()

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(150)
    mobile_panel = page.get_by_role("complementary", name="AI 小助手")
    mobile_box = mobile_panel.bounding_box()
    mobile_composer_box = page.get_by_label("自行提问").bounding_box()
    assert mobile_box and mobile_box["x"] >= 0 and mobile_box["x"] + mobile_box["width"] <= 390
    assert mobile_composer_box and mobile_composer_box["y"] + mobile_composer_box["height"] <= 844
    assert page.get_by_role("button", name="收起 AI 小助手").is_visible()
    page.screenshot(path=str(OUTPUT / "mobile-plan-answer.png"), full_page=False)

    browser.close()

assert len(requests) >= 2
assert any(item["payload"].get("question") == "结合当前导入状态，告诉我下一步最应该做什么。" for item in requests)
assert any(item["payload"].get("question", "").startswith("请明确判断当前统计方法") for item in requests)
assert not page_errors, page_errors
print(json.dumps({"ok": True, "requests": len(requests), "screenshots": str(OUTPUT)}, ensure_ascii=False))
