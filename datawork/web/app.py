"""FastAPI 应用：无状态分析与本地持久工作区共用同一后端。"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict
from pathlib import Path
import platform
import re
import shutil
import time
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
from datawork.application.batch_export_service import dependent_combination_aggregate_names
from datawork.application.preflight_service import PreflightService
from datawork.application.report_service import ReportService
from datawork.application.ai_assistant_service import AIAssistantService, STEP_GUIDES
from datawork.application.dataset_service import DEFAULT_MAX_BYTES, DatasetService
from datawork.application.design_service import DesignService
from datawork.application.workspace_service import WorkspaceService
from datawork.ai.provider import ProviderKind
from datawork.ai.settings import AISettings, AISettingsService, PrivacyMode, SecretStorage
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.formula import apply_derived_columns
from datawork.core.method_registry import list_methods
from datawork.core.plan import AnalysisPlan, DerivedColumn
from datawork.io.profiler import profile_dataframe
from datawork.engine.batch import BatchAnalysisResult
from datawork.engine.result import StatisticalResult
from datawork.infrastructure.paths import resolve_workspace_paths
from datawork.web.schemas import (
    AIAnalysisExplainRequest, AIAssistantAskRequest, AIExplainRequest, AIResultExplainRequest, AIResultReportRequest, AISettingsUpdate, InstantReportCreate, PlanClone, PlanCreate,
    DerivedPreviewRequest, PlanUpdate, ProjectCreate, ReportCreate, RunCompare, WorkspaceAuthLogin,
)
from datawork.web.sessions import (
    CURRENT_SESSION,
    SessionCapacityError,
    SessionExpiredError,
    SessionRegistry,
    SessionResourceProxy,
)
from datawork.web.workspace_auth import WorkspaceAuthService


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


def _directory_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def create_app(
    *,
    workspace_root: str | Path | None = None,
    session_registry: SessionRegistry | None = None,
) -> FastAPI:
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
    registry = session_registry or SessionRegistry(
        workspace_root,
        max_sessions=int(os.getenv("DATAWORK_MAX_ACTIVE_USERS", "3")),
        timeout_seconds=int(os.getenv("DATAWORK_SESSION_TIMEOUT_SECONDS", "600")),
        presence_timeout_seconds=int(os.getenv("DATAWORK_PRESENCE_TIMEOUT_SECONDS", "300")),
        ai_guest_question_limit=int(os.getenv("DATAWORK_AI_GUEST_QUESTION_LIMIT", "10")),
    )
    workspace_auth = WorkspaceAuthService(registry.root)
    registry.cleanup_expired_data = workspace_auth.cleanup_expired_sessions
    owner_workspace = WorkspaceService(registry.root / "owner") if workspace_auth.configured else None
    session_workspace = SessionResourceProxy(lambda session: session.workspace)
    project_workspace = SessionResourceProxy(
        lambda session: owner_workspace if owner_workspace is not None else session.workspace,
    )
    ai_settings = SessionResourceProxy(lambda session: session.ai_settings)
    ai_assistant = SessionResourceProxy(lambda session: session.ai_assistant)
    server_ai_settings = AISettingsService(
        resolve_workspace_paths(registry.root / "server_ai")
    )
    server_ai_assistant = AIAssistantService(server_ai_settings)
    application.state.session_registry = registry
    application.state.workspace = project_workspace
    application.state.workspace_auth = workspace_auth
    application.state.ai_settings = ai_settings
    application.state.server_ai_settings = server_ai_settings

    def request_session_id(request: Request) -> str | None:
        return request.headers.get("X-DataWork-Session") or request.cookies.get("datawork_session")

    def request_client_id(request: Request) -> str | None:
        return request.headers.get("X-DataWork-Client")

    def session_error(status_code: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": message,
                "error": {
                    "code": code,
                    "message": message,
                    "issues": [],
                    "details": {
                        "active_users": registry.status(None)["active_users"],
                        "max_users": registry.max_sessions,
                        "idle_timeout_seconds": registry.timeout_seconds,
                    },
                },
            },
        )

    public_api_paths = {
        "/api/health",
        "/api/capabilities",
        "/api/methods",
        "/api/help/steps",
        "/api/session/status",
        "/api/session/heartbeat",
        "/api/session/activity",
        "/api/session/release",
    }
    workspace_api_prefixes = (
        "/api/workspace",
        "/api/projects",
        "/api/datasets",
        "/api/plans",
        "/api/runs",
        "/api/reports",
    )

    def is_workspace_api(path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in workspace_api_prefixes)

    def workspace_auth_error() -> JSONResponse:
        message = "项目工作区仅限所有者使用，请先输入工作区密码。"
        return JSONResponse(
            status_code=401,
            content={
                "detail": message,
                "error": {
                    "code": ErrorCode.WORKSPACE_AUTH_REQUIRED.value,
                    "message": message,
                    "issues": [],
                    "details": {},
                },
            },
        )

    @application.middleware("http")
    async def session_isolation(request: Request, call_next):
        path = request.scope.get("path", request.url.path)
        root_path = request.scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        if not path.startswith("/api/") or path in public_api_paths:
            return await call_next(request)

        try:
            session = registry.acquire(request_session_id(request), request_client_id(request))
        except SessionCapacityError as exc:
            return session_error(429, "session_capacity_reached", str(exc))
        except SessionExpiredError as exc:
            return session_error(440, "session_expired", str(exc))

        token = CURRENT_SESSION.set(session)
        try:
            if is_workspace_api(path) and workspace_auth.configured and not session.workspace_authenticated:
                response = workspace_auth_error()
            else:
                response = await call_next(request)
        finally:
            CURRENT_SESSION.reset(token)
        status = registry.status(session.session_id)
        response.headers["X-DataWork-Active-Users"] = str(status["active_users"])
        response.headers["X-DataWork-Max-Users"] = str(status["max_users"])
        response.set_cookie(
            "datawork_session",
            session.session_id,
            httponly=True,
            secure=request.headers.get("x-forwarded-proto", "").lower() == "https",
            samesite="lax",
            path="/",
            max_age=registry.timeout_seconds,
        )
        return response

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
                *dependent_combination_aggregate_names(result),
                *[f"批次_{index:03d}" for index in range(1, len(result.results) + 1)],
                "失败与警告",
                "分析设置",
            ],
        }

    def write_batch_export_status(
        export_id: str,
        payload: dict[str, Any],
        target_workspace: WorkspaceService | None = None,
    ) -> None:
        target_workspace = target_workspace or session_workspace.current()
        export_root = target_workspace.paths.reports / "generic_batch_exports"
        status_path = export_root / export_id / "status.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = status_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        temporary.replace(status_path)

    def generate_batch_export_artifacts(
        export_id: str,
        result: BatchAnalysisResult,
        target_workspace: WorkspaceService,
    ) -> None:
        export_dir = target_workspace.paths.reports / "generic_batch_exports"
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
                target_workspace,
            )
        except Exception as exc:
            LOGGER.exception("批量导出后台生成失败: %s", export_id)
            write_batch_export_status(
                export_id,
                batch_export_payload(export_id, result, status="failed", error=str(exc)),
                target_workspace,
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

    def _current_session_resources():
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("当前请求没有 DataWork 会话上下文")
        return session

    def _ai_access_payload(
        session,
        *,
        source: str,
        quota: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        return {
            "configuration_source": source,
            "using_personal_api": source == "personal",
            "owner_authenticated": bool(session.workspace_authenticated),
            "workspace_auth_available": bool(workspace_auth.configured),
            "guest_quota": quota or registry.ai_quota_status(session.session_id),
        }

    def _effective_ai_status() -> dict[str, Any]:
        session = _current_session_resources()
        personal = session.ai_settings.public_status()
        server = server_ai_settings.public_status()
        if personal["enabled"] and personal["configured"]:
            payload = dict(personal)
            source = "personal"
        elif server["enabled"] and server["configured"]:
            payload = dict(server)
            source = "server"
        else:
            payload = dict(personal)
            source = "personal"
        payload.update(_ai_access_payload(session, source=source))
        payload["server_configuration_available"] = bool(
            server["enabled"] and server["configured"]
        )
        payload["server_managed"] = source == "server"
        return payload

    def _select_ai_runtime(
        *,
        consume_guest_quota: bool,
        connection_test: bool = False,
    ) -> tuple[AIAssistantService, dict[str, Any]]:
        session = _current_session_resources()
        personal = session.ai_settings.public_status()
        personal_ready = bool(
            personal["connection_ready"]
            if connection_test
            else personal["enabled"] and personal["configured"]
        )
        if personal_ready:
            return session.ai_assistant, _ai_access_payload(
                session, source="personal"
            )

        server = server_ai_settings.public_status()
        server_ready = bool(
            server["connection_ready"]
            if connection_test
            else server["enabled"] and server["configured"]
        )
        if not server_ready:
            return session.ai_assistant, _ai_access_payload(
                session, source="personal"
            )
        if session.workspace_authenticated:
            return server_ai_assistant, _ai_access_payload(
                session, source="server"
            )
        quota = registry.ai_quota_status(session.session_id)
        if consume_guest_quota:
            quota = registry.consume_ai_guest_question(session.session_id)
            if quota is None:
                raise DataWorkError(
                    ErrorCode.AI_FREE_QUOTA_EXHAUSTED,
                    "本浏览器的 10 次免费 AI 提问额度已用完。请验证工作区密码，或在 AI 设置中填写自己的 API 密钥。",
                    status_code=429,
                    details={
                        "limit": registry.ai_guest_question_limit,
                        "remaining": 0,
                        "reset_seconds": registry.ai_quota_status(
                            session.session_id
                        )["resets_in_seconds"],
                        "workspace_auth_available": workspace_auth.configured,
                    },
                )
        return server_ai_assistant, _ai_access_payload(
            session, source="server", quota=quota
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
        session_status = registry.status(None)
        return {
            "status": "ok",
            "version": _package_version(),
            "python": platform.python_version(),
            "platform": platform.system(),
            "features": {
                "api_contract": "v1.7",
                "pairing_workflow": True,
                "pairing_abs": True,
                "dependent_variable_groups": True,
                "dependent_variable_combinations": True,
                "branch_complete_posthoc": True,
            },
            "workspace": {
                "enabled": True,
                "storage": "sqlite",
                "isolation": "owner_only" if workspace_auth.configured else "per_session",
                "authentication_required": workspace_auth.configured,
                "schema_version": 1,
            },
            "sessions": {
                "active_users": session_status["active_users"],
                "max_users": session_status["max_users"],
                "idle_timeout_seconds": session_status["idle_timeout_seconds"],
            },
        }

    @application.get("/api/session")
    def current_session() -> dict[str, Any]:
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("会话中间件未建立上下文")
        status = registry.status(session.session_id)
        status["session_id"] = session.session_id
        status["workspace"] = {
            "enabled": True,
            "authentication_required": workspace_auth.configured,
            "authenticated": session.workspace_authenticated if workspace_auth.configured else True,
        }
        return status

    @application.get("/api/session/status")
    def current_session_status(request: Request) -> dict[str, object]:
        return registry.status(request_session_id(request), touch=False)

    @application.post("/api/session/heartbeat")
    def session_heartbeat(request: Request) -> dict[str, object]:
        return registry.heartbeat(request_session_id(request), request_client_id(request))

    @application.post("/api/session/activity")
    def session_activity(request: Request) -> dict[str, object]:
        return registry.record_activity(request_session_id(request), request_client_id(request))

    @application.post("/api/session/release")
    async def session_release(request: Request) -> dict[str, object]:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        session_id = request_session_id(request) or payload.get("session_id")
        client_id = request_client_id(request) or payload.get("client_id")
        return registry.release(session_id, client_id)

    @application.get("/api/workspace-auth/status")
    def workspace_auth_status() -> dict[str, Any]:
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("会话中间件未建立上下文")
        return {
            "required": workspace_auth.configured,
            "authenticated": session.workspace_authenticated if workspace_auth.configured else True,
            "idle_timeout_seconds": registry.timeout_seconds,
            "temporary_session_cleanup": registry.cleanup_expired_data,
        }

    @application.post("/api/workspace-auth/login")
    def workspace_auth_login(request: WorkspaceAuthLogin) -> dict[str, Any]:
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("会话中间件未建立上下文")
        if not workspace_auth.configured:
            session.workspace_authenticated = True
            return workspace_auth_status()

        now = time.monotonic()
        if session.workspace_auth_locked_until > now:
            wait_seconds = max(1, math.ceil(session.workspace_auth_locked_until - now))
            raise DataWorkError(
                ErrorCode.WORKSPACE_AUTH_LOCKED,
                f"密码连续错误次数过多，请 {wait_seconds} 秒后重试。",
                status_code=429,
                details={"retry_after_seconds": wait_seconds},
            )
        if not workspace_auth.verify(request.password):
            session.workspace_auth_failures += 1
            remaining = max(0, 5 - session.workspace_auth_failures)
            if remaining == 0:
                session.workspace_auth_locked_until = now + 300
                session.workspace_auth_failures = 0
                raise DataWorkError(
                    ErrorCode.WORKSPACE_AUTH_LOCKED,
                    "密码连续错误 5 次，工作区登录已锁定 5 分钟。",
                    status_code=429,
                    details={"retry_after_seconds": 300},
                )
            raise DataWorkError(
                ErrorCode.WORKSPACE_AUTH_FAILED,
                f"工作区密码不正确，还可尝试 {remaining} 次。",
                status_code=401,
                details={"remaining_attempts": remaining},
            )

        session.workspace_authenticated = True
        session.workspace_auth_failures = 0
        session.workspace_auth_locked_until = 0.0
        return workspace_auth_status()

    @application.post("/api/workspace-auth/logout")
    def workspace_auth_logout() -> dict[str, Any]:
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("会话中间件未建立上下文")
        session.workspace_authenticated = False
        return workspace_auth_status()

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
                "pairing_workflow": True,
                "pairing_abs": True,
                "dependent_variable_groups": True,
                "dependent_variable_combinations": True,
                "branch_complete_posthoc": True,
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
        payload = _effective_ai_status()
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
        payload = ai_settings.save(
            settings, api_key=request.api_key, secret_storage=storage
        )
        payload["settings"] = _effective_ai_status()
        return _sanitize(payload)

    @application.delete("/api/ai/key")
    def clear_ai_key(request: Request) -> dict[str, Any]:
        require_ai_access(request)
        ai_settings.clear_key()
        return {"ok": True, "status": _sanitize(_effective_ai_status())}

    @application.post("/api/ai/test")
    async def test_ai_connection(request: Request) -> dict[str, Any]:
        require_ai_access(request)
        assistant, access = _select_ai_runtime(
            consume_guest_quota=False, connection_test=True
        )
        payload = await assistant.test_connection()
        payload["ai_access"] = access
        return _sanitize(payload)

    @application.get("/api/help/steps")
    def help_steps() -> dict[str, Any]:
        return _sanitize(STEP_GUIDES)

    @application.post("/api/ai/explain/step")
    async def explain_step(request: AIExplainRequest, http_request: Request) -> dict[str, Any]:
        require_ai_access(http_request)
        assistant, access = _select_ai_runtime(consume_guest_quota=True)
        payload = await assistant.explain_step(
            request.step, context=request.context, question=request.question
        )
        payload["ai_access"] = access
        return _sanitize(payload)

    @application.post("/api/ai/ask")
    async def ask_ai_assistant(
        request: AIAssistantAskRequest, http_request: Request
    ) -> dict[str, Any]:
        require_ai_access(http_request)
        assistant, access = _select_ai_runtime(consume_guest_quota=True)
        payload = await assistant.ask(
            question=request.question,
            context=request.context,
            result=request.result,
            selection=request.selection.model_dump(mode="json"),
            ai_report=request.ai_report,
            result_context_id=request.result_context_id,
            ai_report_context_id=request.ai_report_context_id,
        )
        payload["ai_access"] = access
        return _sanitize(payload)

    @application.post("/api/ai/explain/analysis-plan")
    async def explain_analysis_plan(
        request: AIAnalysisExplainRequest, http_request: Request
    ) -> dict[str, Any]:
        require_ai_access(http_request)
        if request.use_ai:
            assistant, access = _select_ai_runtime(consume_guest_quota=True)
        else:
            assistant = _current_session_resources().ai_assistant
            access = _ai_access_payload(
                _current_session_resources(), source="personal"
            )
        payload = await assistant.explain_analysis_plan(
            request.context, question=request.question, use_ai=request.use_ai
        )
        payload["ai_access"] = access
        return _sanitize(payload)

    @application.post("/api/ai/explain/result")
    async def explain_result(request: AIResultExplainRequest, http_request: Request) -> dict[str, Any]:
        require_ai_access(http_request)
        assistant, access = _select_ai_runtime(consume_guest_quota=True)
        payload = await assistant.explain_result(
            request.result,
            question=request.question,
            context=request.context,
            selection=request.selection.model_dump(mode="json"),
            ai_report=request.ai_report,
            result_context_id=request.result_context_id,
            ai_report_context_id=request.ai_report_context_id,
        )
        payload["ai_access"] = access
        return _sanitize(payload)

    @application.post("/api/ai/report/result")
    async def generate_ai_result_report(
        request: AIResultReportRequest, http_request: Request
    ) -> dict[str, Any]:
        if request.use_ai:
            require_ai_access(http_request)
            assistant, access = _select_ai_runtime(consume_guest_quota=True)
        else:
            assistant = _current_session_resources().ai_assistant
            access = _ai_access_payload(
                _current_session_resources(), source="personal"
            )
        payload = await assistant.generate_result_report(
            request.result,
            title=request.title,
            use_ai=request.use_ai,
            analysis_context=request.analysis_context,
        )
        payload["ai_access"] = access
        return _sanitize(payload)

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

    @application.post("/api/derived/preview")
    async def preview_derived_columns(
        file: UploadFile = File(...),
        derived_columns_json: str = Form(...),
        sheet: str | None = Form(default=None),
        percentage_scale: str = Form(default="percent_points"),
    ) -> dict[str, Any]:
        try:
            raw = json.loads(derived_columns_json)
            if not isinstance(raw, list):
                raise ValueError("自定义列配置必须是数组")
            definitions = [DerivedColumn.model_validate(item) for item in raw]
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"自定义列配置无效: {exc}", status_code=422) from exc
        loaded = await _read_upload(dataset_service, file, sheet, percentage_scale)
        try:
            derived_frame, transformation_log, warnings = apply_derived_columns(loaded.frame, definitions)
        except ValueError as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, str(exc), status_code=422) from exc
        derived_profile = profile_dataframe(derived_frame, loaded.source_filename, loaded.selected_sheet)
        return _sanitize({
            "profile": asdict(derived_profile),
            "columns": [str(column) for column in derived_frame.columns],
            "preview": _records(derived_frame.head(20)),
            "derived_log": transformation_log,
            "warnings": warnings,
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
        export_root = (session_workspace.paths.reports / "generic_batch_exports").resolve()
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
        export_root = (session_workspace.paths.reports / "generic_batch_exports").resolve()
        status_path = (export_root / export_id / "status.json").resolve()
        if export_root not in status_path.parents or not status_path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "批量导出状态不存在", status_code=404)
        return json.loads(status_path.read_text(encoding="utf-8"))

    @application.get("/api/batch/exports/{export_id}/{artifact}")
    def download_standardized_batch_report(export_id: str, artifact: str) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{32}", export_id):
            raise DataWorkError(ErrorCode.REPORT_FAILED, "无效的批量结果标识", status_code=404)
        export_root = (session_workspace.paths.reports / "generic_batch_exports").resolve()
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
            target_workspace = session_workspace.current()
            write_batch_export_status(export_id, payload["batch_export"], target_workspace)
            background_tasks.add_task(
                generate_batch_export_artifacts,
                export_id,
                execution.result,
                target_workspace,
            )
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
        export_root = session_workspace.paths.reports / "instant_exports"
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
        export_root = (session_workspace.paths.reports / "instant_exports").resolve()
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
        payload = project_workspace.info(include_paths=False)
        payload["used_bytes"] = _directory_size(project_workspace.paths.root)
        payload["owner_only"] = workspace_auth.configured
        return payload

    @application.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return project_workspace.repository.list_projects()

    @application.post("/api/projects", status_code=201)
    def create_project(request: ProjectCreate) -> dict[str, Any]:
        return project_workspace.create_project(request.name, request.description)

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = project_workspace.repository.get_project(project_id)
        project["datasets"] = project_workspace.repository.list_datasets(project_id)
        project["plans"] = project_workspace.list_plans(project_id)
        project["runs"] = project_workspace.repository.list_runs(project_id)
        return _sanitize(project)

    @application.get("/api/projects/{project_id}/datasets")
    def list_datasets(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(project_workspace.repository.list_datasets(project_id))

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
        return _sanitize(project_workspace.add_dataset(
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
        return _sanitize(project_workspace.repository.get_dataset(dataset_id))

    @application.post("/api/datasets/{dataset_id}/derived-preview")
    def preview_workspace_derived_columns(dataset_id: str, request: DerivedPreviewRequest) -> dict[str, Any]:
        _record, loaded = project_workspace.load_dataset(dataset_id)
        try:
            definitions = [DerivedColumn.model_validate(item) for item in request.derived_columns]
            derived_frame, transformation_log, warnings = apply_derived_columns(loaded.frame, definitions)
        except (ValidationError, ValueError) as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"自定义列配置无效: {exc}", status_code=422) from exc
        derived_profile = profile_dataframe(derived_frame, loaded.source_filename, loaded.selected_sheet)
        return _sanitize({
            "profile": asdict(derived_profile),
            "columns": [str(column) for column in derived_frame.columns],
            "preview": _records(derived_frame.head(20)),
            "derived_log": transformation_log,
            "warnings": warnings,
        })

    @application.get("/api/projects/{project_id}/plans")
    def list_plans(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(project_workspace.repository.list_plans(project_id))

    @application.post("/api/projects/{project_id}/plans", status_code=201)
    def create_plan(project_id: str, request: PlanCreate) -> dict[str, Any]:
        try:
            return _sanitize(project_workspace.create_plan(
                project_id,
                request.dataset_id,
                name=request.name,
                plan_data=request.plan,
            ))
        except ValidationError as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"分析计划无效: {exc}") from exc

    @application.get("/api/plans/{plan_id}")
    def get_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(project_workspace.repository.get_plan(plan_id))

    @application.put("/api/plans/{plan_id}")
    def update_plan(plan_id: str, request: PlanUpdate) -> dict[str, Any]:
        try:
            return _sanitize(project_workspace.update_plan(plan_id, name=request.name, plan_data=request.plan))
        except ValidationError as exc:
            raise DataWorkError(ErrorCode.INVALID_PLAN, f"分析计划无效: {exc}") from exc

    @application.post("/api/plans/{plan_id}/clone", status_code=201)
    def clone_plan(plan_id: str, request: PlanClone) -> dict[str, Any]:
        return _sanitize(project_workspace.clone_plan(plan_id, name=request.name))

    @application.get("/api/plans/{plan_id}/preflight")
    def preflight_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(project_workspace.preflight_plan(plan_id))

    @application.post("/api/plans/{plan_id}/runs", status_code=201)
    def run_plan(plan_id: str) -> dict[str, Any]:
        return _sanitize(project_workspace.run_plan(plan_id))

    @application.get("/api/projects/{project_id}/runs")
    def list_runs(project_id: str) -> list[dict[str, Any]]:
        return _sanitize(project_workspace.repository.list_runs(project_id))

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        record = project_workspace.repository.get_run(run_id)
        record["reports"] = project_workspace.repository.list_reports(run_id)
        return _sanitize(record)

    @application.post("/api/runs/compare")
    def compare_runs(request: RunCompare) -> dict[str, Any]:
        return _sanitize(project_workspace.compare_runs(request.run_ids))

    @application.post("/api/runs/{run_id}/reports", status_code=201)
    def create_report(run_id: str, request: ReportCreate) -> dict[str, Any]:
        return _sanitize(project_workspace.generate_report(run_id, title=request.title))

    @application.get("/api/reports/{report_id}/download")
    def download_report(report_id: str) -> FileResponse:
        report, path = project_workspace.report_path(report_id)
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
        report, primary_path = project_workspace.report_path(report_id)
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
