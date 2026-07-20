import json

from fastapi.testclient import TestClient

from datawork.ai.provider import LLMResponse, ModelInfo
from datawork.web.app import create_app


RESULT_ENVELOPE = {
    "kind": "single",
    "result": {
        "alpha": 0.05,
        "method": {
            "name": "twoway_anova",
            "label_zh": "双因素方差分析",
            "formula": "y ~ A * B",
            "research_question": "检验 A、B 及其交互作用。",
        },
        "design": {
            "n_observations": 60,
            "n_subjects": 60,
            "dependent_vars": ["y"],
            "between_factors": ["A", "B"],
        },
        "omnibus_tests": [
            {
                "effect": "A×B",
                "df_num": 2,
                "df_den": 54,
                "f_value": 4.56,
                "p_value": 0.014,
                "eta_sq_p": 0.145,
                "is_significant": True,
            }
        ],
        "warnings": [],
    },
}


RANKING_RESULT_ENVELOPE = {
    "kind": "single",
    "result": {
        "alpha": 0.05,
        "method": {"name": "oneway_anova", "label_zh": "单因素方差分析", "formula": "y ~ group"},
        "design": {"n_observations": 36, "dependent_vars": ["y"], "between_factors": ["group"]},
        "descriptive_stats": [
            {"group": "B", "n": 12, "mean": 6.0, "sd": 1.1},
            {"group": "C", "n": 12, "mean": 2.0, "sd": 0.9},
            {"group": "A", "n": 12, "mean": 9.0, "sd": 1.0},
        ],
        "significance_letters": [
            {"factor": "group", "method": "Tukey", "group": "A", "mean": 9.0, "letters": "a"},
            {"factor": "group", "method": "Tukey", "group": "B", "mean": 6.0, "letters": "b"},
            {"factor": "group", "method": "Tukey", "group": "C", "mean": 2.0, "letters": "c"},
        ],
        "warnings": [],
    },
}


