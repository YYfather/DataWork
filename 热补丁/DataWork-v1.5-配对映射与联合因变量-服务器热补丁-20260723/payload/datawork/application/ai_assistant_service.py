"""面向普通使用者的 AI 操作辅助服务。"""

from __future__ import annotations

import json
import math
from typing import Any

from pydantic import BaseModel, Field

from datawork.ai.guard import guard_ai_output
from datawork.ai.provider import create_provider
from datawork.ai.settings import AISettingsService, PrivacyMode
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.method_registry import get_method


STEP_GUIDES: dict[str, dict[str, Any]] = {
    "welcome": {
        "title": "开始使用 DataWork",
        "summary": "先导入数据，再确认变量角色和统计方法，最后执行分析并阅读结果。统计数值始终由本地统计引擎计算。",
        "actions": ["选择即时分析或项目工作区", "首次使用可先配置 AI，也可以完全不配置", "准备 CSV、TSV 或 XLSX 数据"],
        "cautions": ["AI 只负责解释，不会修改统计结果", "正式分析前应确认数据列含义"],
    },
    "import_data": {
        "title": "导入并检查数据",
        "summary": "程序会读取表格、识别列类型、统计缺失值和重复行，并为每列给出初步角色建议。",
        "actions": ["选择数据文件", "确认百分比按百分点还是比例读取", "点击“读取并检查数据”"],
        "cautions": ["37% 可解释为 37 或 0.37，两者会影响均值和模型系数", "自动推断只是建议，后续仍需人工确认"],
    },
    "data_quality": {
        "title": "理解数据质量检查",
        "summary": "行列数、缺失率和重复行用于判断数据是否完整；列级信息帮助识别因变量、分组因素和标识列。",
        "actions": ["检查缺失率是否异常", "确认重复行是否来自真实重复观测", "核对数值列和分类列是否识别正确"],
        "cautions": ["缺失值处理方式会改变有效样本量", "ID 列不应被当作连续因变量"],
    },
    "batch_workflow": {
        "title": "通用批量分析",
        "summary": "按用户选择的多个因变量、分类因素组合和拆分列建立多个任务，在每个任务执行完全相同的统计方法，最后合并为一个结果表。",
        "actions": [
            "选择需要重复执行的统计方法、因变量和分类因素候选池。",
            "需要组合实验时启用‘分类因素组合’，设置最高计算阶数 k 和跨组合 p 值校正。",
            "把仅用于区分批次的列加入‘批量拆分’，不要同时把它放入模型因素。",
            "执行前检查每个批次的样本量和因素水平，再确认运行。",
            "完成后下载仅包含通用合并结果的 XLSX。",
        ],
        "cautions": [
            "批量引擎不识别或假设任何特定列名、处理前缀、对照关系或领域语义。",
            "样本不足或模型不成立的批次会保留在合并表中，并记录失败原因。",
        ],
    },
    "build_plan": {
        "title": "建立分析计划",
        "summary": "分析计划明确要分析哪些因变量、哪些因素进入模型、是否拆分数据，以及采用哪种统计方法。",
        "actions": ["先选因变量", "再选固定因素", "仅在需要分层分析时选择拆分列", "查看“分析目的与预期效果”卡片"],
        "cautions": ["拆分列通常不能同时作为模型因素；专业模式有受控例外", "方法显示为“未实现”时程序不会偷偷改用其他方法"],
    },
    "choose_method": {
        "title": "选择统计方法",
        "summary": "方法应由数据结构和研究问题共同决定。程序会根据当前变量选择解释该方法究竟分析什么，以及运行后会输出什么。",
        "actions": ["选择方法", "确认因变量和因素", "阅读动态生成的分析目的", "确认预期输出符合研究问题"],
        "cautions": ["预期效果描述的是输出形式，不是提前断言显著或不显著", "应同时关注效应量和不确定性"],
    },
    "review_plan": {
        "title": "执行前确认",
        "summary": "此处展示最终模型结构、分析目的和预期效果。执行前请确认变量角色与研究问题一致。",
        "actions": ["检查模型结构", "确认变量没有选反", "确认预期输出能够回答研究问题"],
        "cautions": ["错误的变量角色会得到形式正确但含义错误的结果"],
    },
    "run_analysis": {
        "title": "执行统计分析",
        "summary": "点击执行后，统计引擎会校验计划、完成假设检验和效应量计算，并生成可复现元数据。",
        "actions": ["核对分析目的", "核对预期输出", "执行分析", "若报错，按结构化提示修正"],
        "cautions": ["程序不会把失败的方法静默替换成其他方法"],
    },
    "interpret_results": {
        "title": "阅读分析结果",
        "summary": "先确认分析实际输出是否与执行前的预期形式一致，再结合 p 值、效应量、置信区间和诊断警告解释。",
        "actions": ["先确认方法和模型", "查看总体检验", "查看效应量和区间", "阅读警告与事后比较"],
        "cautions": ["p>0.05 表示证据不足，不等于完全相同", "观察性数据不能据此断言因果"],
    },
    "workspace": {
        "title": "使用项目工作区",
        "summary": "项目工作区会保存原始数据、数据指纹、分析计划、运行记录和报告，适合长期研究。",
        "actions": ["创建项目", "上传数据集", "保存分析计划", "每次运行保留独立记录"],
        "cautions": ["源文件被替换后哈希校验会阻止复用旧结论", "API 密钥不会写入项目数据库"],
    },
    "report": {
        "title": "生成与使用报告",
        "summary": "报告包包含统计报告、规范化结果和可复现信息，可用于核查分析过程。",
        "actions": ["确认运行成功后生成报告", "保存 ZIP 报告包", "提交前人工复核 AI 解释"],
        "cautions": ["AI 表述属于辅助草稿，最终学术结论需由研究者负责"],
    },
    "ai_settings": {
        "title": "配置 AI 助手",
        "summary": "先填写服务商、API 地址和密钥，再测试连接。测试成功后程序自动拉取 Model ID，并等待你手动选择。",
        "actions": ["选择服务商", "填写 API 地址和密钥", "点击测试并拉取模型", "从列表中手动选择 Model ID", "确认保存并启用"],
        "cautions": ["不会自动选择第一个模型", "第三方 API 的费用和数据政策由相应服务商决定", "默认不发送原始数据行"],
    },
    "calibration": {
        "title": "理解校正（Calibration）",
        "summary": "校正是在正式建模前按明确规则调整数值特征，使不同数据源或批次处于可比较的尺度与基准空间。",
        "actions": ["确认系统误差或基准偏移的来源", "选择标准化、稳健标准化或基线中心化", "记录校正列、基准列与基准值", "比较校正前后的分布与模型诊断"],
        "cautions": ["校正不是为了制造显著性，不能替代数据质量控制", "基准组必须由研究设计预先定义，不能根据结果临时挑选"],
        "principle": "校正的目的，是消除仪器、批次或数据源引入的系统误差，对齐共同的基准特征空间（Baseline），并在极端值或分布漂移出现时避免算法产生持续性的预测偏移。标准化对齐均值与尺度；稳健标准化用中位数和 MAD 降低极值影响；基线中心化则以预先指定的基准组均值作为零点。",
    },
}


_STEP_PRINCIPLES = {
    "welcome": "DataWork 将确定性的统计计算与解释辅助分离：本地计算核心负责数值，助手只负责说明工作流与解释边界。",
    "import_data": "列类型、缺失结构与量纲会直接影响可用模型；先建立可追溯的数据画像，才能避免把格式问题误当成统计发现。",
    "data_quality": "质量检查关注数据生成过程是否与分析假设一致，而不只是寻找空值；重复、异常编码和角色误判都会改变有效样本与估计目标。",
    "batch_workflow": "批量分析把同一预注册计划应用到多个明确任务，并以统一字段聚合；最高阶数 k 表示完整生成 1 阶到 k 阶的全部因素组合。",
    "build_plan": "分析计划把研究问题映射为变量角色、模型结构和输出指标，是统计计算的可复现契约。",
    "choose_method": "方法选择取决于估计目标、变量尺度、依赖结构和模型假设，不能只依据结果是否显著。",
    "review_plan": "执行前审查用于阻止角色冲突和不可识别模型，避免在计算完成后才发现研究问题与模型不一致。",
    "run_analysis": "统计引擎只执行通过验证的显式计划；错误会被保留并报告，不会静默替换方法。",
    "interpret_results": "推断需要同时读取效应方向、大小、不确定性、校正后 p 值与诊断信息，单个阈值不能独立构成结论。",
    "workspace": "数据指纹、计划修订和运行记录共同构成可追溯链，使每份结果能回到其原始数据与参数。",
    "report": "规范报告让单次与批量结果共享字段定义，同时保留原始结果、过程信息与可复现元数据。",
    "ai_settings": "外部模型仅在用户明确进入“问 AI”工作流后读取允许的上下文；本步建议始终使用本地规则。",
}
for _step_name, _principle in _STEP_PRINCIPLES.items():
    STEP_GUIDES[_step_name]["principle"] = _principle


class StepExplanation(BaseModel):
    title: str
    purpose: str
    what_to_check: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    key_risk: str


class AnalysisGuidance(BaseModel):
    suitability_status: str = "needs_review"
    suitability_label: str = "需要核对"
    suitability_reason: str = ""
    analysis_purpose: str
    method_reason: str
    expected_outcome: str
    design_review_summary: str = ""
    design_checks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    data_basis: list[str] = Field(default_factory=list)
    checks_before_run: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class ResultGuidance(BaseModel):
    title: str
    summary: str
    findings: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class NormativeReportTable(BaseModel):
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class NormativeResultReport(BaseModel):
    title: str
    analysis_overview: list[str] = Field(default_factory=list)
    data_and_design: list[str] = Field(default_factory=list)
    descriptive_statistics: list[str] = Field(default_factory=list)
    assumption_review: list[str] = Field(default_factory=list)
    inferential_results: list[str] = Field(default_factory=list)
    follow_up_results: list[str] = Field(default_factory=list)
    effect_sizes_and_uncertainty: list[str] = Field(default_factory=list)
    ordered_comparisons: list[str] = Field(default_factory=list)
    conclusion: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    tables: list[NormativeReportTable] = Field(default_factory=list)


