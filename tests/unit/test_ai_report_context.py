import json

from fastapi.testclient import TestClient

from datawork.ai.provider import LLMResponse
from datawork.application.ai_assistant_service import (
    _assistant_ai_report_prose,
    _assistant_full_result_diagnostics,
    _normalize_result_context_selection,
)
from datawork.web.app import create_app


RESULT = {
    "kind": "single",
    "result": {
        "alpha": 0.05,
        "method": {"name": "oneway_anova", "label_zh": "单因素方差分析"},
        "omnibus_tests": [{"effect": "group", "f_value": 4.2, "p_value": 0.02}],
        "assumption_checks": [{"test": "Shapiro-Wilk", "p_value": 0.18}],
        "coefficients": [{"term": "Intercept", "estimate": 2.4}],
        "warnings": ["样本量较小"],
    },
}


def test_result_context_defaults_to_normative_evidence():
    selection = _normalize_result_context_selection(None)
    assert selection["current_result"] is True
    assert selection["result_scope"] == "normative_evidence"
    assert selection["include_ordering"] is True
    assert selection["ai_report"] is False


def test_full_result_context_adds_diagnostics_without_repeating_omnibus_table():
    payload = _assistant_full_result_diagnostics(RESULT)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "assumption_checks" in serialized
    assert "coefficients" in serialized
    assert "warnings" in serialized
    assert "omnibus_tests" not in serialized


def test_ai_report_must_belong_to_current_result_context():
    report = {
        "source": "ai",
        "report": {
            "title": "AI 总结",
            "conclusion": ["存在清晰的组别规律。"],
            "tables": [{"rows": [["不应进入助手"]]}],
            "ordered_comparisons": ["A > B"],
        },
    }
    stale, issue = _assistant_ai_report_prose(
        report,
        requested=True,
        result_context_id="run:new",
        ai_report_context_id="run:old",
    )
    assert stale is None
    assert "不属于当前分析运行" in issue

    current, issue = _assistant_ai_report_prose(
        report,
        requested=True,
        result_context_id="run:new",
        ai_report_context_id="run:new",
    )
    assert issue == ""
    assert current == {"title": "AI 总结", "conclusion": ["存在清晰的组别规律。"]}


def test_builtin_fallback_does_not_reveal_unselected_result(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.post("/api/ai/explain/result", json={
        "result": RESULT,
        "question": "结论是什么？",
        "selection": {"current_result": False},
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "builtin"
    assert "4.2" not in json.dumps(payload["result_guidance"], ensure_ascii=False)
    assert "未读取统计结果证据" in payload["result_guidance"]["title"]


def test_result_explanation_sends_only_selected_evidence_blocks(tmp_path, monkeypatch):
    calls: list[dict] = []

    class CapturingProvider:
        async def generate_structured(self, messages, schema, max_tokens=None):
            calls.append(json.loads(messages[-1]["content"]))
            return LLMResponse(
                parsed=schema(
                    title="结果解读",
                    summary="当前证据支持按规范表解释。",
                    findings=["先概括规律，再核对例外。"],
                    next_checks=[],
                    cautions=[],
                ),
                model="context-test-model",
            )

        async def close(self):
            return None

    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: CapturingProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    client.put("/api/ai/settings", json={
        "enabled": True,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "context-test-model",
        "privacy_mode": "metadata_only",
        "secret_storage": "session",
        "remember_key": False,
        "api_key": "test-secret-value",
    })

    response = client.post("/api/ai/explain/result", json={
        "result": RESULT,
        "question": "结论是什么？",
        "context": {"data_profile": {"n_rows": 12}, "selected_method": "oneway_anova"},
        "selection": {
            "data_profile": False,
            "analysis_plan": False,
            "current_result": True,
            "result_scope": "normative_evidence",
            "ai_report": False,
        },
    })
    assert response.status_code == 200, response.text
    selected = calls[-1]["selected_context"]
    assert set(selected) == {"normative_evidence"}
    assert "canonical_result" not in calls[-1]
    assert response.json()["context_basis"]["items"][0]["label"].endswith("规范化证据")
    assert response.json()["context_basis"]["items"][1]["key"] == "read_only_ordering"

    response = client.post("/api/ai/explain/result", json={
        "result": RESULT,
        "question": "只根据规范表概括。",
        "selection": {
            "current_result": True,
            "result_scope": "normative_evidence",
            "include_ordering": False,
        },
    })
    assert response.status_code == 200, response.text
    selected = calls[-1]["selected_context"]
    assert "read_only_ordering" not in selected["normative_evidence"]
    assert all(
        item["key"] != "read_only_ordering"
        for item in response.json()["context_basis"]["items"]
    )

    response = client.post("/api/ai/explain/result", json={
        "result": RESULT,
        "question": "诊断如何？",
        "selection": {
            "current_result": True,
            "result_scope": "full_result",
        },
    })
    assert response.status_code == 200, response.text
    selected = calls[-1]["selected_context"]
    assert set(selected) == {"normative_evidence", "full_result_and_diagnostics"}

    response = client.post("/api/ai/explain/result", json={
        "result": RESULT,
        "question": "结合已有总结说明规律。",
        "context": {
            "data_profile": {"n_rows": 12, "columns": []},
            "selected_method": "oneway_anova",
            "selected_method_label": "单因素方差分析",
            "dependent_variables": ["y"],
            "fixed_factors": ["group"],
        },
        "selection": {
            "data_profile": True,
            "analysis_plan": True,
            "current_result": False,
            "ai_report": True,
        },
        "ai_report": {
            "source": "ai",
            "report": {"conclusion": ["总体呈现清晰的组别规律。"]},
        },
        "result_context_id": "run:1",
        "ai_report_context_id": "run:1",
    })
    assert response.status_code == 200, response.text
    selected = calls[-1]["selected_context"]
    assert set(selected) == {
        "data_profile",
        "analysis_plan",
        "ai_generated_report_for_interpretation_only",
    }
    assert "建议同时勾选" in response.json()["context_basis"]["warning"]
