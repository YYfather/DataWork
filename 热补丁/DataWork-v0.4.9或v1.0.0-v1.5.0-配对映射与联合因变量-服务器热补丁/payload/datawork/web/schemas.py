"""工作区 API 请求模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class WorkspaceAuthLogin(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PlanCreate(BaseModel):
    dataset_id: str
    name: str = Field(min_length=1, max_length=160)
    plan: dict[str, Any]


class PlanUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    plan: dict[str, Any]


class PlanClone(BaseModel):
    name: str | None = Field(default=None, max_length=160)


class DerivedPreviewRequest(BaseModel):
    derived_columns: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class ReportCreate(BaseModel):
    title: str = Field(default="统计分析报告", min_length=1, max_length=200)


class InstantReportCreate(BaseModel):
    execution: dict[str, Any]
    title: str = Field(default="统计分析报告", min_length=1, max_length=200)


class RunCompare(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=20)


class AISettingsUpdate(BaseModel):
    enabled: bool = False
    provider: str
    base_url: str
    model: str
    privacy_mode: str = "metadata_only"
    remember_key: bool = False
    secret_storage: str = "session"
    api_key: str | None = Field(default=None, max_length=4096)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=256, le=16384)
    allow_no_api_key: bool = False


class AIExplainRequest(BaseModel):
    step: str = Field(default="welcome", max_length=80)
    question: str = Field(default="", max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class AIAnalysisExplainRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=4000)
    use_ai: bool = True


class AIResultContextSelection(BaseModel):
    data_profile: bool = False
    analysis_plan: bool = False
    current_result: bool = True
    result_scope: Literal["normative_evidence", "full_result"] = "normative_evidence"
    include_ordering: bool = True
    ai_report: bool = False


class AIResultExplainRequest(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    selection: AIResultContextSelection = Field(default_factory=AIResultContextSelection)
    ai_report: dict[str, Any] | None = None
    result_context_id: str = Field(default="", max_length=200)
    ai_report_context_id: str = Field(default="", max_length=200)


class AIAssistantAskRequest(BaseModel):
    """小助手自由问答；上下文范围完全由界面选择器决定。"""

    question: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    selection: AIResultContextSelection = Field(default_factory=AIResultContextSelection)
    ai_report: dict[str, Any] | None = None
    result_context_id: str = Field(default="", max_length=200)
    ai_report_context_id: str = Field(default="", max_length=200)


class AIResultReportRequest(BaseModel):
    result: dict[str, Any]
    title: str = Field(default="AI 规范统计结果报告", min_length=1, max_length=200)
    use_ai: bool = True
    analysis_context: dict[str, Any] = Field(default_factory=dict)