class AINormativeResultProse(BaseModel):
    """AI-owned prose only; deterministic ordering and tables are injected locally."""

    title: str
    analysis_overview: list[str] = Field(default_factory=list)
    data_and_design: list[str] = Field(default_factory=list)
    descriptive_statistics: list[str] = Field(default_factory=list)
    assumption_review: list[str] = Field(default_factory=list)
    inferential_results: list[str] = Field(default_factory=list)
    follow_up_results: list[str] = Field(default_factory=list)
    effect_sizes_and_uncertainty: list[str] = Field(default_factory=list)
    conclusion: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AIAssistantService:
    def __init__(self, settings: AISettingsService) -> None:
        self.settings_service = settings

    def builtin_help(self, step: str) -> dict[str, Any]:
        guide = STEP_GUIDES.get(step, STEP_GUIDES["welcome"])
        return {"step": step, "source": "builtin", **guide}

    async def test_connection(self) -> dict[str, Any]:
        """测试认证与模型端点，并返回全部可见 Model ID。"""

        settings = self.settings_service.load()
        config = self.settings_service.provider_config(require_model=False)
        provider = create_provider(config=config)
        if provider is None:
            raise DataWorkError(
                ErrorCode.AI_UNAVAILABLE, "AI 服务尚未配置", status_code=409
            )
        try:
            try:
                models = await provider.list_models()
            except Exception as exc:
                raise DataWorkError(
                    ErrorCode.AI_REQUEST_FAILED,
                    f"连接或模型发现失败：{exc}",
                    status_code=502,
                ) from exc
            if not models:
                raise DataWorkError(
                    ErrorCode.AI_REQUEST_FAILED,
                    "连接成功，但服务没有返回任何可用 Model ID。",
                    status_code=502,
                )
            available_ids = {item.id for item in models if item.selectable}
            previous_model = settings.model if settings.model in available_ids else ""
            return {
                "ok": True,
                "provider": settings.provider.value,
                "message": f"连接成功，共拉取到 {len(models)} 个 Model ID。请选择后再启用 AI。",
                "models": [item.to_dict() for item in models],
                "model_count": len(models),
                "selectable_count": len(available_ids),
                "previous_model": previous_model,
                "selected_model": "",
                "selection_required": True,
            }
        finally:
            await provider.close()

    async def explain_analysis_plan(
        self,
        context: dict[str, Any],
        *,
        question: str = "",
        use_ai: bool = True,
    ) -> dict[str, Any]:
        """解释当前数据与当前方法组合的分析目的和预期输出。"""

        deterministic = _deterministic_analysis_guidance(context)
        settings = self.settings_service.load()
        status = self.settings_service.public_status(settings)
        if not use_ai or not settings.enabled or not status["configured"]:
            return {
                "source": "builtin",
                "guidance": deterministic.model_dump(mode="json"),
                "setup_required": not status["configured"],
            }

        sanitized = _sanitize_context(
            context,
            include_preview=settings.privacy_mode == PrivacyMode.INCLUDE_PREVIEW,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是实验统计分析计划解释助手。必须严格围绕用户当前选择的数据列和统计方法。"
                    "先给出 suitability_status（suitable、conditional 或 needs_changes）、suitability_label 和 suitability_reason，"
                    "明确回答当前方法是否适合、是否需要修改；不能只复述方法原理。"
                    "analysis_purpose 要说明该方法在当前变量组合下具体分析什么问题；"
                    "expected_outcome 要说明运行后会得到什么形式的结果、指标和比较，"
                    "design_review_summary、design_checks 和 recommended_actions 必须审查样本重复、平衡性、缺失、模型复杂度与事后比较风险，"
                    "recommended_actions 要写成可以直接核对或修改的动作；alternatives 只列出与当前设计真正相关的替代方法及适用条件。"
                    "不得提前猜测显著性、方向或数值。method_reason 要解释为什么该方法适合当前结构。"
                    "语言面向非统计专业研究者，避免空泛表述，不要重复字段标题。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_context": sanitized,
                        "deterministic_reference": deterministic.model_dump(mode="json"),
                        "question": question.strip()
                        or "请解释当前分析方法为了分析什么，以及基于当前数据最后会得到什么形式的预期效果。",
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        return await self._generate_structured(
            messages,
            schema=AnalysisGuidance,
            fallback=deterministic,
            payload_key="guidance",
        )

    async def explain_step(
        self,
        step: str,
        *,
        context: dict[str, Any] | None = None,
        question: str = "",
    ) -> dict[str, Any]:
        context = context or {}
        if step in {"build_plan", "choose_method", "review_plan", "run_analysis"} and context.get("selected_method"):
            return await self.explain_analysis_plan(context, question=question)

        builtin = self.builtin_help(step)
        settings = self.settings_service.load()
        status = self.settings_service.public_status(settings)
        fallback = StepExplanation(
            title=builtin["title"],
            purpose=builtin["summary"],
            what_to_check=list(builtin.get("cautions", [])),
            next_actions=list(builtin.get("actions", [])),
            key_risk=(builtin.get("cautions") or ["请人工核对当前选择。"])[0],
        )
        if not settings.enabled or not status["configured"]:
            return {
                "source": "builtin",
                "explanation": fallback.model_dump(mode="json"),
                "setup_required": not status["configured"],
            }

        sanitized = _sanitize_context(
            context,
            include_preview=settings.privacy_mode == PrivacyMode.INCLUDE_PREVIEW,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DataWork 操作向导。根据当前步骤和上下文，用结构化、简短、"
                    "面向非统计专业用户的中文解释目的、检查项、下一步和最重要风险。"
                    "不得编造统计结果，不得替代统计引擎选择方法。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "step": step,
                        "builtin_guide": builtin,
                        "context": sanitized,
                        "question": question.strip()
                        or "请解释当前步骤以及我接下来应该做什么。",
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        return await self._generate_structured(
            messages,
            schema=StepExplanation,
            fallback=fallback,
            payload_key="explanation",
        )

    async def ask(
        self,
        *,
        question: str,
        context: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        selection: dict[str, Any] | None = None,
        ai_report: dict[str, Any] | None = None,
        result_context_id: str = "",
        ai_report_context_id: str = "",
    ) -> dict[str, Any]:
        """按用户选择的依据进行自由问答，直接返回 Markdown 正文。"""

        assistant_context = context if isinstance(context, dict) else {}
        result_payload = result if isinstance(result, dict) else {}
        selected = _normalize_result_context_selection(selection)
        selected["current_result"] = bool(selected["current_result"] and result_payload)
        report_prose, report_issue = _assistant_ai_report_prose(
            ai_report,
            requested=selected["ai_report"],
            result_context_id=result_context_id,
            ai_report_context_id=ai_report_context_id,
        )
        basis = _assistant_context_basis(selected, report_prose, report_issue)

        selected_context: dict[str, Any] = {}
        if selected["data_profile"] and assistant_context.get("data_profile"):
            selected_context["data_profile"] = _sanitize_context(
                assistant_context.get("data_profile"), include_preview=False
            )
        if selected["analysis_plan"]:
            selected_context["analysis_plan"] = _assistant_analysis_plan_context(
                assistant_context
            )
        if selected["current_result"]:
            normative = _deterministic_normative_report(
                result_payload, title="AI 小助手规范化证据"
            )
            evidence = _build_ai_report_evidence_packet(
                normative,
                _assistant_normative_evidence_context(
                    assistant_context, result_payload
                ),
                result=result_payload,
                include_preview=False,
            )
            if not selected["include_ordering"]:
                evidence.pop("read_only_ordering", None)
            selected_context["normative_evidence"] = evidence
            if selected["result_scope"] == "full_result":
                selected_context["full_result_and_diagnostics"] = (
                    _assistant_full_result_diagnostics(result_payload)
                )
        if report_prose is not None:
            selected_context["ai_generated_report"] = report_prose

        workflow = {
            "mode": assistant_context.get("mode"),
            "workflow_step": assistant_context.get("workflow_step"),
            "workflow_progress": assistant_context.get("workflow_progress"),
        }
        settings = self.settings_service.load()
        status = self.settings_service.public_status(settings)
        if not settings.enabled or not status["configured"]:
            return {
                "source": "builtin",
                "answer_markdown": "AI 尚未启用或配置完成，请先打开 **AI 设置**。",
                "setup_required": not status["configured"],
                "context_basis": basis,
            }

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 DataWork 中的自由问答助手。只使用 selected_context 中由用户明确选择的资料回答；"
                    "workflow 只用于理解用户目前所在阶段，不能用它补充未选择的数据、计划或结果。"
                    "直接回答用户实际提出的问题，篇幅与问题相称。不要自动总结整份资料，不要固定输出‘核心发现’、"
                    "‘下一步’或其他模板栏目，也不要把证据逐行改写成清单；只有问题确实需要时才使用标题、列表或表格。"
                    "不得编造统计数值；AI 生成的文字报告属于辅助材料，若与统计结果证据冲突，以统计结果证据为准。"
                    "使用简洁、可直接显示的中文 Markdown 返回正文，不要用 JSON，也不要在全文外包裹 Markdown 代码围栏。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question.strip(),
                        "workflow": workflow,
                        "selected_context": selected_context,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        try:
            config = self.settings_service.provider_config()
            provider = create_provider(config=config)
            if provider is None:
                return {
                    "source": "builtin",
                    "answer_markdown": "AI 服务当前不可用，请检查 **AI 设置**。",
                    "warning": "AI 服务不可用。",
                    "context_basis": basis,
                }
            try:
                response = await provider.generate_text(messages)
                if response.error or not response.content.strip():
                    response = await provider.generate_text([
                        *messages,
                        {
                            "role": "system",
                            "content": "上一次回答为空。请只返回针对用户问题的简洁 Markdown 正文。",
                        },
                    ])
            finally:
                await provider.close()
            if response.error or not response.content.strip():
                return {
                    "source": "builtin",
                    "answer_markdown": "这次没有收到有效的 AI 回答，请稍后重试。",
                    "warning": response.error or "AI 返回了空内容。",
                    "context_basis": basis,
                }
            return {
                "source": "ai",
                "answer_markdown": _clean_markdown_response(response.content),
                "provider": settings.provider.value,
                "model": response.model or settings.model,
                "usage": response.usage,
                "cost_usd_estimate": response.cost_usd,
                "context_basis": basis,
            }
        except DataWorkError as exc:
            return {
                "source": "builtin",
                "answer_markdown": "AI 请求未能完成，请检查 **AI 设置** 后重试。",
                "warning": exc.message,
                "setup_required": True,
                "context_basis": basis,
            }
        except Exception as exc:
            return {
                "source": "builtin",
                "answer_markdown": "AI 请求未能完成，请稍后重试。",
                "warning": f"AI 请求失败：{exc}",
                "context_basis": basis,
            }

    async def explain_result(
        self,
        result: dict[str, Any],
        *,
        question: str = "",
        context: dict[str, Any] | None = None,
        selection: dict[str, Any] | None = None,
        ai_report: dict[str, Any] | None = None,
        result_context_id: str = "",
        ai_report_context_id: str = "",
    ) -> dict[str, Any]:
        deterministic = _deterministic_result_help(result)
        selected = _normalize_result_context_selection(selection)
        report_prose, report_issue = _assistant_ai_report_prose(
            ai_report,
            requested=selected["ai_report"],
            result_context_id=result_context_id,
            ai_report_context_id=ai_report_context_id,
        )
        basis = _assistant_context_basis(selected, report_prose, report_issue)
        fallback_guidance = _assistant_result_fallback(deterministic, selected)
        settings = self.settings_service.load()
        status = self.settings_service.public_status(settings)
        if not settings.enabled or not status["configured"]:
            return {
                "source": "builtin",
                "result_guidance": fallback_guidance.model_dump(mode="json"),
                "setup_required": not status["configured"],
                "context_basis": basis,
            }

        assistant_context = context if isinstance(context, dict) else {}
        selected_context: dict[str, Any] = {}
        if selected["data_profile"]:
            selected_context["data_profile"] = _sanitize_context(
                assistant_context.get("data_profile", {}), include_preview=False
            )
        if selected["analysis_plan"]:
            selected_context["analysis_plan"] = _assistant_analysis_plan_context(
                assistant_context
            )
        if selected["current_result"]:
            normative = _deterministic_normative_report(
                result, title="AI 小助手规范化证据"
            )
            normative_evidence = _build_ai_report_evidence_packet(
                normative,
                _assistant_normative_evidence_context(assistant_context, result),
                result=result,
                include_preview=False,
            )
            if not selected["include_ordering"]:
                normative_evidence.pop("read_only_ordering", None)
            selected_context["normative_evidence"] = normative_evidence
            if selected["result_scope"] == "full_result":
                selected_context["full_result_and_diagnostics"] = (
                    _assistant_full_result_diagnostics(result)
                )
        if report_prose is not None:
            selected_context["ai_generated_report_for_interpretation_only"] = report_prose

        canonical = json.dumps(result, ensure_ascii=False, default=str)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是统计结果阅读助手。只能使用 selected_context 中明确提供的内容回答。"
                    "未被选择的上下文视为不存在，不得猜测或补全。"
                    "不得修改、补造或猜测 F、p、自由度、效应量、均值或置信区间。"
                    "p>0.05 应写为证据不足，不能写成完全没有差异。"
                    "证据冲突时必须依次服从：full_result_and_diagnostics、normative_evidence、"
                    "ai_generated_report_for_interpretation_only、用户文字。AI 报告只用于辅助理解，不能作为统计事实来源。"
                    "必须直接回答用户的问题，优先提炼跨任务、跨条件或组别间的稳定规律，说明例外与边界；"
                    "不要把证据表逐行改写成冗长清单。若规范证据包含组别排序，涉及组别相对位置时优先使用其中的 A > B > C 式排序，"
                    "不得只说某组最高或最低，并须区分估计值顺序与校正后显著差异。"
                    "输出结构化字段，便于界面分区展示。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question.strip()
                        or "请帮我用通俗中文读懂这些结果。",
                        "selected_context": selected_context,
                        "context_contract": {
                            "result_scope": selected["result_scope"],
                            "include_ordering": selected["include_ordering"],
                            "raw_rows_sent": False,
                            "ai_report_is_explanatory_only": True,
                        },
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        generated = await self._generate_structured(
            messages,
            schema=ResultGuidance,
            fallback=fallback_guidance,
            payload_key="result_guidance",
        )
        ordered = _ordered_comparisons_from_result(result)
        if ordered and selected["current_result"] and selected["include_ordering"]:
            findings = list(generated.get("result_guidance", {}).get("findings", []) or [])
            generated["result_guidance"]["findings"] = list(dict.fromkeys([*ordered, *findings]))
        generated["context_basis"] = basis
        if generated.get("source") != "ai":
            return generated
        guard_text = json.dumps(
            generated["result_guidance"], ensure_ascii=False, default=str
        )
        guard = guard_ai_output(guard_text, result_json=canonical)
        generated["guard"] = guard
        if not guard["passed"]:
            return {
                "source": "builtin_guard_fallback",
                "result_guidance": fallback_guidance.model_dump(mode="json"),
                "warning": "AI 输出未通过数值一致性检查，已改用程序生成的保守解释。",
                "guard": guard,
                "context_basis": basis,
            }
        return generated

    async def generate_result_report(
        self,
        result: dict[str, Any],
        *,
        title: str = "AI 规范统计结果报告",
        use_ai: bool = True,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """先返回本地排序与三表；可选地让 AI 仅撰写受守卫的文字总结。"""

        deterministic = _deterministic_normative_report(result, title=title)
        local_evidence = _evidence_only_normative_report(deterministic)
        local_evidence_summary = _local_report_evidence_summary(result, deterministic)
        if not use_ai:
            return {
                "source": "builtin",
                "report": local_evidence.model_dump(mode="json"),
                "report_markdown": _render_normative_evidence_report(local_evidence),
                "report_control": _report_control_metadata(),
                "evidence_summary": local_evidence_summary,
                "warning": "当前页仅包含本地统计内核生成的只读排序和三张规范表；AI 文字总结通过独立请求生成，成功后在第二页显示。",
            }
        settings = self.settings_service.load()
        status = self.settings_service.public_status(settings)
        if not settings.enabled or not status["configured"]:
            return {
                "source": "builtin",
                "report": local_evidence.model_dump(mode="json"),
                "report_markdown": _render_normative_evidence_report(local_evidence),
                "report_control": _report_control_metadata(),
                "evidence_summary": local_evidence_summary,
                "setup_required": not status["configured"],
                "warning": "AI 未启用或尚未完成配置；本地排序和三张规范表不受影响。",
            }

        include_preview = settings.privacy_mode is PrivacyMode.INCLUDE_PREVIEW
        evidence_packet = _build_ai_report_evidence_packet(
            deterministic,
            analysis_context or {},
            result=result,
            include_preview=include_preview,
        )
        evidence_summary = _ai_report_evidence_summary(
            evidence_packet,
            privacy_mode=settings.privacy_mode.value,
        )
        # 外部模型只读取受限证据包；本地守卫还可读取完整计算结果，以校验所有
        # 数值型标签和统计值的可追溯性，但完整结果不会因此发送给模型。
        guard_source = json.dumps(
            {
                "canonical_result": result,
                "ai_evidence_packet": evidence_packet,
            },
            ensure_ascii=False,
            default=str,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是严谨的中文统计报告撰写助手。只能使用用户消息中的 ai_evidence_packet，"
                    "不得使用外部知识补造统计事实，也不得重新计算、修改或补全本地统计结果。"
                    "三张规范表与 assumption_checks 是统计结论的唯一数值依据；有限的数据预览只用于理解列和标签语境，"
                    "不能覆盖表格结果、重新计算 p 值或产生表中不存在的统计结论。"
                    "不得补造、修改或推算未提供的均值、标准差、自由度、统计量、p 值、效应量或置信区间。"
                    "你的核心任务是沿统计证据链提炼规律，而不是转录统计表。"
                    "证据链依次为：研究设计与任务范围、父级/总体检验及校正结论、条件性效应与后续比较、本地只读排序、效应量、前提检验与解释边界。"
                    "先识别跨任务反复出现的稳定规律，再识别只在特定因变量、时间、批次或因素条件下出现的条件性规律和例外；"
                    "随后判断效应方向是否一致、排序是否稳定、效应量是否支持实际重要性，并说明前提检验对可信度的影响。"
                    "每节先写归纳结论，再用表号、少量代表性统计量或本地只读排序说明证据来源；完整逐项数值留在规范表中。"
                    "报告结构采用：目的与方法、描述性规律、前提检验综合判断、推断规律、后续比较规律、结论与边界。"
                    "报告必须按参照格式引用三张本地规范表：描述性统计见表1，总体/多变量检验及效应量见表2，单变量与后续检验见表3。"
                    "前提检验依据 assumption_checks 中的检验名称、统计量、p 值、判断与备注进行综合判断；优先概括整体满足情况，只单独指出需要关注的例外；"
                    "只有 assumption_checks 为空时，才可以说明未提供可计算的前提检验。"
                    "正文必须是可直接使用的统计结果报告，不写统计学教程、操作步骤或泛泛建议。"
                    "当证据包表示批量结果时，以规律为组织单位，而不是以任务为组织单位：概括哪些因素持续相关、哪些影响随条件改变、哪些方向具有一致性以及哪些结果构成例外。"
                    "描述性部分概括中心趋势、离散程度和排序模式；推断部分概括显著模式、非显著交互与校正口径；"
                    "后续比较概括有解释价值的方向和层级；效应量部分概括实际重要性的整体范围与异质性。"
                    "规范表承担逐任务 M、SD、n、p 值、效应量和两两比较的完整陈列，正文不重复承担数据清单功能。"
                    "不得在最终报告中出现 read_only_ordering、ordered_comparisons、ai_evidence_packet、normative_tables、canonical_result 等内部 JSON 字段名；"
                    "只能写成人类可读的‘本地只读排序’、‘规范表’或‘原始统计结果’。"
                    "叙述顺序必须与证据链一致：先说明设计与描述性规律，再综合前提检验，随后归纳推断规律、方向模式和具体差异。"
                    "析因模型的推断段落必须先报告最高阶交互，再按阶数递减报告低阶交互，最后报告主效应。"
                    "显著交互存在时，先说明该交互，再解释简单效应；三阶或更高阶交互显著时，应报告固定其他因素后的简单简单效应。"
                    "不能脱离显著交互直接概括受影响的主效应，也不能把边际均值顺序写成条件内显著差异；"
                    "相关交互均不显著时，才逐一解释主效应，并把相应事后比较紧跟在该主效应之后。"
                    "主效应显著且因素有三个及以上水平时才报告相应事后多重比较；两个水平只报告方向，不虚构额外事后检验。"
                    "MANOVA 必须先报告预先指定的整体多变量判据，再报告经校正的单变量跟进，最后才进入显著因变量的简单效应或事后比较。"
                    "多重比较优先使用校正后 p 值，并写明校正方法。p>=alpha 只能表述为证据不足或未达到显著，不能写成完全相同。"
                    "涉及组别相对位置时，必须逐字使用证据包内只读排序字段给出的 A > B > C 式排序；"
                    "该排序为只读证据，禁止重排、删改，也不得把描述性大小顺序冒充显著差异。"
                    "所有阿拉伯数字都必须逐字来自 ai_evidence_packet；"
                    "不要自行概括出新的计数，也不要给叙述段落添加阿拉伯数字编号。"
                    "仅在结果中存在时报告效应量和置信区间；显著性与实际重要性必须区分。"
                    "结论不得把观察性关联写成因果，不得引用外部资料，不得复制示例中的虚构数字。"
                    "每个字段写成可直接进入正式报告的简洁中文段落。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": title,
                        "ai_evidence_packet": evidence_packet,
                        "synthesis_objective": "沿证据链归纳跨任务稳定规律、条件性规律、方向一致性、例外与解释边界，不逐行转录表格。",
                        "evidence_chain": [
                            "研究设计、统计方法与任务范围",
                            "描述性趋势、离散程度与组别排序模式",
                            "前提检验的整体满足情况与需关注例外",
                            "父级/总体检验、交互层级与跨任务校正结论",
                            "简单效应、事后比较和本地只读排序共同支持的方向规律",
                            "效应量所反映的实际重要性、异质性与不确定性",
                            "可推广结论、条件限制与观察性解释边界",
                        ],
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        prose_fallback = AINormativeResultProse(title=title)
        generated = await self._generate_structured(
            messages,
            schema=AINormativeResultProse,
            fallback=prose_fallback,
            payload_key="report",
        )
        generated["report_control"] = _report_control_metadata()
        generated["evidence_summary"] = evidence_summary
        # 排序由本地结果确定性生成，AI 只能解释，不能改写组别次序。
        generated["report"]["ordered_comparisons"] = deterministic.ordered_comparisons
        # 表格必须逐值来自计算核心，不能交由模型重写或补造。
        generated["report"]["tables"] = [
            table.model_dump(mode="json") for table in deterministic.tables
        ]
        _normalize_ai_report_language(generated["report"])
        report = NormativeResultReport.model_validate(generated["report"])
        generated["report_markdown"] = (
            _render_normative_report(report)
            if generated.get("source") == "ai"
            else _render_normative_evidence_report(local_evidence)
        )
        if generated.get("source") != "ai":
            generated["report"] = local_evidence.model_dump(mode="json")
            generated.setdefault("warning", "AI 未返回可应用的文字总结；本地排序和三张规范表仍可正常使用。")
            return generated

        # 只审计 AI 能改写的叙述字段。本地引擎随后覆盖的排序、规范表格及其
        # “表1/表2”编号均为确定性内容，不能反过来造成 AI 数值守卫误报。
        guard_text = _ai_authored_report_guard_text(report)
        guard = (
            guard_ai_output(guard_text, result_json=guard_source, strict_numeric=True)
            if guard_text.strip()
            else {
                "passed": False,
                "violations": ["AI 未返回任何可应用的文字总结。"],
                "warnings": [],
            }
        )
        generated["guard"] = guard
        if not guard["passed"]:
            repair_messages = [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "上一次报告未通过统计数值一致性检查。请只根据 ai_evidence_packet "
                        "完整重写报告；只能原样使用其中已有数值，"
                        "允许常规小数舍入、百分数换算和显著性阈值表达，不得引入其他数值。"
                        "需要纠正的问题："
                        + json.dumps(guard.get("violations", [])[:8], ensure_ascii=False)
                    ),
                },
            ]
            repaired = await self._generate_structured(
                repair_messages,
                schema=AINormativeResultProse,
                fallback=prose_fallback,
                payload_key="report",
            )
            repaired["report_control"] = _report_control_metadata()
            repaired["evidence_summary"] = evidence_summary
            repaired["report"]["ordered_comparisons"] = deterministic.ordered_comparisons
            repaired["report"]["tables"] = [
                table.model_dump(mode="json") for table in deterministic.tables
            ]
            _normalize_ai_report_language(repaired["report"])
            repaired_report = NormativeResultReport.model_validate(repaired["report"])
            repaired_markdown = _render_normative_report(repaired_report)
            repaired["report_markdown"] = repaired_markdown
            if repaired.get("source") == "ai":
                repaired_guard_text = _ai_authored_report_guard_text(repaired_report)
                repaired_guard = (
                    guard_ai_output(
                        repaired_guard_text,
                        result_json=guard_source,
                        strict_numeric=True,
                    )
                    if repaired_guard_text.strip()
                    else {
                        "passed": False,
                        "violations": ["AI 未返回任何可应用的文字总结。"],
                        "warnings": [],
                    }
                )
                repaired["guard"] = repaired_guard
                if repaired_guard["passed"]:
                    removed = _enforce_deterministic_report_controls(
                        repaired["report"], deterministic, allow_prose_fallback=False
                    )
                    repaired_report = NormativeResultReport.model_validate(repaired["report"])
                    repaired["report_markdown"] = _render_normative_report(repaired_report)
                    repaired["guard_repaired"] = True
                    if removed:
                        repaired["source"] = "ai_guard_partial"
                        repaired["guard_replaced_sections"] = removed
                        repaired["warning"] = "AI 文字中不符合本地推断层级的章节已移除：" + "、".join(removed) + "。"
                    return repaired
                (
                    partially_guarded_report,
                    replaced_sections,
                    kept_sections,
                    filtered_guard,
                ) = _replace_unsafe_ai_report_sections(
                    repaired_report,
                    deterministic,
                    guard_source,
                )
                if replaced_sections and kept_sections:
                    partially_guarded_payload = partially_guarded_report.model_dump(mode="json")
                    hierarchy_removed = _enforce_deterministic_report_controls(
                        partially_guarded_payload,
                        deterministic,
                        allow_prose_fallback=False,
                    )
                    partially_guarded_report = NormativeResultReport.model_validate(
                        partially_guarded_payload
                    )
                    if not _ai_authored_report_guard_text(partially_guarded_report).strip():
                        return _ai_report_guard_failure_response(
                            local_evidence,
                            evidence_summary,
                            repaired.get("guard", guard),
                            initial_guard=guard,
                        )
                    repaired["source"] = "ai_guard_partial"
                    repaired["report"] = partially_guarded_report.model_dump(mode="json")
                    repaired["report_markdown"] = _render_normative_report(
                        partially_guarded_report
                    )
                    repaired["warning"] = (
                        "AI 文字中未通过数值一致性或推断层级检查的章节已移除："
                        + "、".join(list(dict.fromkeys([*replaced_sections, *hierarchy_removed])))
                        + "。其余通过检查的 AI 文字已保留。"
                    )
                    repaired["guard"] = {
                        "passed": True,
                        "violations": [],
                        "warnings": ["未通过检查的 AI 章节已移除；未使用内置文字回填。"],
                    }
                    repaired["guard_filtered"] = filtered_guard
                    repaired["guard_initial"] = guard
                    repaired["guard_replaced_sections"] = list(dict.fromkeys([*replaced_sections, *hierarchy_removed]))
                    repaired["guard_kept_sections"] = kept_sections
                    repaired["guard_attempts"] = 2
                    return repaired
            return _ai_report_guard_failure_response(
                local_evidence,
                evidence_summary,
                repaired.get("guard", guard),
                initial_guard=guard,
            )
        removed = _enforce_deterministic_report_controls(
            generated["report"], deterministic, allow_prose_fallback=False
        )
        report = NormativeResultReport.model_validate(generated["report"])
        generated["report_markdown"] = _render_normative_report(report)
        if removed:
            generated["source"] = "ai_guard_partial"
            generated["guard_replaced_sections"] = removed
            generated["warning"] = "AI 文字中不符合本地推断层级的章节已移除：" + "、".join(removed) + "。"
        return generated

    async def _generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[BaseModel],
        fallback: BaseModel,
        payload_key: str,
    ) -> dict[str, Any]:
        try:
            settings = self.settings_service.load()
            config = self.settings_service.provider_config()
            provider = create_provider(config=config)
            if provider is None:
                return {
                    "source": "builtin",
                    payload_key: fallback.model_dump(mode="json"),
                    "warning": "AI 服务不可用。",
                }
            try:
                structured_max_tokens = (
                    max(config.max_tokens, 8192)
                    if schema in {NormativeResultReport, AINormativeResultProse}
                    else config.max_tokens
                )
                response = await provider.generate_structured(
                    messages,
                    schema,
                    max_tokens=structured_max_tokens,
                )
                if response.error or response.parsed is None:
                    retry_messages = [
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "上一次响应为空或未符合结构要求。请重新返回完整的结构化内容，"
                                "不要使用 Markdown 代码块，也不要省略必填字段。"
                            ),
                        },
                    ]
                    response = await provider.generate_structured(
                        retry_messages,
                        schema,
                        max_tokens=structured_max_tokens,
                    )
            finally:
                await provider.close()
            if response.error or response.parsed is None:
                warning = (
                    _ai_report_structure_failure_warning(response.error)
                    if payload_key == "report"
                    else "AI 连续两次未返回可应用的结构化内容。"
                )
                return {
                    "source": "builtin",
                    payload_key: fallback.model_dump(mode="json"),
                    "warning": warning,
                }
            return {
                "source": "ai",
                payload_key: response.parsed.model_dump(mode="json"),
                "provider": settings.provider.value,
                "model": response.model or settings.model,
                "usage": response.usage,
                "cost_usd_estimate": response.cost_usd,
            }
        except DataWorkError as exc:
            return {
                "source": "builtin",
                payload_key: fallback.model_dump(mode="json"),
                "warning": exc.message,
                "setup_required": True,
            }
        except Exception as exc:
            return {
                "source": "builtin",
                payload_key: fallback.model_dump(mode="json"),
                "warning": f"AI 请求失败：{exc}",
            }


