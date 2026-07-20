import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("DATAWORK_UI_TEST_URL", "http://127.0.0.1:8765")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    ai_requests = []
    ai_report_requests = []
    all_ai_report_requests = []
    builtin_report_responses = []
    batch_status_polls = []
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def handle_ai_request(route):
        request = route.request
        ai_requests.append({
            "url": request.url,
            "payload": json.loads(request.post_data or "{}"),
        })
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "source": "builtin",
                "explanation": {
                    "title": "测试说明", "purpose": "验证助手导航",
                    "what_to_check": [], "next_actions": [], "key_risk": "无",
                },
                "guidance": {
                    "suitability_status": "conditional", "suitability_label": "有条件适用",
                    "suitability_reason": "当前方法基本匹配，仍需核对设计条件。",
                    "analysis_purpose": "验证上下文", "method_reason": "验证入口",
                    "expected_outcome": "验证请求", "design_checks": ["核对变量角色"],
                    "recommended_actions": ["确认样本独立性"], "data_basis": [],
                    "checks_before_run": [], "limitations": [], "alternatives": [],
                },
                "result_guidance": {
                    "title": "自由提问回答", "summary": "已按当前完整结果回答。",
                    "findings": ["1 > 0（按组均值排序）"], "next_checks": [], "cautions": [],
                },
            }, ensure_ascii=False),
        )

    page.route("**/api/ai/explain/**", handle_ai_request)

    def handle_ai_report(route):
        payload = json.loads(route.request.post_data or "{}")
        all_ai_report_requests.append(payload)
        if not payload.get("use_ai"):
            route.continue_()
            return
        ai_report_requests.append(payload)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "source": "ai",
                "provider": "browser-test",
                "model": "mock-report-model",
                "evidence_summary": {
                    "table_count": 3, "ordering_count": 2,
                    "effect_size_count": 6, "assumption_check_count": 4,
                    "role_column_count": 5, "preview_rows_sent": 0,
                    "preview_columns": [], "privacy_mode": "metadata_only",
                },
                "report": {
                    "title": payload.get("title", "AI 文字总结"),
                    "analysis_overview": ["AI 已在不改写统计表的前提下优化多模型报告表述。"],
                    "data_and_design": ["组合模型的任务边界与内置报告保持一致。"],
                    "descriptive_statistics": ["完整描述统计保留在合并工作簿。"],
                    "assumption_review": ["各子模型分别复核假设。"],
                    "inferential_results": ["本次不做跨模型校正，直接解释原始 p。"],
                    "follow_up_results": [
                        "排序方向与read_only_ordering一致。第一项比较见表3。第二项比较见表3。第三项比较见表3。第四项比较见表3。"
                    ],
                    "effect_sizes_and_uncertainty": ["效应量不因 p 值校正而改变。"],
                    "conclusion": ["这是浏览器验收用 AI 优化结论。"],
                    "limitations": ["AI 只优化文字，数值以计算内核为准。"],
                    "tables": [{"title": "表1. 多模型结果总览", "columns": ["任务 ID"], "rows": [["task-1"]]}],
                },
                "report_markdown": "# AI 文字总结\n\n这是浏览器验收用 AI 优化结论。",
            }, ensure_ascii=False),
        )

    page.route("**/api/ai/report/result", handle_ai_report)

    def handle_batch_status(route):
        batch_status_polls.append(route.request.url)
        if len(batch_status_polls) <= 2:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"status": "preparing"}, ensure_ascii=False),
            )
            return
        route.continue_()

    page.route("**/api/batch/exports/*/status", handle_batch_status)
    page.on("response", lambda response: builtin_report_responses.append(response)
            if response.url.endswith("/api/ai/report/result")
            and response.request.post_data_json.get("use_ai") is False else None)
    page.route("**/api/ai/status", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"enabled": True, "configured": True, "provider": "browser-test", "model": "mock-report-model"}),
    ))
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    workflow = page.locator(".workflow-strip")
    assert workflow.get_by_role("button").count() == 5
    workflow.get_by_role("button", name="跳转到选择文件").click()
    assert "workflow-jump-highlight" in (page.locator("#instant-data-import").get_attribute("class") or "")
    workflow.get_by_role("button", name="跳转到查看结果").click()
    assert "workflow-jump-highlight" in (page.locator("#instant-data-import").get_attribute("class") or "")

    page.get_by_role("button", name="打开 AI 小助手").click()
    page.get_by_text("本步建议", exact=True).wait_for()
    assert page.get_by_role("heading", name="导入并检查数据").is_visible()
    assert page.get_by_text("原始数据行默认不发送", exact=False).count() == 1
    assert ai_requests == []

    with page.expect_response(lambda response: "/api/ai/explain/" in response.url):
        page.get_by_role("button", name="告诉我下一步").click()
    assert len(ai_requests) == 1
    assert ai_requests[0]["payload"]["context"]["workflow_step"] == "import_data"

    page.get_by_role("button", name="关闭 AI 小助手").click()
    page.locator('input[type="file"]').first.set_input_files(
        ROOT / "golden_datasets" / "data" / "factorial_four_multivariate_v2.csv"
    )
    page.get_by_role("button", name="读取并检查数据").click()
    page.get_by_text("建立分析计划", exact=True).wait_for(timeout=30000)
    workflow.get_by_role("button", name="跳转到检查数据").click()
    assert "workflow-jump-highlight" in (page.locator("#instant-data-check").get_attribute("class") or "")
    workflow.get_by_role("button", name="跳转到建立计划").click()
    assert "workflow-jump-highlight" in (page.locator("#analysis-roles").get_attribute("class") or "")
    page.get_by_role("button", name="打开 AI 小助手").click()
    assert page.get_by_label("AI 小助手", exact=True).get_by_role("heading", name="建立分析计划").is_visible()
    with page.expect_response(lambda response: "/api/ai/explain/analysis-plan" in response.url):
        page.get_by_role("button", name="评估当前方法").click()
    question = "请明确判断当前统计方法是否适合这份数据和变量角色，并说明证据。"
    directed = next(
        request["payload"] for request in reversed(ai_requests)
        if request["url"].endswith("/api/ai/explain/analysis-plan")
        and request["payload"].get("question") == question
    )
    assert directed["question"] == question
    assert directed["context"]["workflow_step"] == "build_plan"
    assert directed["context"]["selected_method"]
    assert "dependent_variables" in directed["context"]
    assert page.get_by_label("AI 小助手", exact=True).locator(".assistant-verdict").last.is_visible()
    assistant_screenshot = ROOT / ".ui-assistant-sync-verification.png"
    page.screenshot(path=str(assistant_screenshot), full_page=False)
    page.get_by_text("本次发送上下文", exact=True).click()
    live_context = page.locator(".assistant-context-body").inner_text()
    assert "方法" in live_context and "multifactor_" not in live_context
    page.get_by_role("button", name="关闭 AI 小助手").click()

    assert page.get_by_text("校正（Calibration）", exact=True).count() == 0
    assert page.get_by_text("分类因素组合实验", exact=True).count() == 0
    concise_cross_model = page.get_by_label("跨模型校正方法")
    assert concise_cross_model.is_visible()
    concise_cross_model.select_option("none")
    page.get_by_role("button", name="专业模式").first.click()
    assert page.get_by_text("校正（Calibration）", exact=True).is_visible()
    assert page.get_by_label("跨模型校正方法").input_value() == "none"
    confirmation = page.get_by_role("button", name="确认并启用组合实验")
    for factor_name in ("A", "B"):
        factor_row = page.locator(".role-row.dynamic-role-row").filter(has=page.get_by_text(factor_name, exact=True)).first
        assert factor_row.locator("strong").first.inner_text() == factor_name
        factor_button = factor_row.locator("button.choice").nth(1)
        if factor_button.get_attribute("aria-pressed") != "true":
            factor_button.click()
            if confirmation.is_visible():
                confirmation.click()
    combination_toggle = page.locator('.factor-combination-panel input[type="checkbox"]').first
    if not combination_toggle.is_checked():
        combination_toggle.check()
    order_label = page.get_by_text("计算阶数（最高阶 k）", exact=False).first
    assert order_label.is_visible(), page.locator(".factor-combination-panel").first.inner_text()
    order_label.locator("select").select_option("1")
    page.get_by_text("编辑组合名称（可选）", exact=True).first.click()
    page.get_by_label("组合名称 A", exact=True).fill("主处理模型")
    page.get_by_label("组合名称 B", exact=True).fill("辅助处理模型")
    page.get_by_label("组合名称 B", exact=True).press("Tab")
    page.wait_for_timeout(100)
    assert "判断 p 与原始 p 完全相同" in page.locator(".combination-warning").first.inner_text()

    with page.expect_response(lambda response: response.url.endswith("/api/preflight")) as first_preflight:
        page.get_by_role("button", name="检查并执行分析").click()
    first_preflight_payload = first_preflight.value.json()
    assert first_preflight_payload["batch_summary"]["group_count"] > 1, first_preflight_payload
    assert first_preflight_payload["batch_summary"]["p_adjust"] == "none"
    preview_names = {item["key"]["factor_combination"] for item in first_preflight_payload["batch_summary"]["groups"]}
    assert preview_names == {"主处理模型", "辅助处理模型"}, preview_names
    assert {item["key"]["factor_columns"] for item in first_preflight_payload["batch_summary"]["groups"]} == {"A", "B"}
    page.get_by_role("heading", name="多模型运行确认").wait_for(timeout=5000)
    assert "不校正" in page.locator(".multi-run-alert").inner_text()
    assert "判断 p 不会被修改" in page.locator(".multi-run-alert").inner_text()
    multi_confirm = page.get_by_role("button", name=re.compile(r"^确认并运行 \d+ 个模型$"))
    assert "个模型" in multi_confirm.inner_text()
    with page.expect_response(lambda response: response.url.endswith("/api/analyze")) as analysis_response:
        multi_confirm.click()
    analysis_payload = analysis_response.value.json()
    test_rows = [row for row in analysis_payload["result"]["summary"] if row.get("result_type") == "test"]
    assert test_rows
    assert all(row["p_adjust_method"] == "none" for row in test_rows)
    assert {row["factor_combination"] for row in test_rows} == {"主处理模型", "辅助处理模型"}
    assert {row["factor_columns"] for row in test_rows} == {"A", "B"}
    page.get_by_text("分析结果", exact=True).wait_for(timeout=60000)
    result_panel = page.locator("#instant-analysis-result")
    workflow.get_by_role("button", name="跳转到查看结果").click()
    assert "workflow-jump-highlight" in (result_panel.get_attribute("class") or "")
    for _ in range(120):
        if builtin_report_responses:
            break
        page.wait_for_timeout(500)
    assert any(request.get("use_ai") is False for request in all_ai_report_requests), (
        all_ai_report_requests, page_errors, page.locator("body").inner_text()[-1500:]
    )
    assert builtin_report_responses, (all_ai_report_requests, page_errors)
    assert builtin_report_responses[-1].status == 200, builtin_report_responses[-1].text()

    report_panel = page.locator("#instant-ai-result-report")
    report_panel.get_by_role("button", name="本地排序与规范表", exact=True).wait_for(timeout=30000)
    report_panel.get_by_role("button", name="本地排序与规范表", exact=True).click()
    ordering = report_panel.locator(".comparison-sequence-disclosure")
    if ordering.count() and ordering.first.get_attribute("open") is None:
        ordering.first.locator("summary").click()
    report_panel_text = report_panel.inner_text()
    sequence_texts = report_panel.locator(".comparison-sequence-flow").all_inner_texts()
    assert any(re.search(r"(?:A2\s*>\s*A1|B2\s*>\s*B1)", text) for text in sequence_texts), report_panel_text
    assert "共 2 项 · 整体滚动查看" in ordering.first.locator("summary").inner_text()
    ordering_list = ordering.first.locator(".comparison-sequence-list.scrollable")
    assert ordering_list.count() == 1
    assert ordering_list.locator(":scope > article").count() == len(sequence_texts)
    assert ordering.first.locator(".comparison-sequence-more").count() == 0
    assert ordering_list.evaluate("element => getComputedStyle(element).overflowY") == "auto"
    ordering_list.evaluate("element => { const seed = element.querySelector('article'); for (let index = 0; seed && index < 24; index += 1) element.appendChild(seed.cloneNode(true)) }")
    ordering_scroll = ordering_list.evaluate("element => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight })")
    assert ordering_scroll["scrollHeight"] > ordering_scroll["clientHeight"], ordering_scroll
    ordering_list.evaluate("element => { element.scrollTop = element.scrollHeight }")
    assert ordering_list.evaluate("element => element.scrollTop") > 0
    assert report_panel.locator(".report-content-disclosure").count() == 0
    assert report_panel.locator(".report-table-disclosure").count() == 3, (
        builtin_report_responses[-1].json(), report_panel_text
    )
    evidence_metrics = report_panel.locator(".report-evidence-strip article")
    assert evidence_metrics.count() == 4
    local_effect_metric = evidence_metrics.filter(has_text="效应量").first
    local_assumption_metric = evidence_metrics.filter(has_text="前提检验").first
    assert int(local_effect_metric.locator("strong").inner_text()) > 0
    assert int(local_assumption_metric.locator("strong").inner_text()) > 0
    for label in ("下载合并结果 XLSX", "下载完整规范报告 ZIP", "下载规范报告 Markdown", "下载完整结果 JSON"):
        link = result_panel.get_by_role("link", name=label, exact=True)
        link.wait_for(timeout=30000)
        assert link.is_visible()
        assert link.get_attribute("href")

    per_batch_button = result_panel.get_by_role("button", name="逐批查看", exact=True)
    assert per_batch_button.is_visible()
    per_batch_button.click()
    batch_selector = result_panel.locator(".batch-task-switcher select")
    batch_selector.wait_for(timeout=5000)
    assert batch_selector.locator("option").count() == len(analysis_payload["result"]["results"])
    adjustment_table = result_panel.locator(".batch-detail-page > .result-block .result-table-disclosure").first
    assert adjustment_table.is_visible() and adjustment_table.get_attribute("open") is not None
    assert adjustment_table.locator("tbody tr").count() > 0
    if len(analysis_payload["result"]["results"]) > 1:
        batch_selector.select_option("1")
        assert "2 /" in result_panel.locator(".batch-task-context").inner_text()
        assert adjustment_table.locator("tbody tr").count() > 0
        result_panel.get_by_role("button", name="上一批", exact=True).click()
        assert batch_selector.input_value() == "0"
    batch_detail_screenshot = ROOT / ".ui-batch-detail-verification.png"
    page.screenshot(path=str(batch_detail_screenshot), full_page=False)
    result_panel.get_by_role("button", name="结果总览", exact=True).click()

    report_tables = report_panel.locator(".report-table-disclosure")
    assert report_tables.count() > 0
    effect_report_table = report_tables.nth(1)
    assert effect_report_table.get_attribute("open") is None
    effect_report_table.locator("summary").click()
    assert effect_report_table.get_attribute("open") is not None
    assert effect_report_table.locator("table").is_visible()
    assert effect_report_table.locator("tbody tr.effect-size-row").count() > 0
    assert "效应量（含区间）" in effect_report_table.locator("thead").inner_text()
    assert "补充效应量" not in effect_report_table.inner_text()
    table_scroll = effect_report_table.locator(".table-scroll")
    page.set_viewport_size({"width": 820, "height": 1000})
    page.wait_for_timeout(100)
    scroll_metrics = table_scroll.evaluate("element => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth })")
    assert scroll_metrics["scrollWidth"] > scroll_metrics["clientWidth"], scroll_metrics
    table_scroll.evaluate("element => { element.scrollLeft = element.scrollWidth }")
    assert table_scroll.evaluate("element => element.scrollLeft") > 0
    page.set_viewport_size({"width": 1440, "height": 1000})

    free_question = "请解释当前排序中哪些组别差异达到显著？"
    page.get_by_role("button", name="打开 AI 小助手").click()
    assert page.locator("#assistant-question-input").input_value() == ""
    page.locator("#assistant-question-input").fill(free_question)
    with page.expect_response(lambda response: response.url.endswith("/api/ai/explain/result")):
        page.get_by_role("button", name="发送", exact=True).click()
    assert page.locator("#assistant-question-input").input_value() == ""
    result_question_request = next(request["payload"] for request in reversed(ai_requests) if request["url"].endswith("/api/ai/explain/result"))
    assert result_question_request["question"] == free_question
    assert result_question_request["result"]["kind"] == "batch"
    page.get_by_role("button", name="展开 AI 小助手").click()
    assistant_panel = page.get_by_role("complementary", name="AI 小助手")
    assert "expanded" in (assistant_panel.get_attribute("class") or "")
    expanded_screenshot = ROOT / ".ui-assistant-expanded-verification.png"
    page.screenshot(path=str(expanded_screenshot), full_page=False)
    page.get_by_role("button", name="恢复悬浮尺寸").click()
    assert "expanded" not in (assistant_panel.get_attribute("class") or "")
    page.get_by_role("button", name="关闭 AI 小助手").click()

    report_panel.get_by_role("button", name="AI 文字总结", exact=True).wait_for(timeout=30000)
    assert len(ai_report_requests) == 1
    assert ai_report_requests[0]["result"]["kind"] == "batch"
    assert len(ai_report_requests[0]["result"]["result"]["results"]) == len(analysis_payload["result"]["results"])
    assert ai_report_requests[0]["result"]["result"]["summary"] == analysis_payload["result"]["summary"]
    assert ai_report_requests[0]["analysis_context"]["method"]["name"]
    assert ai_report_requests[0]["analysis_context"]["data_roles"]["dependent_variables"]
    assert len(ai_report_requests[0]["analysis_context"]["data_preview"]) <= 20
    assert report_panel.get_by_text("1 / 2", exact=True).is_visible()
    report_panel.get_by_role("button", name="AI 文字总结", exact=True).click()
    ai_text_disclosure = report_panel.locator(".report-content-disclosure")
    if ai_text_disclosure.get_attribute("open") is None:
        ai_text_disclosure.locator(":scope > summary").click()
    assert report_panel.get_by_text("这是浏览器验收用 AI 优化结论。", exact=True).is_visible()
    assert "read_only_ordering" not in report_panel.inner_text()
    ai_more = report_panel.locator(".ai-report-more")
    assert ai_more.count() > 0
    ai_more.first.locator("summary").click()
    assert ai_more.first.get_attribute("open") is not None
    assert report_panel.get_by_role("button", name="AI 文字总结", exact=True).get_attribute("aria-current") == "page"
    assert report_panel.locator(".report-content-disclosure").count() == 1
    assert report_panel.locator(".comparison-sequence-disclosure").count() == 0
    assert report_panel.locator(".ai-report-tables").count() == 0
    assert report_panel.locator(".report-evidence-strip").count() == 0
    ai_report_screenshot = ROOT / ".ui-ai-report-page-verification.png"
    page.screenshot(path=str(ai_report_screenshot), full_page=False)
    report_panel.get_by_role("button", name="上一页：本地排序与规范表", exact=True).click()
    assert report_panel.get_by_role("button", name="本地排序与规范表", exact=True).get_attribute("aria-current") == "page"
    assert report_panel.locator(".report-content-disclosure").count() == 0
    assert report_panel.get_by_text("AI 文字总结已经生成", exact=True).is_visible()
    assert report_panel.get_by_text("未调用外部 AI", exact=False).count() == 0
    report_screenshot = ROOT / ".ui-batch-report-pagination-verification.png"
    report_panel.scroll_into_view_if_needed()
    page.screenshot(path=str(report_screenshot), full_page=False)

    with page.expect_response(lambda response: response.url.endswith("/api/preflight")):
        page.get_by_role("button", name="检查并执行分析").click()
    page.get_by_role("heading", name="重复运行提醒").wait_for(timeout=30000)
    repeat_text = page.locator(".repeat-run-alert").inner_text()
    assert "历史运行不会被自动拼接" in repeat_text
    assert page.get_by_role("button", name=re.compile(r"^确认并运行 \d+ 个模型$")).is_visible()
    repeat_screenshot = ROOT / ".ui-repeat-run-verification.png"
    page.screenshot(path=str(repeat_screenshot), full_page=False)
    page.get_by_role("button", name="返回修改").click()

    screenshot = ROOT / ".ui-iteration-verification.png"
    page.screenshot(path=str(screenshot), full_page=True)
    print(f"UI verification passed; screenshots={assistant_screenshot},{expanded_screenshot},{batch_detail_screenshot},{report_screenshot},{ai_report_screenshot},{repeat_screenshot},{screenshot}")
    browser.close()