def test_builtin_summary_and_normative_report_use_ordered_group_expression(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    explanation = client.post(
        "/api/ai/explain/result",
        json={"result": RANKING_RESULT_ENVELOPE, "question": "三组怎么排序？"},
    )
    assert explanation.status_code == 200, explanation.text
    findings = explanation.json()["result_guidance"]["findings"]
    assert any("A > B > C" in item for item in findings)

    report_response = client.post(
        "/api/ai/report/result",
        json={"result": RANKING_RESULT_ENVELOPE, "title": "组别排序报告", "use_ai": False},
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert any("A > B > C" in item for item in report["report"]["ordered_comparisons"])
    assert "## 本地只读排序（A > B > C）" in report["report_markdown"]
    assert "## 一、研究目的、统计方法与设计" not in report["report_markdown"]
    assert "A > B > C" in report["report_markdown"]
    assert "显著性以校正后的成对比较为准" in report["report_markdown"]
    assert any(
        "A[a] > B[b] > C[c]" in item
        for item in report["report"]["ordered_comparisons"]
    )


def test_ai_report_cannot_reverse_the_deterministic_group_order(tmp_path, monkeypatch):
    class ReversingProvider:
        async def generate_structured(self, messages, schema, max_tokens=None):
            parsed = schema(
                title="AI 组别排序报告",
                analysis_overview=["按当前结果生成报告。"],
                ordered_comparisons=["C > B > A"],
                conclusion=["排序见规范字段。"],
            )
            return LLMResponse(parsed=parsed, model="reversing-model")

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: ReversingProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    client.put(
        "/api/ai/settings",
        json={
            "enabled": True, "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "model": "reversing-model", "privacy_mode": "metadata_only",
            "secret_storage": "session", "remember_key": False, "api_key": "test-secret-value",
        },
    )
    response = client.post(
        "/api/ai/report/result",
        json={"result": RANKING_RESULT_ENVELOPE, "title": "AI 组别排序报告", "use_ai": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "ai"
    assert any("A > B > C" in item for item in payload["report"]["ordered_comparisons"])
    assert all("C > B > A" not in item for item in payload["report"]["ordered_comparisons"])
    assert len(payload["report"]["tables"]) == 3
    assert "按当前结果生成报告。" in payload["report"]["analysis_overview"]

    builtin_response = client.post(
        "/api/ai/report/result",
        json={"result": RANKING_RESULT_ENVELOPE, "title": "AI 组别排序报告", "use_ai": False},
    )
    assert builtin_response.status_code == 200, builtin_response.text
    assert payload["report"]["tables"] == builtin_response.json()["report"]["tables"]


def test_ai_cannot_override_deterministic_inference_hierarchy(tmp_path, monkeypatch):
    class HierarchyBreakingProvider:
        async def generate_structured(self, messages, schema, max_tokens=None):
            parsed = schema(
                title="AI 析因报告",
                inferential_results=["忽略交互，直接独立解释 A 主效应。"],
                follow_up_results=["在没有父检验依据时执行额外事后比较。"],
                conclusion=["结论仅依据 A 主效应。"],
            )
            return LLMResponse(parsed=parsed, model="hierarchy-breaking-model")

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: HierarchyBreakingProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    client.put(
        "/api/ai/settings",
        json={
            "enabled": True, "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "model": "hierarchy-breaking-model", "privacy_mode": "metadata_only",
            "secret_storage": "session", "remember_key": False, "api_key": "test-secret-value",
        },
    )

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "AI 析因报告", "use_ai": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["source"] == "ai_guard_partial"
    assert payload["report_control"]["mode"] == "deterministic"
    assert "忽略交互" not in "\n".join(payload["report"]["inferential_results"])
    assert "没有父检验依据" not in "\n".join(payload["report"]["follow_up_results"])
    assert "仅依据 A 主效应" not in "\n".join(payload["report"]["conclusion"])
    assert payload["report"]["inferential_results"] == []
    assert payload["report"]["follow_up_results"] == []
    assert payload["report"]["conclusion"] == []
    assert "未使用内置文字回填" not in payload.get("warning", "")


def test_ai_settings_are_managed_without_leaking_secret(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    catalog = client.get("/api/ai/providers")
    assert catalog.status_code == 200
    assert {item["kind"] for item in catalog.json()} >= {"deepseek", "openai", "ollama"}
    assert all(item["supports_discovery"] for item in catalog.json())

    response = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["settings"]["has_api_key"] is True
    assert "api_key" not in payload["settings"]
    assert "test-secret-value" not in response.text

    config_text = (tmp_path / "ai_settings.json").read_text(encoding="utf-8")
    assert "test-secret-value" not in config_text
    assert "api_key" not in json.loads(config_text)

    status = client.get("/api/ai/status").json()
    assert status["configured"] is True
    assert status["selection_required"] is False
    assert status["api_key_masked"] == "••••••••"

    cleared = client.delete("/api/ai/key")
    assert cleared.status_code == 200
    assert cleared.json()["status"]["has_api_key"] is False


def test_model_can_be_blank_until_discovery(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.put(
        "/api/ai/settings",
        json={
            "enabled": False,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert response.status_code == 200
    status = response.json()["settings"]
    assert status["connection_ready"] is True
    assert status["configured"] is False
    assert status["selection_required"] is True


def test_connection_discovers_models_and_requires_manual_selection(tmp_path, monkeypatch):
    class FakeProvider:
        async def list_models(self):
            return [
                ModelInfo(id="model-b", display_name="Model B", owned_by="vendor"),
                ModelInfo(
                    id="embed-only",
                    display_name="Embedding",
                    capabilities=["embedContent"],
                    selectable=False,
                ),
                ModelInfo(id="model-a", display_name="Model A", input_token_limit=128000),
            ]

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: FakeProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    client.put(
        "/api/ai/settings",
        json={
            "enabled": False,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )

    response = client.post("/api/ai/test")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model_count"] == 3
    assert payload["selectable_count"] == 2
    assert payload["selection_required"] is True
    assert payload["selected_model"] == ""
    assert {item["id"] for item in payload["models"]} == {"model-a", "model-b", "embed-only"}


def test_builtin_step_help_works_without_ai_configuration(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.post(
        "/api/ai/explain/step",
        json={
            "step": "welcome",
            "question": "下一步是什么？",
            "context": {"preview": [{"secret_column": "do-not-send"}]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "builtin"
    assert payload["explanation"]["title"] == "开始使用 DataWork"
    assert payload["setup_required"] is True


def test_analysis_guidance_uses_current_method_and_data(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.post(
        "/api/ai/explain/analysis-plan",
        json={
            "use_ai": False,
            "context": {
                "selected_method": "twoway_anova",
                "dependent_variables": ["株高"],
                "fixed_factors": ["品种", "水分处理"],
                "split_by": [],
                "alpha": 0.05,
                "ss_type": 3,
                "data_profile": {
                    "n_rows": 120,
                    "n_cols": 5,
                    "columns": [
                        {"name": "株高", "dtype": "float64", "n_unique": 110, "n_missing": 0},
                        {"name": "品种", "dtype": "object", "n_unique": 3, "n_missing": 0},
                        {"name": "水分处理", "dtype": "object", "n_unique": 4, "n_missing": 0},
                    ],
                },
            },
        },
    )
    assert response.status_code == 200
    guidance = response.json()["guidance"]
    assert "株高" in guidance["analysis_purpose"]
    assert "品种" in guidance["analysis_purpose"]
    assert "水分处理" in guidance["analysis_purpose"]
    assert "交互" in guidance["analysis_purpose"]
    assert "不会在计算前预测" in guidance["expected_outcome"]
    assert any("120 行" in item for item in guidance["data_basis"])
    assert guidance["suitability_status"] in {"suitable", "conditional", "needs_changes"}
    assert guidance["suitability_label"]
    assert guidance["suitability_reason"]
    assert guidance["recommended_actions"]
    assert guidance["alternatives"]


def test_builtin_result_explanation_preserves_engine_values(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    result = {
        "kind": "single",
        "result": {
            "method": {"label_zh": "双因素方差分析"},
            "alpha": 0.05,
            "omnibus_tests": [
                {
                    "effect": "A:B",
                    "f_value": 0.2626,
                    "p_value": 0.988308,
                    "eta_sq_p": 0.01,
                    "is_significant": False,
                }
            ],
        },
    }
    response = client.post(
        "/api/ai/explain/result", json={"result": result, "question": "怎么看？"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "builtin"
    findings = " ".join(payload["result_guidance"]["findings"])
    assert "0.2626" in findings
    assert "0.988308" in findings
    assert "未达到统计显著" in findings


def test_builtin_normative_report_is_separate_and_preserves_input(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    original = json.loads(json.dumps(RESULT_ENVELOPE))
    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "builtin"
    assert payload["report"]["title"] == "规范结果报告"
    assert payload["report"]["analysis_overview"] == []
    assert payload["report"]["descriptive_statistics"] == []
    assert payload["report"]["conclusion"] == []
    assert "## 一、研究目的、统计方法与设计" not in payload["report_markdown"]
    assert "## 三张规范统计表" in payload["report_markdown"]
    assert payload["report"]["tables"][0]["title"].startswith("表1.")
    assert len(payload["report"]["tables"]) == 3
    assert "效应" in payload["report"]["tables"][1]["columns"]
    assert "4.5600" in payload["report_markdown"]
    assert "0.014000" in payload["report_markdown"]
    assert "不包含内置文字报告" in payload["report_markdown"]
    assert RESULT_ENVELOPE == original


def test_builtin_batch_normative_report_displays_merged_models_without_ai(tmp_path, monkeypatch):
    class ForbiddenProvider:
        def __init__(self, *args, **kwargs):
            raise AssertionError("use_ai=false 时不得创建外部 AI provider")

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        ForbiddenProvider,
    )
    batch_result = {
        "kind": "batch",
        "result": {
            "method": "twoway_anova",
            "dv_col": "score",
            "factor_cols": ["A", "B", "C"],
            "split_cols": ["因素组合"],
            "settings": {"cross_model_p_adjust": "holm"},
            "results": [
                {"subset_key": "A × B", "n_rows": 48, "error": ""},
                {"subset_key": "A × C", "n_rows": 48, "error": "设计矩阵不可估计"},
            ],
            "overview": [
                {
                    "task_id": "task-1",
                    "factor_combination": "A × B",
                    "combination_order": 2,
                    "dependent_variable": "score",
                    "effect": "A × B",
                    "statistic_name": "F",
                    "statistic_value": 5.41,
                    "df_num": 1,
                    "df_den": 44,
                    "p_value": 0.0246,
                    "p_adjusted_across_tasks": 0.0492,
                    "p_adjust_method": "holm",
                    "significant_adjusted": True,
                    "conclusion": "校正后显著",
                }
            ],
        },
    }
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.post(
        "/api/ai/report/result",
        json={"result": batch_result, "title": "组合模型规范报告", "use_ai": False},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "builtin"
    assert "AI 文字总结通过独立请求生成" in payload["warning"]
    assert "表1. 各任务与设计单元描述性统计" in payload["report_markdown"]
    assert "跨模型校正 p" in payload["report"]["tables"][1]["columns"]
    assert "设计矩阵不可估计" in payload["report_markdown"]
    assert payload["report"]["descriptive_statistics"] == []
    assert "各组 M、SD 与 n 如下" not in payload["report_markdown"]
    assert "## 一、研究目的、统计方法与设计" not in payload["report_markdown"]


def test_ai_normative_report_passes_numeric_guard(tmp_path, monkeypatch):
    guard_inputs = []
    from datawork.ai.guard import guard_ai_output as real_guard_ai_output

    def capture_guard(ai_text, **kwargs):
        guard_inputs.append(ai_text)
        return real_guard_ai_output(ai_text, **kwargs)

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.guard_ai_output", capture_guard
    )

    class FakeProvider:
        async def generate_structured(self, messages, schema, max_tokens=None):
            assert max_tokens == 8192
            assert "tables" not in schema.model_fields
            assert "ordered_comparisons" not in schema.model_fields
            parsed = schema(
                title="双因素方差分析规范报告",
                analysis_overview=["采用双因素方差分析检验 A、B 及交互作用。"],
                data_and_design=["共分析 60 条观测，因变量为 y。"],
                assumption_review=["结果中未提供独立诊断检验。"],
                inferential_results=["A×B 交互达到统计显著，F(2,54)=4.56，p=0.014，偏 η²=0.145。"],
                follow_up_results=["显著交互应优先结合简单效应解释。"],
                effect_sizes_and_uncertainty=["交互作用的偏 η²=0.145。"],
                conclusion=["现有数据支持 A×B 交互作用。"],
                limitations=["统计显著性不等于实际重要性。"],
            )
            return LLMResponse(parsed=parsed, model="fake-report-model")

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: FakeProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "fake-report-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "ai"
    assert payload["model"] == "fake-report-model"
    assert payload["guard"]["passed"] is True
    assert "F(2,54)=4.56" in payload["report_markdown"]
    assert "## 七、规范统计表格" not in payload["report_markdown"]
    assert "组别序列化结论" not in payload["report_markdown"]
    assert "本页仅包含 AI 优化后的文字总结" in payload["report_markdown"]
    assert payload["report"]["tables"]
    assert guard_inputs
    assert "表1" not in guard_inputs[0]
    assert "组别排序与比较关系" not in guard_inputs[0]


def test_ai_normative_report_accepts_numeric_factor_labels_after_type_conversion(tmp_path, monkeypatch):
    class NumericLabelProvider:
        calls = 0

        async def generate_structured(self, messages, schema, max_tokens=None):
            self.calls += 1
            return LLMResponse(
                parsed=schema(
                    title="年份因素规范报告",
                    data_and_design=["年份因素包含 2024 与 2025 两个水平。"],
                    descriptive_statistics=[
                        "年份=2024、处理=1：n=12，M=8.2000，SD=1.1000。",
                        "年份=2025、处理=2：n=12，M=8.8000，SD=1.0000。",
                    ],
                    conclusion=["现有结果比较了 2024 与 2025 两个年份水平。"],
                ),
                model="numeric-label-model",
            )

        async def close(self):
            return None

    provider = NumericLabelProvider()
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: provider,
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "numeric-label-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200
    execution = {
        "kind": "single",
        "result": {
            "method": {"name": "twoway_anova", "label_zh": "双因素方差分析"},
            "design": {"between_factors": ["年份", "处理"], "dependent_vars": ["产量"]},
            "descriptive_stats": [
                {"年份": "2024", "处理": "1", "n": 12, "mean": 8.2, "sd": 1.1},
                {"年份": 2025, "处理": 2, "n": 12, "mean": 8.8, "sd": 1.0},
            ],
        },
    }

    response = client.post(
        "/api/ai/report/result",
        json={"result": execution, "title": "年份因素规范报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert provider.calls == 1
    assert payload["source"] == "ai"
    assert payload["guard"]["passed"] is True
    assert not payload.get("guard_repaired")


def test_ai_report_receives_read_only_ordering_tables_roles_and_bounded_preview(tmp_path, monkeypatch):
    captured = {}

    class EvidenceProvider:
        async def generate_structured(self, messages, schema, max_tokens=None):
            request_payload = json.loads(messages[1]["content"])
            captured["system_prompt"] = messages[0]["content"]
            captured["request_payload"] = request_payload
            captured.update(request_payload["ai_evidence_packet"])
            return LLMResponse(
                parsed=schema(
                    title="证据包报告",
                    analysis_overview=["采用双因素方差分析，统计结论见本地规范表。"],
                    conclusion=["组别顺序按 read_only_ordering 呈现，不据此推断显著差异。"],
                ),
                model="evidence-model",
            )

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: EvidenceProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "evidence-model",
            "privacy_mode": "include_preview",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    evidence_result = json.loads(json.dumps(RESULT_ENVELOPE))
    evidence_result["result"]["diagnostics"] = [
        {
            "test_name": "Levene",
            "statistic": 1.234,
            "p_value": 0.287,
            "passed": True,
            "detail": "方差齐性满足",
        }
    ]
    response = client.post(
        "/api/ai/report/result",
        json={
            "result": evidence_result,
            "title": "证据包报告",
            "use_ai": True,
            "analysis_context": {
                "execution_kind": "single",
                "method": {"name": "twoway_anova", "label_zh": "双因素方差分析"},
                "data_roles": {"dependent_variables": ["y"], "fixed_factors": ["year"]},
                "analysis_settings": {"alpha": 0.05},
                "data_profile": {
                    "n_rows": 25,
                    "n_cols": 3,
                    "columns": [
                        {"name": "y", "dtype": "float64"},
                        {"name": "year", "dtype": "object"},
                        {"name": "secret", "dtype": "object"},
                    ],
                },
                "data_preview": [
                    {"y": index, "year": 2024 + index % 2, "secret": "omit"}
                    for index in range(25)
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "ai"
    assert "沿统计证据链提炼规律" in captured["system_prompt"]
    assert "以规律为组织单位" in captured["system_prompt"]
    assert "不逐行转录表格" in captured["request_payload"]["synthesis_objective"]
    assert "reporting_order" not in captured["request_payload"]
    assert captured["request_payload"]["evidence_chain"][-1].startswith("可推广结论")
    assert "read_only_ordering" not in json.dumps(payload["report"], ensure_ascii=False)
    assert "本地只读排序" in " ".join(payload["report"]["conclusion"])
    assert len(captured["normative_tables"]) == 3
    assert captured["normative_tables"][0]["title"].endswith("描述性统计（M ± SD）")
    assert "效应量（含区间）" in captured["normative_tables"][1]["columns"]
    assert any(any("偏 η²=0.145000" in cell for cell in row) for row in captured["normative_tables"][1]["rows"])
    assert captured["assumption_checks"] == [
        {
            "test_name": "Levene",
            "statistic": 1.234,
            "p_value": 0.287,
            "passed": True,
            "detail": "方差齐性满足",
        }
    ]
    assert captured["evidence_inventory"]["effect_sizes_in_table_2"] == 1
    assert captured["evidence_inventory"]["computed_assumption_checks"] == 1
    assert captured["execution_kind"] == "single"
    assert captured["read_only_ordering"]["policy"].startswith("只读")
    assert captured["analysis_method"]["name"] == "twoway_anova"
    assert captured["data_roles"]["dependent_variables"] == ["y"]
    assert len(captured["data_preview"]) == 20
    assert set(captured["data_preview"][0]) == {"y", "year"}
    assert payload["evidence_summary"]["preview_rows_sent"] == 20
    assert payload["evidence_summary"]["preview_columns"] == ["y", "year"]
    assert payload["evidence_summary"]["effect_size_count"] == 1
    assert payload["evidence_summary"]["assumption_check_count"] == 1


def test_ai_normative_report_repairs_numeric_guard_failure(tmp_path, monkeypatch):
    class CorrectingProvider:
        calls = 0

        async def generate_structured(self, messages, schema, max_tokens=None):
            assert max_tokens == 8192
            self.calls += 1
            f_value = 9.99 if self.calls == 1 else 4.56
            parsed = schema(
                title="双因素方差分析规范报告",
                analysis_overview=["采用双因素方差分析检验 A、B 及交互作用。"],
                data_and_design=["共分析 60 条观测，因变量为 y。"],
                assumption_review=["结果中未提供独立诊断检验。"],
                inferential_results=[
                    f"A×B 交互达到统计显著，F(2,54)={f_value}，p=0.014，偏 η²=14.5%。"
                ],
                follow_up_results=["显著交互应优先结合简单效应解释。"],
                effect_sizes_and_uncertainty=["交互作用的偏 η²=14.5%。"],
                conclusion=["现有数据支持 A×B 交互作用。"],
                limitations=["统计显著性不等于实际重要性。"],
            )
            return LLMResponse(parsed=parsed, model="correcting-model")

        async def close(self):
            return None

    provider = CorrectingProvider()
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: provider,
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "correcting-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert provider.calls == 2
    assert payload["source"] == "ai"
    assert payload["guard_repaired"] is True
    assert payload["guard"]["passed"] is True
    assert "F(2,54)=4.56" in payload["report_markdown"]
    assert "9.99" not in payload["report_markdown"]


def test_ai_normative_report_exposes_reason_after_two_guard_failures(tmp_path, monkeypatch):
    class AlwaysWrongProvider:
        calls = 0

        async def generate_structured(self, messages, schema, max_tokens=None):
            self.calls += 1
            return LLMResponse(
                parsed=schema(
                    title="双因素方差分析规范报告",
                    inferential_results=["A×B 交互达到显著，F(2,54)=9.99，p=0.014。"],
                ),
                model="always-wrong-model",
            )

        async def close(self):
            return None

    provider = AlwaysWrongProvider()
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: provider,
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "always-wrong-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert provider.calls == 2
    assert payload["source"] == "ai_guard_failed"
    assert payload["guard_attempts"] == 2
    assert payload["guard"]["passed"] is False
    assert payload["guard_initial"]["passed"] is False
    assert "连续两次" in payload["warning"]
    assert "无法追溯" in payload["warning"]
    assert any("9.99" in item for item in payload["guard"]["violations"])


def test_ai_normative_report_only_replaces_sections_with_untraceable_numbers(tmp_path, monkeypatch):
    class PartiallyWrongProvider:
        calls = 0

        async def generate_structured(self, messages, schema, max_tokens=None):
            self.calls += 1
            return LLMResponse(
                parsed=schema(
                    title="双因素方差分析规范报告",
                    analysis_overview=["采用双因素方差分析检验因素及其交互作用。"],
                    inferential_results=["交互作用达到统计显著，F(2,54)=9.99，p=0.014。"],
                    conclusion=["现有结果支持结合交互作用解释数据。"],
                ),
                model="partially-wrong-model",
            )

        async def close(self):
            return None

    provider = PartiallyWrongProvider()
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: provider,
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "partially-wrong-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert provider.calls == 2
    assert payload["source"] == "ai_guard_partial"
    assert payload["guard"]["passed"] is True
    assert payload["guard_filtered"]["passed"] is False
    assert payload["guard_replaced_sections"] == ["总体与主要推断结果"]
    assert "研究目的与统计方法" in payload["guard_kept_sections"]
    assert payload["report"]["analysis_overview"] == ["采用双因素方差分析检验因素及其交互作用。"]
    assert payload["report"]["inferential_results"] == []
    assert "9.99" not in payload["report_markdown"]
    assert any("9.99" in item for item in payload["guard_filtered"]["violations"])
    assert "其余通过检查的 AI 文字已保留" in payload["warning"]


def test_empty_ai_report_is_retried_then_explains_why_text_was_not_applied(tmp_path, monkeypatch):
    class EmptyProvider:
        calls = 0

        async def generate_structured(self, messages, schema, max_tokens=None):
            assert max_tokens == 8192
            self.calls += 1
            return LLMResponse(error="empty response")

        async def close(self):
            return None

    provider = EmptyProvider()
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: provider,
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    configured = client.put(
        "/api/ai/settings",
        json={
            "enabled": True,
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "empty-model",
            "privacy_mode": "metadata_only",
            "secret_storage": "session",
            "remember_key": False,
            "api_key": "test-secret-value",
        },
    )
    assert configured.status_code == 200

    response = client.post(
        "/api/ai/report/result",
        json={"result": RESULT_ENVELOPE, "title": "规范结果报告"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert provider.calls == 2
    assert payload["source"] == "builtin"
    assert payload["report"]
    assert "notice" not in payload
    assert "连续两次未返回可读取的文字正文" in payload["warning"]
    assert "本地排序和三张规范表仍可正常使用" in payload["warning"]
    assert payload["report"]["analysis_overview"] == []
    assert "空响应" not in json.dumps(payload, ensure_ascii=False)


def test_remote_ai_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAWORK_BIND_HOST", "0.0.0.0")
    monkeypatch.delenv("DATAWORK_ALLOW_REMOTE_AI", raising=False)
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.post(
        "/api/ai/explain/step",
        json={"step": "welcome", "question": "", "context": {}},
    )
    assert response.status_code == 403
    assert "远程 AI 功能默认关闭" in response.json()["detail"]
