"""FastAPI 应用：无状态分析与本地持久工作区共用同一后端。"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import platform
import re
import shutil
import zipfile
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from datawork import __version__
from datawork.application.analysis_service import AnalysisService, ExecutionContext
from datawork.application.preflight_service import PreflightService
from datawork.application.report_service import ReportService
from datawork.application.ai_assistant_service import AIAssistantService, STEP_GUIDES
from datawork.application.dataset_service import DEFAULT_MAX_BYTES, DatasetService
from datawork.application.design_service import DesignService
from datawork.application.workspace_service import WorkspaceService
from datawork.ai.provider import ProviderKind
from datawork.ai.settings import AISettings, AISettingsService, PrivacyMode, SecretStorage
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan
from datawork.engine.batch import BatchAnalysisResult
from datawork.engine.result import StatisticalResult
from datawork.web.schemas import (
    AIAnalysisExplainRequest, AIExplainRequest, AIResultExplainRequest, AIResultReportRequest, AISettingsUpdate, InstantReportCreate, PlanClone, PlanCreate,
    PlanUpdate, ProjectCreate, ReportCreate, RunCompare,
)


MAX_UPLOAD_BYTES = DEFAULT_MAX_BYTES
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)
ALLOWED_BROWSER_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
]


def _package_version() -> str:
    return __version__


def create_app(*, workspace_root: str | Path | None = None) -> FastAPI:
    application = FastAPI(
        title="DataWork API",
        version=_package_version(),
        description="可复现的实验统计分析与项目工作区 API",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_BROWSER_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    dataset_service = DatasetService()
    design_service = DesignService()
    preflight_service = PreflightService()
    report_service = ReportService()
    workspace = WorkspaceService(workspace_root)
    ai_settings = AISettingsService(workspace.paths)
    ai_assistant = AIAssistantService(ai_settings)
    application.state.workspace = workspace
    application.state.ai_settings = ai_settings

    def batch_export_payload(export_id: str, result: BatchAnalysisResult, *, status: str, error: str = "", artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "export_id": export_id,
            "status": status,
            "status_url": f"/api/batch/exports/{export_id}/status",
            "error": error,
            "download_url": f"/api/batch/exports/{export_id}",
            "standardized_report": {
                "schema_version": "datawork.standard-report.v1",
                "download_url": f"/api/batch/exports/{export_id}/zip",
                "xlsx_download_url": f"/api/batch/exports/{export_id}/xlsx",
                "markdown_download_url": f"/api/batch/exports/{export_id}/markdown",
                "json_download_url": f"/api/batch/exports/{export_id}/json",
                "artifacts": artifacts or [],
            },
            "sheet_name": "结果总览",
            "sheet_names": [
                "结果总览",
                *[f"批次_{index:03d}" for index in range(1, len(result.results) + 1)],
                "失败与警告",
                "分析设置",
            ],
        }

    def write_batch_export_status(export_id: str, payload: dict[str, Any]) -> None:
        export_root = workspace.paths.reports / "generic_batch_exports"
        status_path = export_root / export_id / "status.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = status_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        temporary.replace(status_path)

    def generate_batch_export_artifacts(export_id: str, result: BatchAnalysisResult) -> None:
        export_dir = workspace.paths.reports / "generic_batch_exports"
        export_path = export_dir / f"{export_id}.xlsx"
        report_dir = export_dir / export_id
        try:
            bundle = report_service.generate(result, report_dir, title="规范化批量分析报告")
            generated_xlsx = report_dir / "results.xlsx"
            export_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated_xlsx, export_path)
            archive_path = export_dir / f"{export_id}.zip"
            temporary_archive = archive_path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for artifact in bundle.artifacts:
                    artifact_path = Path(artifact.path)
                    archive.write(artifact_path, arcname=artifact_path.relative_to(report_dir).as_posix())
            temporary_archive.replace(archive_path)
            write_batch_export_status(
                export_id,
                batch_export_payload(
                    export_id,
                    result,
                    status="ready",
                    artifacts=[item.model_dump(mode="json") for item in bundle.artifacts],
                ),
            )
        except Exception as exc:
            LOGGER.exception("批量导出后台生成失败: %s", export_id)
            write_batch_export_status(
                export_id,
                batch_export_payload(export_id, result, status="failed", error=str(exc)),
            )

    def require_ai_access(request: Request) -> None:
        bind_host = os.getenv("DATAWORK_BIND_HOST", "127.0.0.1")
        local_bind = bind_host in {"127.0.0.1", "localhost", "::1"}
        explicitly_allowed = os.getenv("DATAWORK_ALLOW_REMOTE_AI") == "1"
        if not local_bind and not explicitly_allowed:
            raise DataWorkError(
                ErrorCode.AI_UNAVAILABLE,
                "远程 AI 功能默认关闭。共享部署必须先配置认证，再由管理员使用 --allow-remote-ai 启用。",
                status_code=403,
            )

    @application.exception_handler(DataWorkError)
    async def handle_datawork_error(_request, exc: DataWorkError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_sanitize({
                "detail": exc.message,
                "error": exc.to_payload().model_dump(mode="json"),
            }),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("DataWork 未预期错误: %s %s", request.method, request.url.path, exc_info=exc)
        message = "程序在处理当前请求时遇到未预期错误。你的选择和原始文件不会被修改；请返回检查数据与参数后重试。"
        return JSONResponse(
            status_code=500,
            content=_sanitize({
                "detail": message,
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": message,
                    "issues": [],
                    "details": {"path": request.url.path},
                },
            }),
        )

    @application.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": _package_version(),
            "python": platform.python_version(),
            "platform": platform.system(),
            "workspace": workspace.info(include_paths=False),
        }

    @application.get("/api/capabilities")
    def capabilities() -> dict[str, Any]:
        methods = list_methods()
        return {
            "version": _package_version(),
            "api_contract": "phase3-v1",
            "statistics": {
                "method_count": len(methods),
                "runnable_method_count": sum(1 for item in methods if item.is_runnable),
                "estimated_marginal_means": True,
                "sphericity_corrections": ["greenhouse_geisser", "huynh_feldt"],
                "mixed_anova": True,
                "random_slopes": True,
                "diagnostic_plots": True,
            },
            "desktop": {
                "sidecar_ready": True,
                "health_endpoint": "/api/health",
                "shutdown_managed_by_parent": True,
            },
        }

    # ── AI 助手与界面化设置 ─────────────────────────────────────

    @application.get("/api/ai/providers")
    def ai_providers() -> list[dict[str, Any]]:
        return _sanitize(ai_settings.provider_catalog())

    @application.get("/api/ai/status")
    def ai_status() -> dict[str, Any]:
        payload = ai_settings.public_status()
        bind_host = os.getenv("DATAWORK_BIND_HOST", "127.0.0.1")
        payload["access_scope"] = "remote_enabled" if os.getenv("DATAWORK_ALLOW_REMOTE_AI") == "1" else "local_only"
        payload["bind_host"] = bind_host
        return _sanitize(payload)

    @application.put("/api/ai/settings")
    def update_ai_settings(request: AISettingsUpdate, http_request: Request) -> dict[str, Any]:
        require_ai_access(http_request)
        try:
            settings = AISettings(
                enabled=request.enabled,
                provider=ProviderKind(request.provider),
                base_url=request.base_url,
                model=request.model,
                privacy_mode=PrivacyMode(request.privacy_mode),
                remember_key=request.remember_key,
                timeout_seconds=request.timeout_seconds,
                max_retries=request.max_retries,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                allow_no_api_key=request.allow_no_api_key,
            )
            storage = SecretStorage(request.secret_storage)
        except (ValueError, ValidationError) as exc:
            raise DataWorkError(
                ErrorCode.AI_CONFIG_ERROR,
                f"AI 设置无效: {exc}",
                status_code=422,
            ) from exc
        return _sanitize(ai_settings.save(settings, api_key=request.api_key, secret_storage=storage))

    @application.delete("/api/ai/key")
    def clear_ai_key(request: Request) -> dict[str, Any]:
        require_ai_access(request)
        ai_settings.clear_key()
        return {"ok": True, "status": ai_settings.public_status()}

    @application.post("/api/ai/test")
    async def test_ai_connection(request: Request) -> dict[str, Any]:
        require_ai_access(request)
        return _sanitize(await ai_assistant.test_connection())

    @application.get("/api/help/steps")
    def help_steps() -> dict[str, Any]:
        return _sanitize(STEP_GUIDES)

    @application.post("/api/ai/explain/step")
    async def explain_step(request: AIExplainRequest, http_request: Request) -> dict[str, Any]:
        require_ai_access(http_request)
        return _sanitize(await ai_assistant.explain_step(
            request.step, context=request.context, question=request.question
        ))

    @application.post("/api/ai/explain/analysis-plan")
    async def explain_analysis_plan(
        request: AIAnalysisExplainRequest, http_request: Request
    ) -> dict[str, Any]:
        require_ai_access(http_request)
        return _sanitize(await ai_assistant.explain_analysis_plan(
            request.context, question=request.question, use_ai=request.use_ai
        ))

    @application.post("/api/ai/explain/result")
    async def explain_result(request: AIResultExplainRequest, http_request: Request) -> dict[str, Any]:
        require_ai_access(http_request)
        return _sanitize(await ai_assistant.explain_result(
            request.result,
            question=request.question,
            context=request.context,
            selection=request.selection.model_dump(mode="json"),
            ai_report=request.ai_report,
            result_context_id=request.result_context_id,
            ai_report_context_id=request.ai_report_context_id,
        ))

    @application.post("/api/ai/report/result")
    async def generate_ai_result_report(
        request: AIResultReportRequest, http_request: Request
    ) -> dict[str, Any]:
        if request.use_ai:
            require_ai_access(http_request)
        return _sanitize(await ai_assistant.generate_result_report(
            request.result,
            title=request.title,
            use_ai=request.use_ai,
            analysis_context=request.analysis_context,
        ))

    @application.get("/api/methods")
    def methods() -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "label_zh": item.label_zh,
                "category": item.category,
                "status": item.status.value,
                "runnable": item.is_runnable,
                "purpose": item.purpose,
                "variable_relationship": item.variable_relationship,
                "variable_requirements": [requirement.__dict__ for requirement in item.variable_requirements],
                "output_metrics": list(item.output_metrics),
                "assumptions": list(item.assumptions),
                "typical_uses": list(item.typical_uses),
                "min_dependent_vars": item.min_dependent_vars,
                "max_dependent_vars": item.max_dependent_vars,
                "dependent_mode": item.dependent_mode,
                "min_fixed_factors": item.min_fixed_factors,
                "max_fixed_factors": item.max_fixed_factors,
                "min_covariates": item.min_covariates,
                "max_covariates": item.max_covariates,
                "min_random_factors": item.min_random_factors,
                "max_random_factors": item.max_random_factors,
                "min_random_slopes": item.min_random_slopes,
                "max_random_slopes": item.max_random_slopes,
                "requires_subject_id": item.requires_subject_id,
                "requires_repeated_factor": item.requires_repeated_factor,
                "requires_any_predictor": item.requires_any_predictor,
                "exact_factor_levels": item.exact_factor_levels,
                "supports_batch": item.supports_batch,
                "supports_emm": item.supports_emm,
                "supports_diagnostic_plots": item.supports_diagnostic_plots,
                "executor": item.executor,
                "parameters": [
                    {
                        "key": parameter.key, "label_zh": parameter.label_zh, "kind": parameter.kind,
                        "default": parameter.default, "description": parameter.description,
                        "options": [{"value": value, "label": label} for value, label in parameter.options],
                        "minimum": parameter.minimum, "maximum": parameter.maximum, "step": parameter.step,
                        "advanced": parameter.advanced,
                        "simple_description": parameter.simple_description,
                        "recommended_options": list(parameter.recommended_options),
                        "recommendation_note": parameter.recommendation_note,
                        "option_help": dict(parameter.option_help),
                    }
                    for parameter in item.parameters
                ],
                "notes": item.notes,
            }
            for item in list_methods()
        ]

    @application.post("/api/profile")
    async def profile(
        file: UploadFile = File(...),
        sheet: str | None = Form(default=None),
        percentage_scale: str = Form(default="percent_points"),
    ) -> dict[str, Any]:
        loaded = await _read_upload(dataset_service, file, sheet, percentage_scale)
        return _sanitize({
            "sheet": loaded.selected_sheet,
            "sheets": loaded.sheet_names,
            "profile": loaded.profile_payload(),
            "role_map": design_service.suggest_roles(loaded.profile).model_dump(mode="json"),
            "fingerprint": loaded.fingerprint.model_dump(mode="json"),
            "cleaning_log": loaded.cleaning_payload(),
            "columns": [str(column) for column in loaded.frame.columns],
            "preview": _records(loaded.frame.head(20)),
        })

    @application.post("/api/preflight")
    async def preflight(
        file: UploadFile = File(...),
        plan_json: str = Form(...),
        sheet: str | None = Form(default=None),
        percentage_scale: str = Form(default="percent_points"),
    ) -> dict[str, Any]:
        try:
            raw_plan = json.loads(plan_json)
        except json.JSONDecodeError as exc:
            raise DataWorkError(
                ErrorCode.INVALID_PLAN,
                f"分析计划 JSON 无效: {exc}",
                status_code=422,
            ) from exc
        if not isinstance(raw_plan, dict):
            raise DataWorkError(ErrorCode.INVALID_PLAN, "分析计划必须是对象", status_code=422)
        loaded = await _read_upload(dataset_service, file, sheet, percentage_scale)
        report = preflight_service.inspect(loaded.frame, raw_plan)
        payload = report.model_dump(mode="json")
        payload["sheet"] = loaded.selected_sheet
        payload["cleaning_log"] = loaded.cleaning_payload()
        return _sanitize(payload)

    @application.get("/api/batch/exports/{export_id}")
    def download_generic_batch(export_id: str) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{32}", export_id):
            raise DataWorkError(ErrorCode.REPORT_FAILED, "无效的批量结果标识", status_code=404)
        export_root = (workspace.paths.reports / "generic_batch_exports").resolve()
        path = (export_root / f"{export_id}.xlsx").resolve()
        if export_root not in path.parents or not path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量结果文件不存在", status_code=404)
        return FileResponse(
            path,
            filename=f"DataWork_合并批量结果_{export_id[:8]}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @application.get("/api/batch/exports/{export_id}/status")
    def generic_batch_export_status(export_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", export_id):
            raise DataWorkError(ErrorCode.REPORT_FAILED, "无效的批量结果标识", status_code=404)
        export_root = (workspace.paths.reports / "generic_batch_exports").resolve()
        status_path = (export_root / export_id / "status.json").resolve()
        if export_root not in status_path.parents or not status_path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量导出状态不存在", status_code=404)
        return json.loads(status_path.read_text(encoding="utf-8"))

    @application.get("/api/batch/exports/{export_id}/{artifact}")
    def download_standardized_batch_report(export_id: str, artifact: str) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{32}", export_id):
            raise DataWorkError(ErrorCode.REPORT_FAILED, "无效的批量结果标识", status_code=404)
        export_root = (workspace.paths.reports / "generic_batch_exports").resolve()
        choices = {
            "zip": (export_root / f"{export_id}.zip", "DataWork_规范化批量分析报告.zip", "application/zip"),
            "xlsx": (export_root / f"{export_id}.xlsx", "DataWork_规范化批量分析结果.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "markdown": (export_root / export_id / "statistical_report.md", "DataWork_规范化批量分析报告.md", "text/markdown; charset=utf-8"),
            "json": (export_root / export_id / "canonical_result.json", "DataWork_规范化批量分析结果.json", "application/json"),
        }
        if artifact not in choices:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "不支持的批量报告文件类型", status_code=404)
        path, filename, media_type = choices[artifact]
        path = path.resolve()
        if export_root not in path.parents or not path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量报告文件不存在", status_code=404)
        return FileResponse(path, filename=filename, media_type=media_type)

    @application.post("/api/analyze")
    async def analyze(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        plan_json: str = Form(...),
        sheet: str | None = Form(default=None),
        percentage_scale: str = Form(default="percent_points"),
    ) -> dict[str, Any]:
        try:
            plan = AnalysisPlan.model_validate_json(plan_json)
        except ValidationError as exc:
            raise DataWorkError(
                ErrorCode.INVALID_PLAN,
                f"分析计划无效: {exc}",
                status_code=422,
            ) from exc

        loaded = await _read_upload(dataset_service, file, sheet, percentage_scale)
        execution = AnalysisService().execute(
            loaded.frame,
            plan,
            context=ExecutionContext(
                dataset_fingerprint=loaded.fingerprint,
                source_filename=loaded.source_filename,
                sheet_name=loaded.selected_sheet,
                cleaning_log=loaded.cleaning_payload(),
            ),
        )
        payload = AnalysisService.serialize_execution(execution)
        payload["sheet"] = loaded.selected_sheet
        if isinstance(execution.result, BatchAnalysisResult):
            export_id = uuid4().hex
            payload["batch_export"] = batch_export_payload(export_id, execution.result, status="preparing")
            write_batch_export_status(export_id, payload["batch_export"])
            background_tasks.add_task(generate_batch_export_artifacts, export_id, execution.result)
        return _sanitize(payload)

    @application.post("/api/instant/reports", status_code=201)
    def create_instant_report(request: InstantReportCreate) -> dict[str, Any]:
        execution = request.execution
        if execution.get("kind") != "single" or not isinstance(execution.get("result"), dict):
            raise DataWorkError(
                ErrorCode.REPORT_FAILED,
                "即时完整报告仅支持单次分析；批量分析请使用结果页现有的合并 XLSX 下载。",
                status_code=422,
            )
        try:
            result = StatisticalResult.model_validate(execution["result"])
        except ValidationError as exc:
            raise DataWorkError(ErrorCode.REPORT_FAILED, f"结果结构无效，无法生成报告: {exc}", status_code=422) from exc

        export_id = uuid4().hex
        export_root = workspace.paths.reports / "instant_exports"
        report_dir = export_root / export_id
        archive_path = export_root / f"{export_id}.zip"
        export_root.mkdir(parents=True, exist_ok=True)
        try:
            bundle = report_service.generate(result, report_dir, title=request.title)
            temporary_archive = archive_path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for artifact in bundle.artifacts:
                    artifact_path = Path(artifact.path)
                    archive.write(artifact_path, arcname=artifact_path.relative_to(report_dir).as_posix())
            temporary_archive.replace(archive_path)
        except Exception:
            shutil.rmtree(report_dir, ignore_errors=True)
            archive_path.unlink(missing_ok=True)
            raise

        return {
            "export_id": export_id,
            "download_url": f"/api/instant/reports/{export_id}/zip",
            "xlsx_download_url": f"/api/instant/reports/{export_id}/xlsx",
            "markdown_download_url": f"/api/instant/reports/{export_id}/markdown",
        }

    @application.get("/api/instant/reports/{export_id}/{artifact}")
    def download_instant_report(export_id: str, artifact: str) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{32}", export_id):
            raise DataWorkError(ErrorCode.REPORT_FAILED, "无效的即时报告标识", status_code=404)
        export_root = (workspace.paths.reports / "instant_exports").resolve()
        choices = {
            "zip": (export_root / f"{export_id}.zip", "DataWork_完整统计报告.zip", "application/zip"),
            "xlsx": (export_root / export_id / "results.xlsx", "DataWork_统计结果.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "markdown": (export_root / export_id / "statistical_report.md", "DataWork_统计报告.md", "text/markdown; charset=utf-8"),
        }
        if artifact not in choices:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "不支持的报告文件类型", status_code=404)
        path, filename, media_type = choices[artifact]
        path = path.resolve()
        if export_root not in path.parents or not path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "即时报告文件不存在", status_code=404)
        return FileResponse(path, filename=filename, media_type=media_type)

    # ── 项目工作区 ───────────────────────────────────────────────

    @application.get("/api/workspace")
    def workspace_info() -> dict[str, Any]:
        return workspace.info(include_paths=False)

    @application.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return workspace.repository.list_projects()

    @application.post("/api/projects", status_code=201)
    def create_project(request: ProjectCreate) -> dict[str, Any]:
        return workspace.create_project(request.name, request.description)

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = workspace.repository.get_project(project_id)
        project["datasets"] = workspace.repository.list_datasets(project_id)
        project["plans"] = workspace.repository.list_plans(project_id)
        project["runs"] = workspace.repository.list_runs(project_id)
        return _sanitize(project)

    @application.get("/api/projects/{project_id}/datasets")
    def list_datasets(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(workspace.repository.list_datasets(project_id))

    @application.post("/api/projects/{project_id}/datasets", status_code=201)
    async def create_dataset(
        project_id: str,
        file: UploadFile = File(...),
        name: str | None = Form(default=None),
        sheet: str | None = Form(default=None),
        percentage_scale: str = Form(default="percent_points"),
        fill_merged_like_cells: bool = Form(default=False),
    ) -> dict[str, Any]:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        return _sanitize(workspace.add_dataset(
            project_id,
            content=content,
            filename=file.filename or "upload.csv",
            name=name,
            sheet=sheet,
            percentage_scale=percentage_scale,
            fill_merged_like_cells=fill_merged_like_cells,
        ))

    @application.get("/api/datasets/{dataset_id}")
    def get_dataset(dataset_id: str) -> dict[str, Any]:
        return _sanitize(workspace.repository.get_dataset(dataset_id))

    @application.get("/api/projects/{project_id}/plans")
    def list_plans(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(workspace.repository.list_plans(project_id))

    @application.post("/api/projects/{project_id}/plans", status_code=201)
    def create_plan(project_id: str, request: PlanCreate) -> dict[str, Any]:
        try:
            return _sanitize(workspace.create_plan(
                project_id,
                request.dataset_id,
                name=request.name,
                plan_data=request.plan,
            ))
        except ValidationError as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"分析计划无效: {exc}") from exc

    @application.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(workspace.repository.get_plan(plan_id))

    @application.put("/api/plans/{plan_id}")
    def update_plan(plan_id: str, request: PlanUpdate) -> dict[str, Any]:
        try:
            return _sanitize(workspace.update_plan(plan_id, name=request.name, plan_data=request.plan))
        except ValidationError as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"分析计划无效: {exc}") from exc

    @application.post("/api/plans/{plan_id}/clone", status_code=201)
    def clone_plan(plan_id: str, request: PlanClone) -> dict[str, Any]:
        return _sanitize(workspace.clone_plan(plan_id, name=request.name))

    @application.get("/api/plans/{plan_id}/preflight")
    def preflight_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(workspace.preflight_plan(plan_id))

    @application.post("/api/plans/{plan_id}/runs", status_code=201)
    def run_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(workspace.run_plan(plan_id))

    @application.get("/api/projects/{project_id}/runs")
    def list_runs(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(workspace.repository.list_runs(project_id))

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        record = workspace.repository.get_run(run_id)
        record["reports"] = workspace.repository.list_reports(run_id)
        return _sanitize(record)

    @application.post("/api/runs/compare")
    def compare_runs(request: RunCompare) -> dict[str, Any]:
        return _sanitize(workspace.compare_runs(request.run_ids))

    @application.post("/api/runs/{run_id}/reports", status_code=201)
    def create_report(run_id: str, request: ReportCreate) -> dict[str, Any]:
        return _sanitize(workspace.generate_report(run_id, title=request.title))

    @application.get("/api/reports/{report_id}/download")
    def download_report(report_id: str) -> FileResponse:
        report, path = workspace.report_path(report_id)
        if report.get("format") == "xlsx":
            return FileResponse(
                path,
                filename=f"DataWork_合并批量结果_{report_id}.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return FileResponse(
            path,
            filename=f"DataWork_Report_{report_id}.zip",
            media_type="application/zip",
        )

    @application.get("/api/reports/{report_id}/artifacts/{artifact}")
    def download_report_artifact(report_id: str, artifact: str) -> FileResponse:
        report, primary_path = workspace.report_path(report_id)
        if report.get("format") != "xlsx":
            raise DataWorkError(ErrorCode.REPORT_FAILED, "该报告没有批量合并附件", status_code=404)
        report_dir = primary_path.parent.resolve()
        choices = {
            "xlsx": (primary_path, "DataWork_合并批量结果.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "zip": (report_dir / "DataWork_规范化批量分析报告.zip", "DataWork_规范化批量分析报告.zip", "application/zip"),
            "markdown": (report_dir / "standardized_report" / "statistical_report.md", "DataWork_规范化批量分析报告.md", "text/markdown; charset=utf-8"),
            "json": (report_dir / "standardized_report" / "canonical_result.json", "DataWork_规范化批量分析结果.json", "application/json"),
        }
        if artifact not in choices:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "不支持的批量报告附件类型", status_code=404)
        path, filename, media_type = choices[artifact]
        path = path.resolve()
        if path != primary_path and report_dir not in path.parents:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量报告附件路径无效", status_code=404)
        if not path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量报告附件不存在", status_code=404)
        return FileResponse(path, filename=filename, media_type=media_type)

    if STATIC_DIR.exists():
        assets = STATIC_DIR / "assets"
        if assets.exists():
            application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @application.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            candidate = (STATIC_DIR / full_path).resolve()
            if STATIC_DIR in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return application


async def _read_upload(
    service: DatasetService,
    upload: UploadFile,
    sheet: str | None,
    percentage_scale: str,
):
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    return service.load_bytes(
        content,
        upload.filename or "upload.csv",
        sheet=sheet,
        percentage_scale=percentage_scale,
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", force_ascii=False, date_format="iso"))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


app = create_app()