def _clean_markdown_response(content: str) -> str:
    """移除模型偶尔包在整段回答外层的 Markdown 代码围栏。"""

    text = content.strip()
    lowered = text.lower()
    if lowered.startswith("```markdown") and text.endswith("```"):
        return text[len("```markdown"): -3].strip()
    if text.startswith("```") and text.endswith("```"):
        return text[3:-3].strip()
    return text


def _sanitize_context(value: Any, *, include_preview: bool, depth: int = 0) -> Any:
    if depth > 6:
        return "[已截断]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:80]:
            key = str(raw_key)
            lowered = key.lower()
            if any(
                token in lowered
                for token in ("api_key", "secret", "password", "token", "authorization")
            ):
                continue
            preview_keys = {
                "preview",
                "data_preview",
                "sample_rows",
                "records",
                "raw_data",
                "raw_rows",
            }
            if not include_preview and (
                lowered in preview_keys or lowered.endswith("_preview")
            ):
                result[key] = "[隐私模式已省略原始数据预览]"
                continue
            result[key] = _sanitize_context(
                item, include_preview=include_preview, depth=depth + 1
            )
        return result
    if isinstance(value, (list, tuple)):
        limit = 5 if include_preview else 20
        return [
            _sanitize_context(item, include_preview=include_preview, depth=depth + 1)
            for item in list(value)[:limit]
        ]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def _sanitize_complete_report_context(value: Any, *, include_preview: bool) -> Any:
    """清洗报告上下文，但完整保留统计结果的列表、字段、层级和文本。"""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(
                token in lowered
                for token in ("api_key", "secret", "password", "token", "authorization")
            ):
                continue
            preview_keys = {
                "preview",
                "data_preview",
                "sample_rows",
                "records",
                "raw_data",
                "raw_rows",
            }
            if not include_preview and (
                lowered in preview_keys or lowered.endswith("_preview")
            ):
                result[key] = "[隐私模式已省略原始数据预览]"
                continue
            result[key] = _sanitize_complete_report_context(
                item, include_preview=include_preview
            )
        return result
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_complete_report_context(item, include_preview=include_preview)
            for item in value
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_result_context_selection(
    selection: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = selection if isinstance(selection, dict) else {}
    scope = str(raw.get("result_scope") or "normative_evidence")
    if scope not in {"normative_evidence", "full_result"}:
        scope = "normative_evidence"
    return {
        "data_profile": bool(raw.get("data_profile", False)),
        "analysis_plan": bool(raw.get("analysis_plan", False)),
        "current_result": bool(raw.get("current_result", True)),
        "result_scope": scope,
        "include_ordering": bool(raw.get("include_ordering", True)),
        "ai_report": bool(raw.get("ai_report", False)),
    }


def _assistant_analysis_plan_context(context: dict[str, Any]) -> dict[str, Any]:
    """Map the live UI plan to a compact, explicit assistant evidence block."""

    roles = {
        "dependent_variables": context.get("dependent_variables", []),
        "fixed_factors": context.get("fixed_factors", []),
        "covariates": context.get("covariates", []),
        "random_factors": context.get("random_factors", []),
        "random_slopes": context.get("random_slopes", []),
        "subject_id": context.get("subject_id", ""),
        "repeated_factor": context.get("repeated_factor", ""),
        "split_by": context.get("split_by", []),
    }
    settings_keys = (
        "estimate_marginal_means",
        "emm_factors",
        "method_parameters",
        "factor_combinations_enabled",
        "factor_combination_min_order",
        "factor_combination_max_order",
        "factor_combination_labels",
        "combination_p_adjust",
        "calibration_enabled",
        "calibration_method",
        "calibration_columns",
        "alpha",
        "ss_type",
    )
    return _sanitize_complete_report_context(
        {
            "method": {
                "name": context.get("selected_method", ""),
                "label": context.get("selected_method_label", ""),
            },
            "data_roles": roles,
            "analysis_settings": {
                key: context.get(key) for key in settings_keys if key in context
            },
        },
        include_preview=False,
    )


def _assistant_normative_evidence_context(
    context: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Supply only the role/profile metadata required to interpret normative tables."""

    plan = _assistant_analysis_plan_context(context)
    return {
        "execution_kind": str(result.get("kind") or "single"),
        "method": plan.get("method", {}),
        "data_roles": plan.get("data_roles", {}),
        "analysis_settings": plan.get("analysis_settings", {}),
        "data_profile": context.get("data_profile", {}),
        "data_preview": [],
    }


_ASSISTANT_DIAGNOSTIC_KEY_TOKENS = (
    "assumption",
    "diagnostic",
    "warning",
    "sphericity",
    "coefficient",
    "model_fit",
    "fit_statistics",
    "convergence",
    "residual",
    "provenance",
    "reproducibility",
    "software",
    "failure",
    "error",
    "aic",
    "bic",
    "r_squared",
)


def _extract_assistant_diagnostics(value: Any) -> Any:
    if isinstance(value, dict):
        extracted: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(token in lowered for token in _ASSISTANT_DIAGNOSTIC_KEY_TOKENS):
                extracted[key] = _sanitize_complete_report_context(
                    item, include_preview=False
                )
                continue
            nested = _extract_assistant_diagnostics(item)
            if nested not in ({}, [], None):
                extracted[key] = nested
        return extracted
    if isinstance(value, (list, tuple)):
        items = [_extract_assistant_diagnostics(item) for item in value]
        return [item for item in items if item not in ({}, [], None)]
    return None


def _assistant_full_result_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    """Add non-tabular diagnostics without duplicating the three normative tables."""

    diagnostics = _extract_assistant_diagnostics(result)
    return {
        "scope": (
            "在规范化证据之外补充模型拟合、前提检验、警告、球形性、系数、"
            "可复现信息与批任务失败；不替代规范表。"
        ),
        "details": diagnostics if isinstance(diagnostics, dict) else {},
    }


def _assistant_ai_report_prose(
    ai_report: dict[str, Any] | None,
    *,
    requested: bool,
    result_context_id: str,
    ai_report_context_id: str,
) -> tuple[dict[str, Any] | None, str]:
    if not requested:
        return None, ""
    if not result_context_id or result_context_id != ai_report_context_id:
        return None, "AI 文字报告不属于当前分析运行，已从本次上下文中排除。"
    payload = ai_report if isinstance(ai_report, dict) else {}
    if str(payload.get("source") or "") not in {"ai", "ai_guard_partial"}:
        return None, "当前运行尚无可用的 AI 文字报告，已从本次上下文中排除。"
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    prose_keys = (
        "title",
        "analysis_overview",
        "data_and_design",
        "descriptive_statistics",
        "assumption_review",
        "inferential_results",
        "follow_up_results",
        "effect_sizes_and_uncertainty",
        "conclusion",
        "limitations",
    )
    prose = {key: report.get(key) for key in prose_keys if report.get(key)}
    if not prose:
        return None, "AI 文字报告没有可供解释的正文，已从本次上下文中排除。"
    return _sanitize_complete_report_context(prose, include_preview=False), ""


def _assistant_context_basis(
    selected: dict[str, Any],
    report_prose: dict[str, Any] | None,
    report_issue: str,
) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    if selected["data_profile"]:
        items.append({"key": "data_profile", "label": "数据画像"})
    if selected["analysis_plan"]:
        items.append({"key": "analysis_plan", "label": "分析计划"})
    if selected["current_result"]:
        scope_label = (
            "完整结果与诊断"
            if selected["result_scope"] == "full_result"
            else "规范化证据"
        )
        items.append({
            "key": "current_result",
            "label": f"当前分析结果 · {scope_label}",
        })
        if selected["include_ordering"]:
            items.append({"key": "read_only_ordering", "label": "组别排序（A > B > C）"})
    if report_prose is not None:
        items.append({"key": "ai_report", "label": "AI 生成的文字报告（仅辅助理解）"})

    warnings: list[str] = []
    if report_issue:
        warnings.append(report_issue)
    if selected["ai_report"] and not selected["current_result"]:
        warnings.append("当前仅选择了 AI 文字报告；建议同时勾选“当前分析结果 · 规范化证据”以核对统计事实。")
    if not selected["current_result"] and report_prose is None:
        warnings.append("本次未选择统计结果证据，回答不会据此陈述具体统计结论。")
    return {
        "items": items,
        "raw_rows_sent": False,
        "warning": " ".join(dict.fromkeys(warnings)),
    }


def _assistant_result_fallback(
    deterministic: ResultGuidance, selected: dict[str, Any]
) -> ResultGuidance:
    if selected["current_result"]:
        return deterministic
    return ResultGuidance(
        title="本次未读取统计结果证据",
        summary="当前上下文未包含规范化证据或完整结果，内置回退不会展示具体统计数值。",
        findings=[],
        next_checks=["勾选“当前分析结果”，并优先使用默认的“规范化证据”后重新提问。"],
        cautions=["AI 文字报告只能辅助理解，不能单独作为统计事实来源。"],
    )


def _iter_statistical_evidence(
    result: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return every successful statistical result with stable task metadata."""

    payload = result.get("result", result)
    if result.get("kind") == "batch" or payload.get("results") or payload.get("tasks"):
        items: list[tuple[dict[str, Any], dict[str, Any]]] = []
        tasks = list(payload.get("results", []) or payload.get("tasks", []) or [])
        for index, task in enumerate(tasks, start=1):
            statistical = task.get("result")
            if task.get("error") or not isinstance(statistical, dict):
                continue
            info = dict(task.get("subset_info", {}) or {})
            items.append(({
                "task_id": info.get("task_id", index),
                "task_context": str(task.get("subset_key") or ""),
            }, dict(statistical)))
        return items
    statistical = payload.get("result", payload)
    return [({}, dict(statistical))] if isinstance(statistical, dict) else []


def _assumption_rows_for_statistical(
    statistical: dict[str, Any], *, task_meta: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Normalize computed diagnostics without turning requirements into results."""

    prefix = dict(task_meta or {})
    rows: list[dict[str, Any]] = []
    for item in statistical.get("diagnostics", []) or []:
        if not isinstance(item, dict):
            continue
        row = {
            **prefix,
            "test_name": item.get("test_name") or item.get("test") or "前提检验",
            "statistic": item.get("statistic", item.get("statistic_value")),
            "p_value": item.get("p_value"),
            "passed": item.get("passed"),
            "detail": item.get("detail") or "",
        }
        if item.get("group") is not None:
            row["group"] = item.get("group")
        if item.get("n") is not None:
            row["n"] = item.get("n")
        rows.append(row)

    sphericity = statistical.get("sphericity")
    if isinstance(sphericity, dict):
        rows.append({
            **prefix,
            "test_name": sphericity.get("test_name") or "Mauchly 球形性检验",
            "statistic": sphericity.get("statistic", sphericity.get("W")),
            "chi_square": sphericity.get("chi_square", sphericity.get("chi2")),
            "df": sphericity.get("df"),
            "p_value": sphericity.get("p_value"),
            "epsilon_gg": sphericity.get("epsilon_gg", sphericity.get("GG_epsilon")),
            "epsilon_hf": sphericity.get("epsilon_hf", sphericity.get("HF_epsilon")),
            "passed": sphericity.get("passed"),
            "detail": sphericity.get("detail") or "",
        })
    return rows


def _assumption_evidence_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_meta, statistical in _iter_statistical_evidence(result):
        rows.extend(_assumption_rows_for_statistical(statistical, task_meta=task_meta))
    return rows


def _assumption_requirements_from_result(result: dict[str, Any]) -> list[str]:
    requirements: list[str] = []
    for _, statistical in _iter_statistical_evidence(result):
        method = statistical.get("method") if isinstance(statistical.get("method"), dict) else {}
        requirements.extend(
            str(item).strip() for item in method.get("assumptions", []) or [] if str(item).strip()
        )
    return list(dict.fromkeys(requirements))


def _effect_size_evidence_count(result: dict[str, Any]) -> int:
    return sum(
        len(_effect_size_table_rows(statistical))
        for _, statistical in _iter_statistical_evidence(result)
    )


def _local_report_evidence_summary(
    result: dict[str, Any], deterministic: NormativeResultReport
) -> dict[str, Any]:
    return {
        "table_count": len(deterministic.tables),
        "ordering_count": len(deterministic.ordered_comparisons),
        "effect_size_count": _effect_size_evidence_count(result),
        "assumption_check_count": len(_assumption_evidence_from_result(result)),
        "preview_rows_sent": 0,
        "preview_columns": [],
        "privacy_mode": "local_only",
    }


def _build_ai_report_evidence_packet(
    deterministic: NormativeResultReport,
    analysis_context: dict[str, Any],
    *,
    result: dict[str, Any],
    include_preview: bool,
) -> dict[str, Any]:
    """Build the only payload an external model may use for report prose."""

    context = analysis_context if isinstance(analysis_context, dict) else {}
    roles = context.get("data_roles") if isinstance(context.get("data_roles"), dict) else {}
    role_columns = list(dict.fromkeys(
        str(value).strip()
        for raw in roles.values()
        for value in (raw if isinstance(raw, list) else [raw])
        if str(value).strip()
    ))[:64]
    allowed_columns = set(role_columns)

    raw_preview = context.get("data_preview") if include_preview else []
    preview_rows: list[dict[str, Any]] = []
    if isinstance(raw_preview, list):
        for raw_row in raw_preview[:20]:
            if not isinstance(raw_row, dict):
                continue
            preview_rows.append({
                str(key): _sanitize_complete_report_context(value, include_preview=True)
                for key, value in list(raw_row.items())[:64]
                if str(key) in allowed_columns
            })

    raw_profile = context.get("data_profile") if isinstance(context.get("data_profile"), dict) else {}
    profile_columns = raw_profile.get("columns") if isinstance(raw_profile.get("columns"), list) else []
    data_profile = {
        "n_rows": raw_profile.get("n_rows"),
        "n_cols": raw_profile.get("n_cols"),
        "total_missing_rate": raw_profile.get("total_missing_rate"),
        "columns": [
            _sanitize_complete_report_context(item, include_preview=False)
            for item in profile_columns[:64]
            if isinstance(item, dict) and str(item.get("name", "")) in allowed_columns
        ],
    }
    assumption_checks = _assumption_evidence_from_result(result)
    assumption_requirements = _assumption_requirements_from_result(result)
    effect_size_count = _effect_size_evidence_count(result)
    return {
        "execution_kind": str(context.get("execution_kind") or "single"),
        "analysis_method": _sanitize_complete_report_context(
            context.get("method", {}), include_preview=False
        ),
        "data_roles": _sanitize_complete_report_context(roles, include_preview=False),
        "analysis_settings": _sanitize_complete_report_context(
            context.get("analysis_settings", {}), include_preview=False
        ),
        "data_profile": data_profile,
        "data_preview": preview_rows,
        "preview_notice": (
            "仅用于理解参与分析列和数值型标签；禁止据此重新计算统计量。"
            if preview_rows
            else "未向 AI 提供原始数据行。"
        ),
        "read_only_ordering": {
            "policy": "只读；必须保持原序，不得把数值大小顺序改写为显著差异。",
            "items": list(deterministic.ordered_comparisons),
        },
        "normative_tables": [
            table.model_dump(mode="json") for table in deterministic.tables
        ],
        "assumption_checks": assumption_checks,
        "assumption_requirements": assumption_requirements,
        "evidence_inventory": {
            "effect_sizes_in_table_2": effect_size_count,
            "computed_assumption_checks": len(assumption_checks),
        },
        "reporting_contract": {
            "table_1": "描述性统计",
            "table_2": "总体/多变量检验、效应量与校正前后判断",
            "table_3": "单变量、简单效应及后续比较",
            "assumption_checks": "结构化前提检验统计；不得以通用假设要求替代实际检验结果",
            "prose_only": True,
            "must_not_recalculate": True,
        },
    }


def _ai_report_evidence_summary(
    evidence_packet: dict[str, Any], *, privacy_mode: str
) -> dict[str, Any]:
    preview = evidence_packet.get("data_preview") or []
    roles = evidence_packet.get("data_roles") or {}
    role_columns = list(dict.fromkeys(
        str(value)
        for raw in roles.values()
        for value in (raw if isinstance(raw, list) else [raw])
        if str(value).strip()
    ))
    return {
        "table_count": len(evidence_packet.get("normative_tables") or []),
        "ordering_count": len((evidence_packet.get("read_only_ordering") or {}).get("items") or []),
        "effect_size_count": int((evidence_packet.get("evidence_inventory") or {}).get("effect_sizes_in_table_2") or 0),
        "assumption_check_count": len(evidence_packet.get("assumption_checks") or []),
        "role_column_count": len(role_columns),
        "preview_rows_sent": len(preview),
        "preview_columns": list(preview[0].keys()) if preview else [],
        "privacy_mode": privacy_mode,
    }


def _deterministic_analysis_guidance(context: dict[str, Any]) -> AnalysisGuidance:
    method_name = str(context.get("selected_method") or "").strip()
    dependent_variables = [str(item) for item in context.get("dependent_variables") or []]
    fixed_factors = [str(item) for item in context.get("fixed_factors") or []]
    covariates = [str(item) for item in context.get("covariates") or []]
    random_factors = [str(item) for item in context.get("random_factors") or []]
    split_by = [str(item) for item in context.get("split_by") or []]
    factor_combinations_enabled = bool(context.get("factor_combinations_enabled", False))
    factor_combination_order = context.get("factor_combination_order")
    factor_combination_min_order = context.get("factor_combination_min_order")
    factor_combination_max_order = context.get("factor_combination_max_order")
    if factor_combination_order is not None:
        factor_combination_min_order = 1
        factor_combination_max_order = factor_combination_order
    combination_p_adjust = str(context.get("combination_p_adjust") or "holm")
    method_parameters = dict(context.get("method_parameters") or {})
    subject_id = str(context.get("subject_id") or "").strip()
    repeated_factor = str(context.get("repeated_factor") or "").strip()
    alpha = context.get("alpha", 0.05)
    profile = context.get("data_profile") or {}

    spec = None
    try:
        spec = get_method(method_name)
        method_label = spec.label_zh
        purpose = spec.purpose
        reason = spec.variable_relationship
        outputs = list(spec.output_metrics)
        limitations = list(spec.assumptions)
        if spec.notes:
            limitations.append(spec.notes)
    except Exception:
        method_label = method_name or "尚未选择统计方法"
        purpose = "请先选择统计方法并配置其所需变量。"
        reason = "方法选择应由研究问题、变量类型和数据结构共同决定。"
        outputs = ["描述统计", "主要检验统计量", "p 值与效应量", "诊断与警告"]
        limitations = ["当前方法尚未识别。"]

    role_lines = []
    if dependent_variables:
        role_lines.append(f"因变量/分析变量：{'、'.join(dependent_variables)}")
    if fixed_factors:
        factor_label = "分类因素候选池" if factor_combinations_enabled else "分类因素"
        role_lines.append(f"{factor_label}：{'、'.join(fixed_factors)}")
        if factor_combinations_enabled:
            role_lines.append(f"因素组合阶数：{factor_combination_min_order}–{factor_combination_max_order}；跨组合校正：{combination_p_adjust}")
    if covariates:
        role_lines.append(f"连续自变量/协变量：{'、'.join(covariates)}")
    if random_factors:
        role_lines.append(f"随机分组因素：{'、'.join(random_factors)}")
    if subject_id:
        role_lines.append(f"受试者/样本 ID：{subject_id}")
    if repeated_factor:
        role_lines.append(f"重复/时间因素：{repeated_factor}")
    if split_by:
        role_lines.append(f"批量拆分列：{'、'.join(split_by)}")

    relationship_parts: list[str] = []
    if fixed_factors:
        if factor_combinations_enabled:
            relationship_parts.append(f"从候选分类因素 {'、'.join(fixed_factors)} 中生成的各阶组合")
        else:
            relationship_parts.append(f"分类因素 {'、'.join(fixed_factors)}")
    if covariates:
        relationship_parts.append(f"连续预测量/协变量 {'、'.join(covariates)}")
    if random_factors:
        relationship_parts.append(f"随机分组因素 {'、'.join(random_factors)}")
    if repeated_factor:
        relationship_parts.append(f"重复因素 {repeated_factor}")

    if dependent_variables and relationship_parts:
        analysis_purpose = (
            f"针对 {'、'.join(dependent_variables)}，使用 {method_label}检验"
            f"{'，并结合'.join(relationship_parts)}的作用或关联。{purpose}"
        )
    elif dependent_variables:
        analysis_purpose = f"针对 {'、'.join(dependent_variables)}，使用 {method_label}进行分析。{purpose}"
    elif fixed_factors:
        analysis_purpose = (
            f"使用 {method_label}分析 {'、'.join(fixed_factors)} 之间的关系。{purpose}"
        )
    else:
        analysis_purpose = purpose

    batch_phrase = ""
    if factor_combinations_enabled:
        batch_phrase = f"程序会分别拟合 {factor_combination_min_order}–{factor_combination_max_order} 阶因素组合，并用 {combination_p_adjust} 校正跨组合检验。"
    expected_outcome = (
        f"程序将使用 {method_label}，基于当前选择生成：{'、'.join(outputs)}。{batch_phrase}"
        "这里描述的是结果的结构和可回答的问题，不会在计算前预测显著性或差异方向。"
    )
    data_basis = []
    if profile.get("n_rows") is not None:
        data_basis.append(f"当前数据集包含 {profile.get('n_rows')} 行、{profile.get('n_cols', '未知')} 列。")
    data_basis.extend(f"{line}。" for line in role_lines)
    column_lookup = {str(column.get("name")): column for column in profile.get("columns", []) if isinstance(column, dict)}
    for variable in dependent_variables + fixed_factors + covariates + random_factors + ([subject_id] if subject_id else []) + ([repeated_factor] if repeated_factor else []):
        column = column_lookup.get(variable)
        if column:
            data_basis.append(f"{variable}：类型 {column.get('dtype', '未知')}，唯一值 {column.get('n_unique', '未知')}，缺失 {column.get('n_missing', '未知')}。")

    checks = [
        "确认每个变量被分配到了正确角色。",
        f"确认显著性水平 α={alpha} 符合研究方案。",
        "确认样本独立性、重复结构和缺失值处理符合试验设计。",
    ]
    if factor_combinations_enabled:
        checks.append("确认候选因素、组合阶数和跨组合多重校正符合预先制定的分析方案。")
    if method_parameters:
        checks.append("确认高级参数仍使用默认值，或已按研究方案有依据地修改。")
    if split_by:
        checks.append("确认拆分后每个子集仍满足该方法的样本量和变量水平要求。")
    limitations.append("统计证据是否能够解释为因果关系，取决于随机化、对照和试验设计，而不是 p 值本身。")

    design_checks: list[str] = []
    recommended_actions: list[str] = []
    critical_issues: list[str] = []
    alternatives: list[str] = []
    n_rows = profile.get("n_rows")
    factor_levels = {
        name: int(column_lookup[name].get("n_unique", 0))
        for name in fixed_factors if name in column_lookup and str(column_lookup[name].get("n_unique", "")).isdigit()
    }
    estimated_cells = 1
    for count in factor_levels.values():
        estimated_cells *= max(count, 1)
    if fixed_factors:
        design_checks.append(f"当前包含 {len(fixed_factors)} 个分类因素，理论完整组合约 {estimated_cells} 个；需要逐组合检查空单元与重复数。")
    if n_rows is not None and estimated_cells > 0 and fixed_factors:
        average_replication = float(n_rows) / estimated_cells
        design_checks.append(f"按总行数粗略估计，每个理论组合平均约 {average_replication:.1f} 条记录；实际最小单元重复将在运行前预检中核算。")
        if average_replication < 2:
            critical_issues.append("理论组合的平均重复不足 2")
            recommended_actions.append("增加因素组合重复或降低模型阶数，避免完整交互模型没有残差自由度。")
    if spec is not None:
        if len(dependent_variables) < spec.min_dependent_vars:
            critical_issues.append(f"分析变量少于方法要求的 {spec.min_dependent_vars} 个")
        if len(fixed_factors) < spec.min_fixed_factors:
            critical_issues.append(f"分类因素少于方法要求的 {spec.min_fixed_factors} 个")
        if len(covariates) < spec.min_covariates:
            critical_issues.append(f"连续自变量少于方法要求的 {spec.min_covariates} 个")
        if len(random_factors) < spec.min_random_factors:
            critical_issues.append(f"随机分组少于方法要求的 {spec.min_random_factors} 个")
        if spec.requires_subject_id and not subject_id:
            critical_issues.append("尚未指定对象 ID")
        if spec.requires_repeated_factor and not repeated_factor:
            critical_issues.append("尚未指定重复或时间因素")
    if method_name in {"oneway_manova", "twoway_manova", "threeway_manova", "multifactor_manova"}:
        outcome_count = len(dependent_variables)
        fixed_order = {"oneway_manova": 1, "twoway_manova": 2, "threeway_manova": 3}.get(
            method_name, int(method_parameters.get("factor_model_order", len(fixed_factors) or 4))
        )
        design_checks.append(f"MANOVA 将联合分析 {outcome_count} 个因变量；当前方法固定为 {fixed_order} 因素模型，已选择 {len(fixed_factors)} 个候选因素。")
        design_checks.append("系统会检查 Box's M、Mardia 残差近似、因变量相关矩阵、条件数和联合响应秩。")
        recommended_actions.append("优先解释 Pillai/Wilks 联合效应；仅在联合效应成立后查看经校正的单变量跟进与事后比较。")
        if outcome_count >= 2 and n_rows is not None and n_rows <= outcome_count + estimated_cells:
            recommended_actions.append("当前行数相对因变量维度和设计单元偏少，建议增加重复或删减冗余因变量。")
    if method_name == "mixed_anova":
        mode = str(method_parameters.get("analysis_mode", "auto"))
        design_checks.append(f"混合设计当前引擎设置为 {mode}；自动模式会在完整平衡单因素设计中使用经典 ANOVA，其余使用 MixedLM。")
        design_checks.append("每个对象必须固定属于一个对象间因素组合，且对象×重复水平不能重复。")
        recommended_actions.append("存在不平衡、部分缺测或两个对象间因素时保留自动/MixedLM 模式，并检查收敛与随机效应方差。")
        alternatives.append("若数据是完整且平衡的单一重复因素设计，可比较经典重复测量 ANOVA；有缺测或层级结构时优先保留混合模型。")
    if method_name == "welch_ttest":
        alternatives.extend([
            "若两组来自同一对象的配对测量，应改用配对 t 检验或相应的重复测量模型。",
            "若分组超过两个水平，应改用 Welch 单因素方差分析或适合该设计的回归模型。",
        ])
    elif method_name in {"oneway_anova", "welch_anova"}:
        alternatives.append("方差明显不齐时优先比较 Welch 单因素方差分析；同一对象被重复测量时改用重复测量或混合模型。")
    elif method_name in {"twoway_anova", "threeway_anova", "multifactor_anova", "ancova"}:
        alternatives.append("若存在对象内重复、批次层级或明显缺测，应比较混合效应模型，避免把相关观测当作独立样本。")
    posthoc_methods = method_parameters.get("posthoc_methods", [])
    if isinstance(posthoc_methods, str):
        posthoc_methods = [posthoc_methods]
    posthoc_methods = [str(item).lower() for item in posthoc_methods]
    if posthoc_methods:
        design_checks.append(f"当前事后比较方法为 {', '.join(posthoc_methods)}；每种方法将独立输出比较和字母分组。")
        if set(posthoc_methods) & {"duncan", "lsd"}:
            recommended_actions.append("Duncan/LSD 较宽松，正式报告建议同步核对 Tukey 或 Holm，并说明预设依据。")
        if "dunnett" in posthoc_methods:
            recommended_actions.append("确认 control_group 与数据中的唯一对照水平完全一致；Dunnett 不生成完整字母分组。")
    if not design_checks:
        design_checks.append("运行前预检会核对完整案例、变量水平、模型参数与可估计性。")
    if not recommended_actions:
        recommended_actions.append("根据预检提示调整设计，并在结果中同时检查诊断、效应量和多重比较。")
    if critical_issues:
        suitability_status = "needs_changes"
        suitability_label = "需要修改"
        suitability_reason = f"当前计划存在 {len(critical_issues)} 项会影响执行或可估计性的关键问题：{'；'.join(critical_issues)}。"
    elif any(item for item in recommended_actions if not item.startswith("根据预检提示")):
        suitability_status = "conditional"
        suitability_label = "有条件适用"
        suitability_reason = "方法与当前变量结构基本匹配，但仍有设计、重复结构或比较策略需要在执行前确认。"
    else:
        suitability_status = "suitable"
        suitability_label = "当前适用"
        suitability_reason = "当前变量角色满足方法的基本结构要求，仍需通过运行前预检和结果诊断确认统计假设。"
    design_review_summary = (
        f"当前计划使用 {method_label}，重点审查 {len(dependent_variables)} 个分析变量、"
        f"{len(fixed_factors)} 个分类因素及其重复/层级结构。预检通过不等于假设必然成立，运行后仍需结合诊断复核。"
    )

    return AnalysisGuidance(
        suitability_status=suitability_status, suitability_label=suitability_label,
        suitability_reason=suitability_reason,
        analysis_purpose=analysis_purpose, method_reason=reason, expected_outcome=expected_outcome,
        design_review_summary=design_review_summary, design_checks=design_checks,
        recommended_actions=recommended_actions, expected_outputs=outputs,
        data_basis=data_basis, checks_before_run=checks,
        limitations=list(dict.fromkeys(item for item in limitations if item)),
        alternatives=list(dict.fromkeys(item for item in alternatives if item)),
    )


def _method_guidance_parts(
    method: str, dv_text: str, factor_text: str, factor_count: int
) -> tuple[str, str, list[str], str]:
    mapping: dict[str, tuple[str, str, list[str], str]] = {
        "welch_ttest": (
            f"比较 {factor_text} 的两个独立组在 {dv_text} 上的平均水平是否存在统计证据支持的差异。",
            "Welch t 检验不强制两个组具有相同方差，适合常见的独立两组比较。",
            ["两组样本量、均值和标准差", "均值差及置信区间", "t 值、自由度和 p 值", "标准化效应量与假设检查"],
            "要求观测相互独立；若同一对象被重复测量，应改用配对或重复测量方法。",
        ),
        "independent_ttest": (
            f"比较 {factor_text} 的两个独立组在 {dv_text} 上的平均水平。",
            "Student t 检验适用于接受两组方差齐性假设的独立两组设计。",
            ["两组描述统计", "均值差和置信区间", "t 值、自由度和 p 值", "效应量与方差齐性检查"],
            "若方差明显不齐，Student t 检验可能不稳健，应优先考虑 Welch t 检验。",
        ),
        "paired_ttest": (
            f"比较同一对象或匹配对象的两个测量指标 {dv_text} 之间的平均变化。",
            "配对 t 检验利用成对关系分析差值，适合前后测或匹配样本。",
            ["有效配对数", "平均差值及置信区间", "t 值、自由度和 p 值", "配对效应量与差值分布检查"],
            "两列必须逐行或按对象正确配对，不能把独立样本误当作配对数据。",
        ),
        "oneway_anova": (
            f"检验单个分类因素 {factor_text} 的多个水平在 {dv_text} 的总体均值上是否存在差异。",
            "单因素方差分析适合一个固定因素、三个或更多独立组的总体比较。",
            ["各组描述统计", "总体 F 检验、自由度和 p 值", "效应量", "显著时的事后多重比较", "残差和方差假设检查"],
            "总体检验显著只说明至少一组不同，具体组间差异需要事后比较。",
        ),
        "welch_anova": (
            f"在不要求各组方差相等的情况下，检验 {factor_text} 的多个水平在 {dv_text} 上的总体均值差异。",
            "Welch ANOVA 对方差不齐和样本量不等更稳健。",
            ["各组描述统计", "Welch F 统计量、校正自由度和 p 值", "效应量或差异规模", "适用的稳健事后比较提示"],
            "总体显著后应使用适合方差不齐的事后比较，不能机械套用普通 Tukey。",
        ),
        "twoway_anova": (
            f"同时分析 {factor_text} 对 {dv_text} 的两个主效应，并检验两个因素是否存在交互作用。",
            "双因素方差分析能够判断一个因素的影响是否会随另一个因素水平而改变。",
            ["两个主效应的 F、自由度、p 值和偏 η²", "交互效应的 F、自由度、p 值和偏 η²", "各因素组合的描述统计", "必要的简单效应或事后比较", "模型诊断和交互图"],
            "存在显著交互时，不应脱离交互结构单独概括主效应。",
        ),
        "threeway_anova": (
            f"分析三个固定因素对 {dv_text} 的主效应、两两交互和三因素交互。",
            "三因素模型适合同时研究三个处理维度及其组合关系。",
            ["三个主效应", "三个两因素交互", "一个三因素交互", "各效应的 F、p 值和效应量", "必要的简单效应与诊断"],
            "高阶交互解释复杂，且当前实现为实验性，需要重点人工复核。",
        ),
        "multifactor_anova": (
            f"分析 {factor_text} 对 {dv_text} 的全部主效应及最高至所选阶数的交互作用。",
            "4–8 因素方差分析使用完整析因模型，并在运行前检查设计矩阵是否可估计。",
            ["全部阶次总体 F 检验", "Type I/II/III 平方和", "偏 η² 与 ω²", "设计单元描述统计", "残差和方差齐性诊断"],
            "应从最高阶显著交互开始解释；高阶模型需要足够完整单元和组合内重复。",
        ),
        "oneway_manova": (
            f"联合检验 {factor_text} 是否对多个相关因变量 {dv_text} 的整体响应模式产生影响。",
            "MANOVA 将多个因变量作为一个联合响应，减少逐个检验时忽略变量相关结构的问题。",
            ["多变量总体检验统计量", "近似 F、自由度和 p 值", "显著后各因变量的后续分析", "协方差结构与奇异性警告"],
            "总体多变量效应不能直接说明哪个因变量造成差异，需结合后续单变量分析。",
        ),
        "twoway_manova": (
            f"联合检验两个因素 {factor_text} 的多元主效应及交互作用是否影响相关因变量 {dv_text}。",
            "双因素 MANOVA 在同一联合响应模型中检验两个主效应和 A×B 交互。",
            ["两个多元主效应", "多元交互效应", "四种多元统计量", "显著后的校正单变量跟进与条件比较"],
            "交互显著时应优先解释条件简单效应，而不是脱离交互概括边际主效应。",
        ),
        "threeway_manova": (
            f"联合检验三个因素 {factor_text} 的主效应、两两交互和三因素交互是否影响相关因变量 {dv_text}。",
            "三因素 MANOVA 使用完整析因联合响应模型。",
            ["三个多元主效应", "三个多元两因素交互", "多元三因素交互", "校正后的单变量跟进"],
            "高阶交互需要结合设计单元、交互图和效应量谨慎解释。",
        ),
        "multifactor_manova": (
            f"联合检验 {factor_text} 的主效应和全部阶次交互是否影响相关因变量 {dv_text}。",
            "4–8 因素 MANOVA 使用完整析因联合响应模型，并保留预先指定的主要多元判据。",
            ["全部多元主效应与交互", "主要多元判据及近似 F", "校正后的单变量跟进", "协方差、正态性和共线诊断"],
            "四因素及以上不会自动展开指数级简单效应；显著交互应按预先规划的条件对比继续分析。",
        ),
    }
    return mapping.get(
        method,
        (
            f"使用当前方法分析 {factor_text} 与 {dv_text} 之间的统计关系。",
            "方法的适用性取决于当前变量角色、样本结构和研究设计。",
            ["描述统计", "总体检验统计量", "p 值与效应量", "模型警告和诊断"],
            "当前方法的详细解释尚未内置，请在执行前人工确认设计假设。",
        ),
    )


def _ordered_expression(entries: list[tuple[str, float]]) -> tuple[str, str]:
    ordered = sorted(entries, key=lambda item: (-item[1], item[0]))
    parts: list[str] = []
    details: list[str] = []
    previous: float | None = None
    for label, value in ordered:
        if parts:
            parts.append(" = " if previous is not None and math.isclose(previous, value, rel_tol=1e-12, abs_tol=1e-12) else " > ")
        parts.append(label)
        details.append(f"{label}: {_fmt(value)}")
        previous = value
    return "".join(parts), "；".join(details)


def _ordered_comparisons_for_statistical(
    statistical: dict[str, Any], *, prefix: str = ""
) -> list[str]:
    """从计算结果生成可追溯的 A > B > C 式排序，不让 AI 推测次序。"""

    ranked_statements: list[tuple[int, int, str]] = []
    seen: set[tuple[tuple[str, float], ...]] = set()
    sequence_index = 0

    def append_ranking(
        entries: list[tuple[str, float]], *, scope: str, basis: str,
        letter_rows: list[dict[str, Any]] | None = None, priority: int = 3,
    ) -> None:
        nonlocal sequence_index
        cleaned = [(str(label).strip(), float(value)) for label, value in entries if str(label).strip()]
        cleaned = [(label, value) for label, value in cleaned if math.isfinite(value)]
        if len(cleaned) < 2:
            return
        signature = tuple(sorted(cleaned))
        if signature in seen:
            return
        seen.add(signature)
        expression, details = _ordered_expression(cleaned)
        ranking_statement = (
            f"{prefix}{scope}：{expression}（{details}；按{basis}从高到低；“>”表示估计值顺序，显著性以校正后的成对比较为准）。"
        )
        if letter_rows:
            letters = " > ".join(
                f"{row.get('group')}[{row.get('letters')} ]".replace(" ]", "]")
                for row in sorted(
                    letter_rows,
                    key=lambda row: (-float(row.get("mean", 0)), str(row.get("group", ""))),
                )
            )
            ranked_statements.append((
                0,
                sequence_index,
                f"{prefix}{scope}显著性层级：{letters}"
                "（仍按估计值从高到低排列；共享字母表示差异未达到显著，没有共同字母才表示差异显著）。",
            ))
            sequence_index += 1
        ranked_statements.append((priority, sequence_index, ranking_statement))
        sequence_index += 1

    letter_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in statistical.get("significance_letters", []) or []:
        if row.get("group") is None or row.get("mean") is None:
            continue
        key = tuple(str(row.get(name, "") or "") for name in ("outcome", "factor", "context", "method"))
        letter_groups.setdefault(key, []).append(row)
    for (outcome, factor, context, method), rows in letter_groups.items():
        qualifier = " / ".join(item for item in [outcome, factor, context] if item)
        append_ranking(
            [(str(row["group"]), float(row["mean"])) for row in rows],
            scope=f"{qualifier + ' ' if qualifier else ''}组别排序",
            basis=f"{method or '事后比较'}对应的估计值",
            letter_rows=rows,
            priority=1,
        )

    emm_groups: dict[tuple[str, ...], list[tuple[str, float]]] = {}
    for row in statistical.get("estimated_marginal_means", []) or []:
        if row.get("group") is None or row.get("mean") is None:
            continue
        levels = row.get("levels") if isinstance(row.get("levels"), dict) else {}
        key = tuple(sorted(map(str, levels.keys())))
        emm_groups.setdefault(key, []).append((str(row["group"]), float(row["mean"])))
    for factors, entries in emm_groups.items():
        append_ranking(
            entries,
            scope=f"{' × '.join(factors) + ' ' if factors else ''}边际均值排序",
            basis="估计边际均值",
            priority=2,
        )

    rows = list(statistical.get("descriptive_stats", []) or [])
    if rows:
        # MANOVA 常把每个因变量保存为 outcome_mean。
        outcome_mean_keys = sorted({key for row in rows for key in row if str(key).endswith("_mean")})
        design_factors = list((statistical.get("design") or {}).get("between_factors", []) or [])

        def row_label(row: dict[str, Any]) -> str:
            if row.get("group") is not None:
                return str(row["group"])
            factor_parts = [f"{factor}={row[factor]}" for factor in design_factors if factor in row]
            if factor_parts:
                return " / ".join(factor_parts)
            for key in ("level", "variable", "name"):
                if row.get(key) is not None:
                    return str(row[key])
            return ""

        for mean_key in outcome_mean_keys:
            append_ranking(
                [(row_label(row), float(row[mean_key])) for row in rows if row_label(row) and row.get(mean_key) is not None],
                scope=f"{mean_key[:-5]} 组别均值排序",
                basis="描述性均值",
                priority=3,
            )
        if not outcome_mean_keys:
            metric = next((key for key in ("mean", "proportion", "success_rate") if any(row.get(key) is not None for row in rows)), None)
            if metric:
                metric_label = {"mean": "均值", "proportion": "比例", "success_rate": "成功率"}[metric]
                append_ranking(
                    [(row_label(row), float(row[metric])) for row in rows if row_label(row) and row.get(metric) is not None],
                    scope=f"组别{metric_label}排序",
                    basis=f"描述性{metric_label}",
                    priority=3,
                )
    return [
        statement for _, _, statement in sorted(ranked_statements, key=lambda item: (item[0], item[1]))
    ][:16]


def _ordered_comparisons_from_result(result: dict[str, Any]) -> list[str]:
    payload = result.get("result", result)
    if result.get("kind") == "batch" or payload.get("results"):
        statements: list[str] = []
        for index, task in enumerate(payload.get("results", []) or [], start=1):
            statistical = task.get("result")
            if not isinstance(statistical, dict):
                continue
            info = task.get("subset_info") if isinstance(task.get("subset_info"), dict) else {}
            label = (
                info.get("factor_combination") or info.get("dependent_variable")
                or task.get("subset_key") or f"任务 {index}"
            )
            statements.extend(_ordered_comparisons_for_statistical(statistical, prefix=f"{label}｜"))
            if len(statements) >= 40:
                break
        return statements[:40]
    statistical = payload.get("result", payload)
    return _ordered_comparisons_for_statistical(statistical)


def _deterministic_result_help(result: dict[str, Any]) -> ResultGuidance:
    payload = result.get("result", result)
    if result.get("kind") == "batch" or payload.get("results"):
        count = len(payload.get("results", []))
        ordered = _ordered_comparisons_from_result(result)
        return ResultGuidance(
            title="批量分析结果说明",
            summary=f"本次共生成 {count} 个子集结果。应逐个检查子集样本量、方向、效应量和警告。",
            findings=[f"已完成 {count} 个子集分析。", *ordered],
            next_checks=["核对子集划分", "比较各子集效应方向和大小", "考虑多重检验校正"],
            cautions=["多个子集同时检验会增加偶然显著的概率。"],
        )

    statistical = payload.get("result", payload)
    method = statistical.get("method", {})
    tests = statistical.get("primary_tests", []) or statistical.get("omnibus_tests", []) or []
    alpha = statistical.get("alpha", 0.05)
    findings: list[str] = []
    findings.extend(_ordered_comparisons_from_result(result))
    for test in tests:
        effect = test.get("effect", "效应")
        p_value = test.get("p_value")
        f_value = test.get("f_value", test.get("statistic_value"))
        eta = test.get("eta_sq_p", test.get("effect_size_value"))
        significant = bool(
            test.get(
                "is_significant",
                p_value is not None and float(p_value) < float(alpha),
            )
        )
        conclusion = "达到统计显著" if significant else "未达到统计显著"
        parts = [f"{effect}：{conclusion}"]
        if f_value is not None:
            parts.append(f"F={_fmt(f_value)}")
        if p_value is not None:
            parts.append(f"p={_fmt(p_value, 6)}")
        if eta is not None:
            parts.append(f"η²p={_fmt(eta)}")
        findings.append("，".join(parts) + "。")
    letter_groups = statistical.get("significance_letters", []) or []
    if letter_groups:
        methods = sorted({str(item.get("method", "")) for item in letter_groups if item.get("method")})
        findings.append(f"已生成 {len(letter_groups)} 行显著性字母分组，涉及 {', '.join(methods) or '当前事后检验'}；共享字母表示差异不显著。")
    summary = (
        "统计引擎已完成总体检验。请把显著性与效应量、样本结构和研究设计结合解释。"
        if findings
        else "统计引擎已完成运行，但当前结果中没有总体检验表。"
    )
    return ResultGuidance(
        title=f"{method.get('label_zh', '统计分析')}结果说明",
        summary=summary,
        findings=findings,
        next_checks=["按模型结构阅读交互与主效应", "查看效应量和诊断警告", "核对是否需要事后比较"],
        cautions=["未显著不等于完全相同", "显著不等于实际影响一定很大", "AI 解释不能替代研究者复核"],
    )


_MANOVA_PRIMARY_STATISTIC_LABELS = {
    "pillai": ("Pillai 轨迹", "Pillai's trace"),
    "wilks": ("Wilks' Lambda", "Wilks' lambda"),
    "hotelling_lawley": ("Hotelling–Lawley 轨迹", "Hotelling-Lawley trace"),
    "roy": ("Roy 最大根", "Roy's greatest root"),
}


def _effect_parts(effect: Any) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(effect or "").split("×") if part.strip())


def _result_row_is_significant(
    row: dict[str, Any], *, alpha: float, prefer_adjusted: bool = False
) -> bool:
    p_keys = ("p_adjusted", "p_value") if prefer_adjusted else ("p_value", "p_adjusted")
    for key in p_keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value) < alpha
        except (TypeError, ValueError):
            break
    for key in ("is_significant", "significant"):
        if row.get(key) is not None:
            return row.get(key) is True
    return False


def _is_manova_result(statistical: dict[str, Any]) -> bool:
    method = dict(statistical.get("method", {}) or {})
    identity = f"{method.get('name', '')} {method.get('label_zh', '')}".lower()
    snapshot = dict(statistical.get("data_snapshot", {}) or {})
    return "manova" in identity or bool(snapshot.get("primary_multivariate_test"))


def _primary_manova_rows(
    statistical: dict[str, Any], omnibus: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    """只用预先指定的 MANOVA 判据驱动正文结论，替代判据留在表中。"""

    if not _is_manova_result(statistical) or not omnibus:
        return omnibus, ""
    snapshot = dict(statistical.get("data_snapshot", {}) or {})
    primary_key = str(snapshot.get("primary_multivariate_test") or "pillai").strip().lower()
    primary_key = {
        "pillai_trace": "pillai",
        "wilks_lambda": "wilks",
        "hotelling": "hotelling_lawley",
        "hotelling_trace": "hotelling_lawley",
        "roys_largest_root": "roy",
        "roy_largest_root": "roy",
    }.get(primary_key, primary_key)
    labels = _MANOVA_PRIMARY_STATISTIC_LABELS.get(primary_key, ())
    selected = [
        row for row in omnibus
        if any(label.casefold() in str(row.get("statistic_name", "")).casefold() for label in labels)
    ]
    if selected:
        return selected, str(selected[0].get("statistic_name") or labels[0])

    # 兼容旧结果：每个效应只取首次保存的判据作为正文依据，避免事后挑选显著行。
    first_by_effect: dict[str, dict[str, Any]] = {}
    for row in omnibus:
        first_by_effect.setdefault(str(row.get("effect", "")), row)
    fallback_rows = list(first_by_effect.values())
    label = str(fallback_rows[0].get("statistic_name") or "首个已保存多变量判据")
    return fallback_rows, label


def _factor_level_counts(statistical: dict[str, Any]) -> dict[str, int]:
    design = dict(statistical.get("design", {}) or {})
    factors = [
        str(item) for item in [
            *(design.get("between_factors", []) or []),
            *(design.get("within_factors", []) or []),
        ]
    ]
    counts: dict[str, int] = {}
    for variable in design.get("variables", []) or []:
        name = str(variable.get("name", ""))
        if name not in factors:
            continue
        levels = variable.get("levels")
        if isinstance(levels, list) and levels:
            counts[name] = len({str(item) for item in levels})
        elif variable.get("n_unique") is not None:
            try:
                counts[name] = int(variable["n_unique"])
            except (TypeError, ValueError):
                pass
    for factor in factors:
        values = {
            str(row[factor])
            for row in statistical.get("descriptive_stats", []) or []
            if isinstance(row, dict) and row.get(factor) is not None
        }
        if values:
            counts[factor] = max(counts.get(factor, 0), len(values))
    return counts


def _simple_effect_identity(item: dict[str, Any]) -> tuple[str, frozenset[str]]:
    raw_effect = str(item.get("effect", ""))
    outcome = ""
    remainder = raw_effect
    if remainder.startswith("[") and "]" in remainder:
        outcome, remainder = remainder[1:].split("]", 1)
        remainder = remainder.strip()
    tested_factor = remainder.split("@", 1)[0].strip()
    fixed = _effect_parts(item.get("fixed_factor"))
    return outcome.strip(), frozenset([tested_factor, *fixed] if tested_factor else fixed)


def _contrast_parent(contrast: str) -> tuple[str, str, str]:
    """返回 (类型, 因变量, 父效应/简单效应标签)。"""

    text = str(contrast or "").strip()
    if " @ " in text and " | " in text:
        return "conditional", "", text.split(" | ", 1)[0].strip()
    if text.startswith("[") and "]" in text:
        bracket, _ = text[1:].split("]", 1)
        parts = [part.strip() for part in bracket.split("|")]
        if len(parts) >= 2:
            if "用户指定" in parts[-1]:
                return "planned", parts[0], parts[-1]
            return "main", parts[0], parts[-1]
        return "main", "", parts[0] if parts else ""
    return "unknown", "", ""


def _normative_controlled_sections(
    statistical: dict[str, Any], *, alpha: float
) -> dict[str, Any]:
    """把统计层级规则落实到正文；完整计算输出仍由规范表保留。"""

    primary_tests = list(statistical.get("primary_tests", []) or [])
    omnibus_all = sorted(
        list(statistical.get("omnibus_tests", []) or []),
        key=lambda row: str(row.get("effect", "")).count("×"),
        reverse=True,
    )
    is_manova = _is_manova_result(statistical)
    decision_rows, primary_label = _primary_manova_rows(statistical, omnibus_all)
    decision_rows = sorted(
        decision_rows,
        key=lambda row: str(row.get("effect", "")).count("×"),
        reverse=True,
    )
    interaction_rows = [row for row in decision_rows if len(_effect_parts(row.get("effect"))) >= 2]
    main_rows = [row for row in decision_rows if len(_effect_parts(row.get("effect"))) < 2]
    significant_interaction_sets = [
        frozenset(_effect_parts(row.get("effect")))
        for row in interaction_rows
        if _result_row_is_significant(row, alpha=alpha)
    ]
    interpretive_interaction_sets = [
        factors for factors in significant_interaction_sets
        if not any(factors < higher for higher in significant_interaction_sets)
    ]
    blocked_effects: set[str] = set()
    for row in decision_rows:
        parts = frozenset(_effect_parts(row.get("effect")))
        if parts and any(parts < interaction for interaction in significant_interaction_sets):
            blocked_effects.add(str(row.get("effect", "")))

    inference = [_normative_test_sentence(item, alpha=alpha) for item in primary_tests]
    if is_manova and primary_label:
        inference.append(
            f"MANOVA 正文按预先指定的{primary_label}作整体判断；其他多变量判据仅在规范表中作补充披露，不据其事后改选结论。"
        )
    for item in [*interaction_rows, *main_rows]:
        sentence = _normative_test_sentence(item, alpha=alpha)
        effect = str(item.get("effect", ""))
        if effect in blocked_effects:
            kind = "低阶交互" if len(_effect_parts(effect)) >= 2 else "主效应"
            sentence += f" 该{kind}受更高阶显著交互限定，仅作完整披露，不作脱离条件的独立解释。"
        inference.append(sentence)

    significant_interaction_effects = [
        str(row.get("effect", ""))
        for row in interaction_rows
        if frozenset(_effect_parts(row.get("effect"))) in interpretive_interaction_sets
    ]
    if significant_interaction_effects:
        highest_order = max(len(_effect_parts(effect)) for effect in significant_interaction_effects)
        follow_up_name = "简单简单效应" if highest_order >= 3 else "简单效应"
        inference.append(
            f"由于存在显著交互（{'、'.join(significant_interaction_effects)}），受交互限定的主效应不作脱离条件的总体概括，"
            f"受更高阶交互限定的低阶交互也不作独立解释；后续只解释由该交互触发并经校正的{follow_up_name}。"
        )
    elif interaction_rows:
        inference.append("相关交互均未达到统计显著，随后才解释未受交互限定的主效应及其有统计依据的比较。")
    if not inference:
        inference.append("当前方法未提供单独的总体推断检验，应结合模型系数、拟合指标或描述统计解释。")

    notes: list[str] = []
    follow_up: list[str] = []
    parent_significant = {
        str(row.get("effect", ""))
        for row in decision_rows
        if _result_row_is_significant(row, alpha=alpha)
    }
    eligible_follow_ups: list[dict[str, Any]] = []
    suppressed_parent_follow_up = False
    for item in statistical.get("follow_up_tests", []) or []:
        if is_manova and decision_rows and str(item.get("effect", "")) not in parent_significant:
            suppressed_parent_follow_up = True
            continue
        eligible_follow_ups.append(item)
        significant = _result_row_is_significant(item, alpha=alpha, prefer_adjusted=True)
        follow_up.append(
            f"{item.get('outcome', '因变量')} 的 {item.get('effect', '效应')} 单变量跟进"
            f"{'达到' if significant else '未达到'}校正后统计显著："
            f"F({_fmt(item.get('df_num'), 2)}, {_fmt(item.get('df_den'), 2)})={_fmt(item.get('f_value'))}，"
            f"校正后 p={_fmt(item.get('p_adjusted', item.get('p_value')), 6)}（{item.get('correction', '未注明校正')}）。"
        )
    if suppressed_parent_follow_up:
        notes.append("有单变量跟进未通过预先指定多变量父检验的显著性门槛，正文不作推断；相应计算行仍保留在规范表中供复核。")

    significant_follow_interactions: dict[str, list[frozenset[str]]] = {}
    for item in eligible_follow_ups:
        parts = frozenset(_effect_parts(item.get("effect")))
        if len(parts) >= 2 and _result_row_is_significant(item, alpha=alpha, prefer_adjusted=True):
            significant_follow_interactions.setdefault(str(item.get("outcome", "")), []).append(parts)

    eligible_simple_labels: set[str] = set()
    eligible_significant_simple_labels: set[str] = set()
    suppressed_simple = False
    for item in statistical.get("simple_effects", []) or []:
        outcome, parent_parts = _simple_effect_identity(item)
        if is_manova:
            parent_allowed = parent_parts in significant_follow_interactions.get(outcome, [])
        elif interaction_rows:
            parent_allowed = parent_parts in interpretive_interaction_sets
        else:
            parent_allowed = True
        if not parent_allowed:
            suppressed_simple = True
            continue
        label = str(item.get("effect", ""))
        eligible_simple_labels.add(label)
        significant = _result_row_is_significant(item, alpha=alpha, prefer_adjusted=True)
        if significant:
            eligible_significant_simple_labels.add(label)
        simple_name = "简单简单效应" if len(parent_parts) >= 3 else "简单效应"
        follow_up.append(
            f"在 {item.get('fixed_level', '给定条件')} 下，{item.get('effect', simple_name)} {simple_name}"
            f"{'达到' if significant else '未达到'}校正后统计显著："
            f"F({_fmt(item.get('df_num'), 2)}, {_fmt(item.get('df_den'), 2)})={_fmt(item.get('f_value'))}，"
            f"校正后 p={_fmt(item.get('p_adjusted', item.get('p_value')), 6)}（{item.get('correction', '未注明校正')}）。"
        )
    if suppressed_simple:
        notes.append("有简单效应没有显著交互或显著单变量交互作为父检验依据，正文已停止解释；规范表仅保留原始计算行。")

    factor_counts = _factor_level_counts(statistical)
    significant_main_effects = {
        str(row.get("effect", ""))
        for row in decision_rows
        if len(_effect_parts(row.get("effect"))) == 1
        and _result_row_is_significant(row, alpha=alpha)
        and str(row.get("effect", "")) not in blocked_effects
    }
    significant_follow_main = {
        (str(row.get("outcome", "")), str(row.get("effect", "")))
        for row in eligible_follow_ups
        if len(_effect_parts(row.get("effect"))) == 1
        and _result_row_is_significant(row, alpha=alpha, prefer_adjusted=True)
    }
    two_level_suppressed: set[str] = set()
    other_suppressed = False
    planned_factors = {
        str(item) for item in (dict(statistical.get("data_snapshot", {}) or {}).get("emm_factors", []) or [])
    }
    for item in statistical.get("contrasts", []) or []:
        contrast_text = str(item.get("contrast", "比较"))
        comparison_type, outcome, parent = _contrast_parent(contrast_text)
        label = "比较"
        allowed = True
        factor = ""
        if comparison_type == "conditional":
            simple_label = parent
            if simple_label.startswith("[") and "]" in simple_label:
                _, remainder = simple_label[1:].split("]", 1)
                factor = remainder.split("@", 1)[0].strip()
            else:
                factor = simple_label.split("@", 1)[0].strip()
            allowed = simple_label in eligible_significant_simple_labels
            label = "显著简单效应后的条件内比较"
        elif comparison_type == "main":
            factor = parent
            allowed = (
                (outcome, parent) in significant_follow_main
                if is_manova and outcome
                else parent in significant_main_effects
            )
            label = "显著主效应后的事后多重比较"
        elif comparison_type == "planned":
            label = "用户预先指定的 EMM 比较"
        elif is_manova or interaction_rows:
            matched = next((factor for factor in planned_factors if f"{factor}=" in contrast_text), "")
            factor = matched
            allowed = bool(matched) and matched not in blocked_effects
            label = "用户预先指定的 EMM 比较"

        if allowed and factor and factor_counts.get(factor) == 2:
            two_level_suppressed.add(factor)
            continue
        if not allowed:
            other_suppressed = True
            continue
        significant = _result_row_is_significant(item, alpha=alpha, prefer_adjusted=True)
        correction = str(item.get("correction") or "未注明校正")
        p_value = item.get("p_adjusted", item.get("p_value"))
        p_label = "p" if correction.lower() == "none" else "校正后 p"
        follow_up.append(
            f"{label}｜{contrast_text}：估计差={_fmt(item.get('estimate'))}，"
            f"{p_label}={_fmt(p_value, 6)}（{correction}），{'达到' if significant else '未达到'}统计显著。"
        )
    if two_level_suppressed:
        notes.append(
            f"{'、'.join(sorted(two_level_suppressed))}仅含两个水平，不另写成事后多重比较；差异方向只按本地均值或 EMM 排序报告。"
        )
    if other_suppressed:
        notes.append("有成对比较未满足显著父检验或显著简单效应的触发条件，正文不作推断；完整结果仍保留在规范表中。")
    follow_up.extend(notes)
    if not follow_up:
        follow_up.append("本次结果未生成符合父检验与交互层级规则的单变量跟进、简单效应或成对比较。")

    return {
        "inference": inference,
        "follow_up": follow_up,
        "significant_interactions": significant_interaction_effects,
        "decision_rows": decision_rows,
        "control_notes": notes,
    }


def _deterministic_normative_report(
    result: dict[str, Any], *, title: str
) -> NormativeResultReport:
    payload = result.get("result", result)
    if result.get("kind") == "batch" or payload.get("results"):
        tasks = list(payload.get("results", []) or payload.get("tasks", []) or [])
        overview = list(payload.get("overview", []) or payload.get("summary", []) or [])
        settings = dict(payload.get("settings", {}) or result.get("plan", {}) or {})
        count = len(tasks)
        failed_tasks = [item for item in tasks if item.get("error")]
        completed = count - len(failed_tasks)
        correction = str(
            settings.get("cross_model_p_adjust")
            or settings.get("combination_p_adjust")
            or next((row.get("p_adjust_method") for row in overview if row.get("p_adjust_method")), "holm")
        )
        correction_label = {
            "holm": "Holm",
            "bonferroni": "Bonferroni",
            "fdr_bh": "Benjamini-Hochberg FDR",
            "none": "不校正",
        }.get(correction, correction)
        significant_tasks = {
            row.get("task_id") or row.get("factor_combination") or index
            for index, row in enumerate(overview, start=1)
            if (
                row.get("significant") is True
                or row.get("raw_conclusion") == "原始显著"
                or row.get("conclusion") == "原始显著"
                if correction == "none"
                else row.get("significant_adjusted") is True
                or row.get("conclusion") == "校正后显著"
            )
        }
        dimensions = list(payload.get("split_cols", []) or payload.get("dimensions", []) or [])
        method_name = str(payload.get("method") or settings.get("method") or "批量统计分析")
        try:
            method_label = get_method(method_name).label_zh
        except Exception:
            method_label = method_name
        diagnostic_total = 0
        diagnostic_attention = 0
        tasks_without_diagnostics = 0
        failed_task_notes: list[str] = []
        for task in tasks:
            info = dict(task.get("subset_info", {}) or {})
            task_identifier = info.get("task_id") or task.get("subset_key")
            task_label_parts = [
                f"{_REPORT_COLUMN_LABELS.get(str(key), str(key))}={value}"
                for key, value in info.items()
                if key not in {"task_id", "combination_order"}
                and value is not None
                and value != ""
            ]
            task_label = "；".join(task_label_parts) or (
                f"任务 {task_identifier}" if task_identifier is not None and task_identifier != "" else "当前任务"
            )
            if task.get("error"):
                failed_task_notes.append(f"{task_label}：执行失败（{task.get('error')}）。")
                continue
            task_statistical = dict(task.get("result", {}) or {})
            diagnostics = list(task_statistical.get("diagnostics", []) or [])
            if diagnostics:
                diagnostic_total += len(diagnostics)
                diagnostic_attention += sum(
                    diagnostic.get("passed") is False for diagnostic in diagnostics
                )
            else:
                tasks_without_diagnostics += 1
        tables = _normative_batch_report_tables(
            tasks=tasks,
            overview=overview,
            method_label=method_label,
            include_cross_task_adjustment=correction != "none",
        )
        ordered_comparisons = _ordered_comparisons_from_result(result)
        return NormativeResultReport(
            title=title,
            analysis_overview=[
                f"采用{method_label}执行多模型分析，共展开 {count} 个独立任务；成功 {completed} 个，失败 {len(failed_tasks)} 个。",
                "各任务分别拟合并按统一字段合并；设计单元描述统计见表1，总体检验与跨任务判断见表2，后续检验见表3，正文不逐行复述表内数值。",
            ],
            data_and_design=[
                f"批量维度为 {'、'.join(_REPORT_COLUMN_LABELS.get(str(item), str(item)) for item in dimensions) or '未单列维度'}；因变量为 {payload.get('dv_col') or '见各任务'}；分类因素候选池为 {'、'.join(map(str, payload.get('factor_cols', []) or [])) or '见各任务'}。",
            ],
            descriptive_statistics=[
                f"{completed} 个成功任务的各设计单元 M、SD 与 n 已集中列于表1；为便于批量比较，正文不再按任务和组别重复陈列。",
            ],
            assumption_review=[
                (
                    f"成功任务共记录 {diagnostic_total} 项模型诊断，其中 {diagnostic_attention} 项需要关注；另有 {tasks_without_diagnostics} 个任务未生成可单列诊断，需结合研究设计复核。"
                    if diagnostic_total
                    else f"{completed} 个成功任务未生成可统一汇总的独立诊断检验，仍需结合随机化、独立性和数据结构复核模型假设。"
                ),
                *failed_task_notes,
            ],
            inferential_results=(
                [
                    "多模型总体检验和校正前判断见表2；正文不逐任务复制 p 值与显著性标签。",
                    f"本次明确选择不做跨模型校正；只按原始 p 判断，达到显著的任务共有 {len(significant_tasks)} 个。",
                    "本次没有‘跨任务校正 p’或‘校正后显著性’；同时检验越多，至少出现一个偶然显著结果的概率越高。",
                ]
                if correction == "none"
                else [
                    "多模型总体检验及校正前后显著性见表2；正文不逐任务复制 p 值与显著性标签。",
                    f"跨模型校正方法为 {correction_label}；校正后达到显著的任务共有 {len(significant_tasks)} 个。",
                    "交互、主效应和父子检验层级仍由本地规范规则控制；具体变化应在表2中按任务对照校正前后判断。",
                ]
            ),
            follow_up_results=[
                "各任务的单变量跟进、简单效应与具体比较见表3。",
                "每个任务内部的单变量跟进、简单效应和事后比较使用各自的对比校正，不与跨模型总体检验混成同一校正家族。",
            ] if tables[2].rows else ["统计引擎未生成单变量跟进、简单效应或事后多重比较；表3保留为空表以维持规范结构。"],
            effect_sizes_and_uncertainty=[
                "效应量与可用区间随相应检验保留在规范表中；解释时应同时考虑方向、大小与不确定性，不能仅凭 p 值判断实际重要性。"
            ],
            ordered_comparisons=ordered_comparisons or [
                "当前批量结果没有可用于组别排序的均值、边际均值或比例；不根据 p 值大小推造 A > B > C。"
            ],
            conclusion=[
                (
                    f"本次多模型运行产生 {count} 个任务，其中 {len(significant_tasks)} 个按原始 p 达到显著；未生成校正后结论。"
                    if correction == "none"
                    else f"本次多模型运行产生 {count} 个任务，其中 {len(significant_tasks)} 个在 {correction_label} 跨模型校正后达到显著。"
                ),
                "该汇总用于定位值得进一步解释的任务，不应脱离具体模型、效应量和研究设计形成统一因果结论。",
            ],
            limitations=[
                (
                    "同时检验多个任务会增加偶然显著风险；本次不校正选择必须在报告中明确披露，不能把逐任务显著误写成已控制整体误报率。"
                    if correction == "none"
                    else "同时检验多个任务会增加偶然显著风险；未校正的原始 p 值不能代替预先定义的跨模型判断规则。"
                ),
                "界面中的规范表格可折叠查看；表格、下载文件与 canonical JSON 均保留本次完整任务结果。",
            ],
            tables=tables,
        )

    statistical = payload.get("result", payload)
    method = statistical.get("method", {})
    design = statistical.get("design", {})
    alpha = float(statistical.get("alpha", 0.05) or 0.05)
    overview = [
        f"采用{method.get('label_zh', '统计方法')}分析当前数据。"
        + (f"模型公式为 {method.get('formula')}。" if method.get("formula") else "")
    ]
    overview.append("各设计单元的描述性统计见表1。")
    if method.get("research_question"):
        overview.append(str(method["research_question"]))

    data_design: list[str] = []
    if design.get("n_observations") is not None:
        data_design.append(
            f"分析使用 {design.get('n_observations')} 条观测"
            + (f"，涉及 {design.get('n_subjects')} 个对象。" if design.get("n_subjects") is not None else "。")
        )
    if design.get("dependent_vars"):
        data_design.append(f"因变量/联合响应为：{'、'.join(map(str, design['dependent_vars']))}。")
    if design.get("between_factors"):
        data_design.append(f"对象间分类因素为：{'、'.join(map(str, design['between_factors']))}。")
    if design.get("within_factors"):
        data_design.append(f"对象内重复因素为：{'、'.join(map(str, design['within_factors']))}。")

    descriptive_rows = list(statistical.get("descriptive_stats", []) or [])
    descriptive = [_normative_descriptive_sentence(row) for row in descriptive_rows]
    if not descriptive:
        descriptive.append("当前结果未提供可单列的描述性统计；不得据此补造组均值或标准差。")

    assumptions: list[str] = []
    for item in statistical.get("diagnostics", []) or []:
        status = "未提示明显违背" if item.get("passed") is True else "需要关注" if item.get("passed") is False else "仅作提示"
        detail = str(item.get("detail") or "").strip()
        assumptions.append(
            f"{item.get('test_name', '诊断')}：{status}"
            + (f"（p={_fmt(item['p_value'], 6)}）" if item.get("p_value") is not None else "")
            + (f"。{detail}" if detail else "。")
        )
    if not assumptions:
        assumptions.append("结果中未提供独立诊断检验；相关分布、独立性和模型假设仍需结合研究设计复核。")

    primary = list(statistical.get("primary_tests", []) or [])
    omnibus = sorted(
        list(statistical.get("omnibus_tests", []) or []),
        key=lambda item: str(item.get("effect", "")).count("×"),
        reverse=True,
    )
    controlled_sections = _normative_controlled_sections(statistical, alpha=alpha)
    inference = [
        "多变量或总体推断检验结果见表2。",
        *controlled_sections["inference"],
    ]
    follow_up = [
        "单变量跟进、简单效应与具体比较见表3。",
        *controlled_sections["follow_up"],
    ]
    significant_interactions = list(controlled_sections["significant_interactions"])

    effects: list[str] = []
    for item in statistical.get("effect_sizes", []) or []:
        effects.append(
            f"{item.get('measure', '效应量')}={_fmt(item.get('value'))}"
            + (f"，95% CI [{_fmt(item.get('ci_lower'))}, {_fmt(item.get('ci_upper'))}]" if item.get("ci_lower") is not None and item.get("ci_upper") is not None else "")
            + (f"。{item.get('interpretation')}" if item.get("interpretation") else "。")
        )
    if not effects:
        if any(item.get("eta_sq_p") is not None for item in [*primary, *omnibus]):
            effects.append("总体检验提供的偏 η² 已与相应 F 检验一并报告；应结合其大小判断实际重要性。")
        else:
            effects.append("结果中未单列效应量或区间估计，不应仅凭 p 值判断实际重要性。")

    if significant_interactions:
        conclusion = [
            f"检测到显著交互（{'、'.join(significant_interactions)}）；结论应优先依据通过父检验门槛且经校正的简单效应和条件内比较，避免脱离交互概括边际主效应。"
        ]
    else:
        significant = [
            item for item in [*primary, *controlled_sections["decision_rows"]]
            if _result_row_is_significant(item, alpha=alpha)
        ]
        conclusion = [
            f"在 α={_fmt(alpha, 3)} 下，"
            + (f"有统计证据支持以下效应：{'、'.join(str(item.get('effect', '总体效应')) for item in significant)}。" if significant else "当前总体检验均未达到统计显著，现有数据提供的差异或关联证据不足。")
        ]

    limitations = list(dict.fromkeys(
        [str(item) for item in (statistical.get("warnings", []) or [])]
        + [str(item) for item in (statistical.get("report_constraints", []) or [])]
        + [str(item) for item in (method.get("report_constraints", []) or [])]
        + ["统计显著性不等于实际重要性；因果解释取决于研究设计，而不是 p 值本身。"]
    ))
    ordered_comparisons = _ordered_comparisons_from_result(result)
    return NormativeResultReport(
        title=title,
        analysis_overview=overview,
        data_and_design=data_design or ["结果中未记录完整的数据与设计摘要。"],
        descriptive_statistics=descriptive,
        assumption_review=assumptions,
        inferential_results=inference,
        follow_up_results=follow_up,
        effect_sizes_and_uncertainty=effects,
        ordered_comparisons=ordered_comparisons or [
            "当前结果没有至少两个可比较组的均值、边际均值或比例；不根据 p 值大小推造 A > B > C。"
        ],
        conclusion=conclusion,
        limitations=limitations,
        tables=_normative_report_tables(statistical, method.get("label_zh", "统计分析")),
    )


_REPORT_COLUMN_LABELS = {
    "task_id": "任务 ID", "factor_combination": "组合名称", "factor_columns": "组合因素", "combination_order": "组合阶数",
    "dependent_variable": "因变量", "dependent_variables": "联合因变量",
    "subset_key": "任务标识", "task_context": "任务条件", "n_rows": "有效行数", "status": "状态", "error": "失败原因",
    "outcome": "因变量", "dv": "因变量", "effect": "效应", "group": "组别",
    "factor": "因素", "context": "条件", "analysis_stage": "检验层级", "n": "n", "count": "n",
    "mean": "M", "sd": "SD", "se": "SE", "statistic_name": "统计量",
    "mean_sd": "M ± SD",
    "statistic_value": "统计量值", "df_num": "分子 df", "df_den": "分母 df",
    "sum_sq": "平方和 SS", "mean_sq": "均方 MS",
    "f_value": "F", "p_value": "p", "p_adjusted": "校正后 p",
    "p_adjusted_across_tasks": "跨模型校正 p", "p_adjust_method": "跨模型校正方法",
    "raw_conclusion": "校正前显著性", "conclusion": "结论", "result_type": "结果类型", "significant_adjusted": "跨模型判断显著",
    "eta_sq_p": "偏 η²", "correction": "校正方法", "contrast": "比较",
    "estimate": "估计差", "ci_lower": "CI 下限", "ci_upper": "CI 上限",
    "fixed_factor": "固定因素", "fixed_level": "固定水平",
    "record_type": "记录类型", "effect_size_source": "效应量来源",
    "effect_size_name": "效应量", "effect_size_value": "效应量值",
    "effect_size_summary": "效应量（含区间）",
    "effect_size_interpretation": "效应解释",
}


def _table_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return _fmt(value, 6)
    if isinstance(value, str):
        return {
            "completed": "完成",
            "failed": "失败",
            "test": "推断检验",
            "holm": "Holm",
            "bonferroni": "Bonferroni",
            "fdr_bh": "Benjamini-Hochberg FDR",
            "none": "不校正",
        }.get(value, value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _rows_table(title: str, rows: list[dict[str, Any]], preferred: list[str]) -> NormativeReportTable | None:
    if not rows:
        return None
    present = {key for row in rows for key in row}
    columns = [key for key in preferred if key in present]
    # 异构后续检验行不能只参考第一行，否则简单效应或比较特有字段会静默丢失。
    for row in rows:
        columns.extend(key for key in row if key in present and key not in columns)
    # 只保留适合正式报告的核心列，内部布尔标记和重复元数据不进入表格。
    columns = [key for key in columns if key not in {"is_significant", "significant", "significance_level", "ss_type", "interpretation", "adjustments"}]
    return NormativeReportTable(
        title=title,
        columns=[_REPORT_COLUMN_LABELS.get(key, key) for key in columns],
        rows=[[_table_value(row.get(key)) for key in columns] for row in rows],
    )


def _table_or_empty(
    title: str, rows: list[dict[str, Any]], preferred: list[str]
) -> NormativeReportTable:
    table = _rows_table(title, rows, preferred)
    if table is not None:
        return table
    return NormativeReportTable(
        title=title,
        columns=[_REPORT_COLUMN_LABELS.get(key, key) for key in preferred],
        rows=[],
    )


def _descriptive_table_rows(
    statistical: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """按参照报告把 MANOVA 的每个响应写为 M ± SD，保留因素标签与 n。"""

    raw_rows = list(statistical.get("descriptive_stats", []) or [])
    design = dict(statistical.get("design", {}) or {})
    factors = [
        str(item) for item in [
            *(design.get("between_factors", []) or []),
            *(design.get("within_factors", []) or []),
        ]
    ]
    outcomes = [str(item) for item in (design.get("dependent_vars", []) or [])]
    rows: list[dict[str, Any]] = []
    if _is_manova_result(statistical) and outcomes:
        for source in raw_rows:
            row = {factor: source.get(factor) for factor in factors if factor in source}
            row["n"] = source.get("n", source.get("count"))
            for outcome in outcomes:
                mean = source.get(f"{outcome}_mean")
                sd = source.get(f"{outcome}_sd")
                if mean is not None or sd is not None:
                    row[outcome] = f"{_fmt(mean)} ± {_fmt(sd)}"
            if len(row) > 1:
                rows.append(row)
        return rows, [*factors, "n", *outcomes]

    for source in raw_rows:
        row = dict(source)
        if source.get("mean") is not None or source.get("sd") is not None:
            row["mean_sd"] = f"{_fmt(source.get('mean'))} ± {_fmt(source.get('sd'))}"
            row.pop("mean", None)
            row.pop("sd", None)
        rows.append(row)
    preferred = [*factors, "outcome", "factor", "group", "n", "count", "mean_sd", "se"]
    return rows, preferred


def _canonical_effect_measure(value: Any) -> str:
    text = str(value or "效应量").strip()
    compact = text.casefold().replace("_", " ").replace("-", " ")
    compact = " ".join(compact.split())
    aliases = {
        "η²p": "偏 η²",
        "partial eta squared": "偏 η²",
        "partial eta square": "偏 η²",
        "eta squared partial": "偏 η²",
        "η²": "η²",
        "eta squared": "η²",
        "omega squared": "ω²",
        "ω²": "ω²",
        "cohen's d": "Cohen's d",
        "cohens d": "Cohen's d",
        "hedges' g": "Hedges' g",
        "hedges g": "Hedges' g",
    }
    return aliases.get(compact, aliases.get(text, text))


def _measure_and_effect(value: Any) -> tuple[str, str]:
    text = str(value or "效应量").strip()
    for separator in (":", "："):
        if separator in text:
            measure, effect = text.split(separator, 1)
            return _canonical_effect_measure(measure), effect.strip()
    if text.endswith(")") and " (" in text:
        measure, effect = text.rsplit(" (", 1)
        canonical = _canonical_effect_measure(measure)
        if canonical in {"偏 η²", "η²", "ω²"}:
            return canonical, effect[:-1].strip()
    return _canonical_effect_measure(text), ""


def _effect_value_signature(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{numeric:.12g}" if math.isfinite(numeric) else str(numeric)


def _effect_size_table_rows(statistical: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect effect sizes with their inferential effect whenever it is known."""

    rows: list[dict[str, Any]] = []
    seen_with_effect: set[tuple[str, str, str]] = set()
    seen_measure_values: set[tuple[str, str]] = set()

    def add(
        *,
        effect: Any,
        measure: Any,
        value: Any,
        source: str,
        ci_lower: Any = None,
        ci_upper: Any = None,
        interpretation: Any = "",
    ) -> None:
        if value is None:
            return
        canonical_measure, embedded_effect = _measure_and_effect(measure)
        effect_label = str(effect or embedded_effect or "总体/汇总").strip()
        signature = (
            effect_label,
            canonical_measure,
            _effect_value_signature(value),
        )
        if signature in seen_with_effect:
            return
        seen_with_effect.add(signature)
        seen_measure_values.add((canonical_measure, signature[2]))
        row = {
            "record_type": "效应量",
            "effect": effect_label,
            "effect_size_source": source,
            "effect_size_name": canonical_measure,
            "effect_size_value": value,
        }
        if ci_lower is not None:
            row["ci_lower"] = ci_lower
        if ci_upper is not None:
            row["ci_upper"] = ci_upper
        if interpretation:
            row["effect_size_interpretation"] = interpretation
        rows.append(row)

    inferential_rows = [
        *list(statistical.get("primary_tests", []) or []),
        *list(statistical.get("omnibus_tests", []) or []),
    ]
    known_effects = list(dict.fromkeys(
        str(item.get("effect") or "").strip()
        for item in inferential_rows
        if isinstance(item, dict) and str(item.get("effect") or "").strip()
    ))
    default_effect = known_effects[0] if len(known_effects) == 1 else ""

    for item in statistical.get("omnibus_tests", []) or []:
        if not isinstance(item, dict):
            continue
        for field, measure in (
            ("eta_sq", "η²"),
            ("eta_sq_p", "偏 η²"),
            ("omega_sq", "ω²"),
        ):
            if field in item:
                add(
                    effect=item.get("effect"),
                    measure=measure,
                    value=item.get(field),
                    source="总体检验",
                )

    for item in statistical.get("effect_sizes", []) or []:
        if not isinstance(item, dict):
            continue
        measure, embedded_effect = _measure_and_effect(item.get("measure"))
        measure_value = (measure, _effect_value_signature(item.get("value")))
        # 统一结果常同时在总体/主要检验和 effect_sizes 中保存同一估计；规范表只保留一次。
        if measure_value in seen_measure_values and not embedded_effect:
            continue
        add(
            effect=embedded_effect or default_effect,
            measure=measure,
            value=item.get("value"),
            source="效应量汇总",
            ci_lower=item.get("ci_lower"),
            ci_upper=item.get("ci_upper"),
            interpretation=item.get("interpretation"),
        )

    # 主要检验中的区间有时属于原始差值而非标准化效应量，因此最后补入；
    # 若 effect_sizes 已提供同一效应量及其专属区间，这里会被去重。
    for item in statistical.get("primary_tests", []) or []:
        if not isinstance(item, dict):
            continue
        add(
            effect=item.get("effect"),
            measure=item.get("effect_size_name"),
            value=item.get("effect_size_value"),
            source="主要检验",
            ci_lower=item.get("ci_lower"),
            ci_upper=item.get("ci_upper"),
        )
    return rows


def _normalized_effect_key(value: Any) -> str:
    return (
        str(value or "").casefold().replace(" ", "").replace("*", "×").replace(":", "×")
    )


def _effect_size_summary(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('effect_size_name') or '效应量'}={_fmt(row.get('effect_size_value'), 6)}"
    ]
    if row.get("ci_lower") is not None and row.get("ci_upper") is not None:
        parts.append(
            f"95% CI [{_fmt(row.get('ci_lower'), 6)}, {_fmt(row.get('ci_upper'), 6)}]"
        )
    if row.get("effect_size_interpretation"):
        parts.append(str(row["effect_size_interpretation"]))
    return "，".join(parts)


def _ai_report_structure_failure_warning(error: Any) -> str:
    """Return a useful, non-technical reason when structured prose cannot be applied."""

    detail = str(error or "").casefold()
    if "json parsing failed" in detail:
        reason = "AI 连续两次返回的文字结构不完整"
    elif "empty" in detail or "未包含可读取正文" in detail:
        reason = "AI 连续两次未返回可读取的文字正文"
    elif detail:
        reason = "AI 连续两次未完成文字总结请求"
    else:
        reason = "AI 连续两次未返回符合文字报告结构的内容"
    return f"{reason}，因此未应用；本地排序和三张规范表仍可正常使用。"


_AI_REPORT_INTERNAL_TERMS = {
    "read_only_ordering": "本地只读排序",
    "ordered_comparisons": "本地只读排序",
    "ai_evidence_packet": "本地证据包",
    "normative_tables": "三张规范表",
    "canonical_result": "原始统计结果",
}


def _normalize_ai_report_language(report: dict[str, Any]) -> None:
    """Remove implementation vocabulary from AI-authored user-facing prose."""

    prose_fields = (
        "analysis_overview", "data_and_design", "descriptive_statistics",
        "assumption_review", "inferential_results", "follow_up_results",
        "effect_sizes_and_uncertainty", "conclusion", "limitations",
    )
    for field in prose_fields:
        normalized: list[str] = []
        for value in report.get(field, []) or []:
            text = str(value).strip()
            for internal, readable in _AI_REPORT_INTERNAL_TERMS.items():
                text = text.replace(internal, readable)
            text = " ".join(text.split())
            if text:
                normalized.append(text)
        report[field] = normalized


def _task_context(task: dict[str, Any]) -> str:
    info = dict(task.get("subset_info", {}) or {})
    parts = [
        f"{key}={value}"
        for key, value in info.items()
        if key not in {"task_id", "combination_order"}
        and value not in (None, "")
    ]
    if parts:
        return "；".join(parts)
    return str(task.get("subset_key") or "").strip()


def _enrich_inference_task_identity(
    inferential_rows: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Restore task ID/context on current and legacy batch overview rows."""

    identities: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        info = dict(task.get("subset_info", {}) or {})
        identities.append({
            "task_id": info.get("task_id", index),
            "task_context": _task_context(task),
            "conditions": {
                str(key): value
                for key, value in info.items()
                if key not in {"task_id", "combination_order"}
                and value not in (None, "")
            },
        })

    enriched: list[dict[str, Any]] = []
    for source in inferential_rows:
        row = dict(source)
        row_task_id = row.get("task_id")
        candidates = [
            identity for identity in identities
            if row_task_id not in (None, "")
            and str(identity["task_id"]) == str(row_task_id)
        ]
        if not candidates and row_task_id in (None, ""):
            for identity in identities:
                comparable = [
                    key for key in identity["conditions"]
                    if row.get(key) not in (None, "")
                ]
                if comparable and all(
                    str(row.get(key)) == str(identity["conditions"][key])
                    for key in comparable
                ):
                    candidates.append(identity)
        if len(candidates) == 1:
            row.setdefault("task_id", candidates[0]["task_id"])
            row.setdefault("task_context", candidates[0]["task_context"])
        enriched.append(row)
    return enriched


def _merge_effect_sizes_into_inference(
    inferential_rows: list[dict[str, Any]],
    effect_size_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach effect sizes to their inferential row; retain ambiguous items as supplements."""

    rows = [dict(row) for row in inferential_rows]
    assigned: dict[int, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []

    def same_task(effect_row: dict[str, Any], inference_row: dict[str, Any]) -> bool:
        effect_task = str(effect_row.get("task_id") or "")
        inference_task = str(inference_row.get("task_id") or "")
        if effect_task and inference_task:
            return effect_task == inference_task
        effect_context = str(effect_row.get("task_context") or "").strip()
        inference_contexts = {
            str(inference_row.get(name) or "").strip()
            for name in ("task_context", "factor_combination", "subset_key")
        }
        return not effect_context or effect_context in inference_contexts

    for effect_row in effect_size_rows:
        candidates = [
            index for index, row in enumerate(rows) if same_task(effect_row, row)
        ]
        effect_key = _normalized_effect_key(effect_row.get("effect"))
        exact = [
            index for index in candidates
            if effect_key and _normalized_effect_key(rows[index].get("effect")) == effect_key
        ]
        target = exact[0] if len(exact) == 1 else candidates[0] if len(candidates) == 1 else None
        if target is None:
            unassigned.append(effect_row)
        else:
            assigned.setdefault(target, []).append(effect_row)

    for index, row in enumerate(rows):
        summaries = list(dict.fromkeys(
            _effect_size_summary(item) for item in assigned.get(index, [])
        ))
        if summaries:
            row["effect_size_summary"] = "；".join(summaries)
        for legacy_field in (
            "eta_sq", "eta_sq_p", "omega_sq", "effect_size_name", "effect_size_value"
        ):
            row.pop(legacy_field, None)

    for effect_row in unassigned:
        rows.append({
            **{
                key: effect_row[key]
                for key in ("task_id", "task_context")
                if effect_row.get(key) not in (None, "")
            },
            "analysis_stage": "补充效应量",
            "effect": effect_row.get("effect") or "总体/汇总",
            "effect_size_summary": _effect_size_summary(effect_row),
        })
    return rows


def _inferential_table_rows(statistical: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    omnibus = sorted(
        list(statistical.get("omnibus_tests", []) or []),
        key=lambda row: str(row.get("effect", "")).count("×"),
        reverse=True,
    )
    if _is_manova_result(statistical):
        primary_rows, primary_label = _primary_manova_rows(statistical, omnibus)
        title = "表2. 多变量总体检验结果"
        if primary_label:
            title += f"（{primary_label}）"
        return primary_rows, title
    primary = list(statistical.get("primary_tests", []) or [])
    return [*primary, *omnibus], "表2. 主要与总体推断检验结果"


def _follow_up_table_rows(statistical: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in statistical.get("follow_up_tests", []) or []:
        rows.append({"analysis_stage": "单变量跟进", **dict(item)})
    for item in statistical.get("simple_effects", []) or []:
        rows.append({"analysis_stage": "简单效应", **dict(item)})
    for item in statistical.get("contrasts", []) or []:
        rows.append({"analysis_stage": "事后/计划比较", **dict(item)})
    return rows


def _normative_report_tables(
    statistical: dict[str, Any], method_label: str
) -> list[NormativeReportTable]:
    """固定输出参照规范的三张主表，不再按结果类型动态增加表号。"""

    descriptive_rows, descriptive_columns = _descriptive_table_rows(statistical)
    effect_size_rows = _effect_size_table_rows(statistical)
    inferential_rows, inferential_title = _inferential_table_rows(statistical)
    inferential_rows = _merge_effect_sizes_into_inference(
        inferential_rows, effect_size_rows
    )
    is_manova = _is_manova_result(statistical)
    if not is_manova:
        inferential_title = f"表2. {method_label}结果汇总"
    table1_title = (
        "表1. 各设计单元多因变量描述性统计（M ± SD）"
        if is_manova
        else "表1. 各组描述性统计（M ± SD）"
    )
    table3_title = (
        "表3. 各因变量的单变量检验与后续比较结果（主体间效应检验）"
        if is_manova
        else "表3. 单变量、简单效应与事后比较结果"
    )
    return [
        _table_or_empty(table1_title, descriptive_rows, descriptive_columns),
        _table_or_empty(
            inferential_title,
            inferential_rows,
            [
                "effect", "statistic_name", "statistic_value", "df_num", "df_den",
                "f_value", "p_value", "effect_size_summary",
            ],
        ),
        _table_or_empty(
            table3_title,
            _follow_up_table_rows(statistical),
            [
                "analysis_stage", "outcome", "fixed_factor", "fixed_level", "effect",
                "contrast", "sum_sq", "df_num", "mean_sq", "df_den", "f_value", "estimate", "se", "df",
                "p_value", "p_adjusted", "eta_sq_p", "ci_lower", "ci_upper", "correction",
            ],
        ),
    ]


def _normative_batch_report_tables(
    *,
    tasks: list[dict[str, Any]],
    overview: list[dict[str, Any]],
    method_label: str,
    include_cross_task_adjustment: bool = True,
) -> list[NormativeReportTable]:
    """把批量任务纵向合并到同一组三表，避免每个任务重复生成三套表号。"""

    descriptive_rows: list[dict[str, Any]] = []
    inferential_rows = _enrich_inference_task_identity(
        [dict(row) for row in overview], tasks
    )
    if not include_cross_task_adjustment:
        for row in inferential_rows:
            if not row.get("raw_conclusion"):
                if row.get("status") == "failed" or row.get("error"):
                    row["raw_conclusion"] = "执行失败"
                elif row.get("significant") is True:
                    row["raw_conclusion"] = "原始显著"
                elif row.get("significant") is False:
                    row["raw_conclusion"] = "原始不显著"
            row.pop("p_adjusted_across_tasks", None)
            row.pop("significant_adjusted", None)
            row.pop("conclusion", None)
    follow_up_rows: list[dict[str, Any]] = []
    batch_effect_size_rows: list[dict[str, Any]] = []
    descriptive_preferred: list[str] = ["task_id", "task_context"]
    for index, task in enumerate(tasks, start=1):
        info = dict(task.get("subset_info", {}) or {})
        task_id = info.get("task_id", index)
        task_context = _task_context(task)
        if task.get("error"):
            if not any(row.get("task_id") == task_id for row in inferential_rows):
                inferential_rows.append({
                    "task_id": task_id,
                    "task_context": task_context,
                    "status": "failed",
                    "error": task.get("error"),
                })
            continue
        statistical = dict(task.get("result", {}) or {})
        task_descriptive, task_columns = _descriptive_table_rows(statistical)
        task_effect_sizes = _effect_size_table_rows(statistical)
        batch_effect_size_rows.extend(
            {"task_id": task_id, "task_context": task_context, **row}
            for row in task_effect_sizes
        )
        for row in task_descriptive:
            descriptive_rows.append({"task_id": task_id, "task_context": task_context, **row})
        for column in task_columns:
            if column not in descriptive_preferred:
                descriptive_preferred.append(column)
        if not overview:
            task_inference, _ = _inferential_table_rows(statistical)
            inferential_rows.extend(
                {"task_id": task_id, "task_context": task_context, **row}
                for row in task_inference
            )
        follow_up_rows.extend(
            {"task_id": task_id, "task_context": task_context, **row}
            for row in _follow_up_table_rows(statistical)
        )

    inferential_rows = _merge_effect_sizes_into_inference(
        inferential_rows, batch_effect_size_rows
    )

    return [
        _table_or_empty(
            "表1. 各任务与设计单元描述性统计（M ± SD）",
            descriptive_rows,
            descriptive_preferred,
        ),
        _table_or_empty(
            f"表2. {method_label}多模型总体检验结果",
            inferential_rows,
            [
                "task_id", "task_context", "factor_combination", "factor_columns",
                "dependent_variable", "dependent_variables", "effect", "statistic_name",
                "statistic_value", "df_num", "df_den", "f_value", "p_value",
                "effect_size_summary",
                "raw_conclusion",
                *(
                    ["p_adjusted_across_tasks", "p_adjust_method", "conclusion"]
                    if include_cross_task_adjustment
                    else []
                ),
                "status", "error",
            ],
        ),
        _table_or_empty(
            "表3. 各任务单变量与后续检验结果",
            follow_up_rows,
            [
                "task_id", "task_context", "analysis_stage", "outcome", "fixed_factor",
                "fixed_level", "effect", "contrast", "df_num", "df_den", "f_value",
                "estimate", "p_value", "p_adjusted", "eta_sq_p", "correction",
            ],
        ),
    ]


def _normative_descriptive_sentence(row: dict[str, Any]) -> str:
    """把描述统计行写成可直接引用的 M、SD、n 叙述，并保留原始因素标签。"""

    outcome = row.get("outcome") or row.get("dv") or row.get("dependent_variable")
    labels: list[str] = []
    levels = row.get("levels")
    if isinstance(levels, dict):
        labels.extend(f"{key}={value}" for key, value in levels.items())
    factor = row.get("factor")
    group = row.get("group")
    if factor is not None and group is not None:
        labels.append(f"{factor}={group}")
    elif group is not None:
        labels.append(str(group))
    if row.get("context"):
        labels.append(str(row["context"]))

    metadata_keys = {
        "outcome", "dv", "dependent_variable", "levels", "factor", "group", "context",
        "n", "count", "mean", "sd", "se", "proportion", "success", "ci_lower", "ci_upper",
        "is_significant", "significant", "source", "method", "letters",
    }
    for key, value in row.items():
        if key not in metadata_keys and value is not None and not isinstance(value, (dict, list)):
            labels.append(f"{key}={value}")
    labels = list(dict.fromkeys(labels))

    metrics: list[str] = []
    sample_size = row.get("n", row.get("count"))
    if sample_size is not None:
        metrics.append(f"n={_fmt(sample_size, 0)}")
    if row.get("mean") is not None:
        metrics.append(f"M={_fmt(row.get('mean'))}")
    if row.get("sd") is not None:
        metrics.append(f"SD={_fmt(row.get('sd'))}")
    if row.get("se") is not None:
        metrics.append(f"SE={_fmt(row.get('se'))}")
    if row.get("success") is not None:
        metrics.append(f"成功数={_fmt(row.get('success'), 0)}")
    if row.get("proportion") is not None:
        metrics.append(f"比例={_fmt(row.get('proportion'))}")

    subject = "、".join(labels) or "当前分析单元"
    if outcome:
        subject = f"{outcome}｜{subject}"
    return f"{subject}：{'，'.join(metrics) if metrics else '描述性结果见规范表格'}。"


def _normative_test_sentence(item: dict[str, Any], *, alpha: float) -> str:
    effect = str(item.get("effect") or "总体效应")
    p_value = item.get("p_value")
    significant = item.get("is_significant")
    if significant is None and p_value is not None:
        significant = float(p_value) < alpha
    conclusion = "达到统计显著" if significant is True else "未达到统计显著" if significant is False else "未提供显著性判断"
    statistic_name = str(item.get("statistic_name") or "F")
    parts = [f"{effect}{conclusion}"]
    if item.get("f_value") is not None and item.get("df_num") is not None and item.get("df_den") is not None:
        parts.append(
            f"{statistic_name}={_fmt(item.get('statistic_value'), 6)}，" if item.get("statistic_value") is not None and statistic_name != "F" else ""
        )
        parts.append(f"F({_fmt(item.get('df_num'), 2)}, {_fmt(item.get('df_den'), 2)})={_fmt(item.get('f_value'))}")
    elif item.get("statistic_value") is not None:
        parts.append(f"{statistic_name}={_fmt(item.get('statistic_value'))}")
        if item.get("df_num") is not None:
            parts.append(f"df={_fmt(item.get('df_num'), 2)}")
    if p_value is not None:
        parts.append(f"p={_fmt(p_value, 6)}")
    if item.get("eta_sq_p") is not None:
        parts.append(f"偏 η²={_fmt(item.get('eta_sq_p'))}")
    return "，".join(part for part in parts if part) + "。"


def _evidence_only_normative_report(
    deterministic: NormativeResultReport,
) -> NormativeResultReport:
    """Keep deterministic ordering and tables while deliberately omitting prose."""

    return NormativeResultReport(
        title=deterministic.title,
        ordered_comparisons=list(deterministic.ordered_comparisons),
        tables=[table.model_copy(deep=True) for table in deterministic.tables],
    )


def _render_normative_evidence_report(report: NormativeResultReport) -> str:
    lines = [f"# {report.title}", ""]
    if report.ordered_comparisons:
        lines.extend(["## 本地只读排序（A > B > C）", ""])
        for comparison in report.ordered_comparisons:
            lines.extend([f"- {str(comparison).strip()}", ""])
    lines.extend(["## 三张规范统计表", ""])
    for table in report.tables:
        lines.extend([f"### {table.title}", ""])
        if not table.columns or not table.rows:
            lines.extend(["无可报告数据。", ""])
            continue
        safe_columns = [str(item).replace("|", "\\|") for item in table.columns]
        lines.extend([
            "| " + " | ".join(safe_columns) + " |",
            "| " + " | ".join("---" for _ in safe_columns) + " |",
        ])
        for row in table.rows:
            cells = [str(item).replace("|", "\\|").replace("\n", " ") for item in row]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines.extend([
        "---",
        "",
        "> 本页仅包含 DataWork 本地统计内核生成的只读排序和规范表，不包含内置文字报告。",
        "",
    ])
    return "\n".join(lines)


def _render_normative_report(report: NormativeResultReport) -> str:
    sections = [
        ("一、研究目的、统计方法与设计", [*report.analysis_overview, *report.data_and_design]),
        ("二、描述性统计", report.descriptive_statistics),
        ("三、前提与模型诊断", report.assumption_review),
        ("四、交互作用、主效应与整体检验", report.inferential_results),
        ("五、后续分析与具体差异", report.follow_up_results),
        (
            "六、效应量、结论与解释边界",
            [*report.effect_sizes_and_uncertainty, *report.conclusion, *report.limitations],
        ),
    ]
    lines = [f"# {report.title}", ""]
    for heading, paragraphs in sections:
        lines.extend([f"## {heading}", ""])
        if paragraphs:
            for paragraph in paragraphs:
                lines.extend([str(paragraph).strip(), ""])
        else:
            lines.extend(["本节没有可报告的信息。", ""])
    lines.extend([
        "---",
        "",
        "> 本页仅包含 AI 优化后的文字总结；只读排序与规范统计表请在本地证据页查看。统计数值来自 DataWork 计算核心。",
        "",
    ])
    return "\n".join(lines)


def _ai_authored_report_guard_text(report: NormativeResultReport) -> str:
    """Return only prose fields that an external model is allowed to author."""

    fields = (
        "analysis_overview",
        "data_and_design",
        "descriptive_statistics",
        "assumption_review",
        "inferential_results",
        "follow_up_results",
        "effect_sizes_and_uncertainty",
        "conclusion",
        "limitations",
    )
    return "\n".join(
        str(paragraph).strip()
        for field in fields
        for paragraph in getattr(report, field)
        if str(paragraph).strip()
    )


_AI_REPORT_PROSE_FIELDS = (
    "analysis_overview",
    "data_and_design",
    "descriptive_statistics",
    "assumption_review",
    "inferential_results",
    "follow_up_results",
    "effect_sizes_and_uncertainty",
    "conclusion",
    "limitations",
)

# 这些章节包含“哪些检验可以进入结论”的层级判断。AI 可以优化其他叙述，
# 但不得改写父检验门槛、交互优先级或事后比较触发条件。
_REPORT_HIERARCHY_CONTROL_FIELDS = (
    "inferential_results",
    "follow_up_results",
    "conclusion",
)


def _enforce_deterministic_report_controls(
    report_payload: dict[str, Any],
    fallback: NormativeResultReport,
    *,
    allow_prose_fallback: bool = True,
) -> list[str]:
    removed: list[str] = []
    fallback_inference = "\n".join(fallback.inferential_results)
    fallback_follow_up = "\n".join(fallback.follow_up_results)
    candidate_inference = "\n".join(
        str(item) for item in (report_payload.get("inferential_results", []) or [])
    )
    candidate_follow_up = "\n".join(
        str(item) for item in (report_payload.get("follow_up_results", []) or [])
    )
    candidate_conclusion = "\n".join(
        str(item) for item in (report_payload.get("conclusion", []) or [])
    )
    candidate_critical = "\n".join(
        [candidate_inference, candidate_follow_up, candidate_conclusion]
    )

    # MANOVA 的主要判据与父检验链、以及实际存在被高阶交互限定的效应，
    # 都必须逐项由本地结果决定，不能仅靠提示词约束模型措辞。
    force_inference = (
        "MANOVA 正文按预先指定" in fallback_inference
        or "该主效应受更高阶显著交互限定" in fallback_inference
        or "该低阶交互受更高阶显著交互限定" in fallback_inference
    )
    unsafe_hierarchy_phrases = (
        "忽略交互",
        "脱离交互",
        "直接独立解释",
        "仅依据主效应",
        "仅依据 A 主效应",
        "仅依据B主效应",
    )
    if any(phrase in candidate_critical for phrase in unsafe_hierarchy_phrases):
        force_inference = True

    # 一旦本地控制器实际拦截了跟进、简单效应、比较或两水平“事后检验”，
    # 后续分析段落整体使用确定性版本，防止 AI 又把被拦截行写回正文。
    force_follow_up = any(
        marker in fallback_follow_up
        for marker in (
            "正文不作推断",
            "正文已停止解释",
            "不另写成事后多重比较",
            "未满足显著父检验",
        )
    ) or "没有父检验依据" in candidate_follow_up

    if force_inference:
        if not allow_prose_fallback:
            if report_payload.get("inferential_results"):
                removed.append(_AI_REPORT_SECTION_LABELS["inferential_results"])
            if report_payload.get("conclusion"):
                removed.append(_AI_REPORT_SECTION_LABELS["conclusion"])
        report_payload["inferential_results"] = (
            list(fallback.inferential_results) if allow_prose_fallback else []
        )
        report_payload["conclusion"] = (
            list(fallback.conclusion) if allow_prose_fallback else []
        )
    elif allow_prose_fallback and "表2" not in candidate_inference:
        table_reference = next(
            (item for item in fallback.inferential_results if "表2" in item), ""
        )
        if table_reference:
            report_payload["inferential_results"] = [
                table_reference,
                *(report_payload.get("inferential_results", []) or []),
            ]
    if force_follow_up or "MANOVA 正文按预先指定" in fallback_inference:
        if not allow_prose_fallback and report_payload.get("follow_up_results"):
            removed.append(_AI_REPORT_SECTION_LABELS["follow_up_results"])
        report_payload["follow_up_results"] = (
            list(fallback.follow_up_results) if allow_prose_fallback else []
        )
    elif allow_prose_fallback and "表3" not in candidate_follow_up:
        table_reference = next(
            (item for item in fallback.follow_up_results if "表3" in item), ""
        )
        if table_reference:
            report_payload["follow_up_results"] = [
                table_reference,
                *(report_payload.get("follow_up_results", []) or []),
            ]

    candidate_overview = "\n".join(
        str(item) for item in (report_payload.get("analysis_overview", []) or [])
    )
    if allow_prose_fallback and "表1" not in candidate_overview:
        table_reference = next(
            (item for item in fallback.analysis_overview if "表1" in item), ""
        )
        if table_reference:
            report_payload["analysis_overview"] = [
                *(report_payload.get("analysis_overview", []) or []),
                table_reference,
            ]
    return list(dict.fromkeys(removed))


def _report_control_metadata() -> dict[str, Any]:
    return {
        "mode": "deterministic",
        "protected_sections": [
            _AI_REPORT_SECTION_LABELS.get(field, field)
            for field in _REPORT_HIERARCHY_CONTROL_FIELDS
        ],
        "rules": [
            "最高阶显著交互优先，受其限定的低阶效应不独立解释",
            "MANOVA 单变量跟进必须通过预先指定的多变量父检验",
            "简单效应和事后比较必须满足显著父检验及多重校正门槛",
            "两个水平只报告方向，不写成事后多重比较",
        ],
    }

_AI_REPORT_SECTION_LABELS = {
    "analysis_overview": "研究目的与统计方法",
    "data_and_design": "数据与研究设计",
    "descriptive_statistics": "描述性统计",
    "assumption_review": "前提与模型诊断",
    "inferential_results": "总体与主要推断结果",
    "follow_up_results": "后续分析与多重比较",
    "effect_sizes_and_uncertainty": "效应量与不确定性",
    "conclusion": "规范结论",
    "limitations": "解释边界与注意事项",
}


def _replace_unsafe_ai_report_sections(
    candidate: NormativeResultReport,
    fallback: NormativeResultReport,
    canonical: str,
) -> tuple[NormativeResultReport, list[str], list[str], dict[str, Any]]:
    """保留通过守卫的 AI 章节，并移除含不可信数值的章节。"""

    merged = candidate.model_dump(mode="json")
    replaced: list[str] = []
    kept: list[str] = []
    violations: list[str] = []
    section_guards: dict[str, dict[str, Any]] = {}

    for field in _AI_REPORT_PROSE_FIELDS:
        paragraphs = [
            str(item).strip()
            for item in getattr(candidate, field)
            if str(item).strip()
        ]
        if not paragraphs:
            merged[field] = []
            continue
        section_guard = guard_ai_output(
            "\n".join(paragraphs),
            result_json=canonical,
            strict_numeric=True,
        )
        section_guards[field] = section_guard
        if section_guard["passed"]:
            kept.append(_AI_REPORT_SECTION_LABELS[field])
            continue
        merged[field] = []
        replaced.append(_AI_REPORT_SECTION_LABELS[field])
        violations.extend(str(item) for item in section_guard.get("violations", []))

    # 排序与表格始终由本地统计结果生成，不属于 AI 可保留内容。
    merged["ordered_comparisons"] = list(fallback.ordered_comparisons)
    merged["tables"] = [item.model_dump(mode="json") for item in fallback.tables]
    unique_violations = list(dict.fromkeys(violations))
    filtered_guard = {
        "passed": False,
        "violations": unique_violations,
        "warnings": [],
        "sections": section_guards,
    }
    return NormativeResultReport.model_validate(merged), replaced, kept, filtered_guard


def _guard_failure_summary(guard: dict[str, Any]) -> str:
    violations = [str(item) for item in guard.get("violations", []) if str(item).strip()]
    if not violations:
        return "修复请求未返回可验证的 AI 叙述。"
    if any("未在统计结果中找到可追溯来源" in item for item in violations):
        category = "AI 叙述中仍有无法追溯到计算结果的数值"
    elif any("不匹配" in item or "自由度组合" in item for item in violations):
        category = "AI 叙述中的统计量、自由度、p 值或效应量与计算结果不一致"
    else:
        category = "AI 叙述违反了统计报告守卫规则"
    return f"{category}（{len(violations)} 项；可展开查看明细）。"


def _ai_report_guard_failure_response(
    local_evidence: NormativeResultReport,
    evidence_summary: dict[str, Any],
    guard: dict[str, Any],
    *,
    initial_guard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "ai_guard_failed",
        "report": local_evidence.model_dump(mode="json"),
        "report_markdown": _render_normative_evidence_report(local_evidence),
        "report_control": _report_control_metadata(),
        "evidence_summary": evidence_summary,
        "warning": (
            "AI 文字连续两次未通过统计数值一致性检查，未应用 AI 文字，也未使用内置文字回填；"
            f"本地排序和三张规范表未受影响。原因：{_guard_failure_summary(guard)}"
        ),
        "guard": guard,
        "guard_initial": initial_guard,
        "guard_attempts": 2,
    }


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)
