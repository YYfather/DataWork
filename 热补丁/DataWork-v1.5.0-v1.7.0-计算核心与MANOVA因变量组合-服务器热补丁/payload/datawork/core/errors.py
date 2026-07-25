"""DataWork 统一错误与校验问题模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    INVALID_PLAN = "invalid_plan"
    INVALID_DATASET = "invalid_dataset"
    METHOD_UNAVAILABLE = "method_unavailable"
    EXECUTION_FAILED = "execution_failed"
    RESOURCE_NOT_FOUND = "resource_not_found"
    WORKSPACE_CONFLICT = "workspace_conflict"
    WORKSPACE_AUTH_REQUIRED = "workspace_auth_required"
    WORKSPACE_AUTH_FAILED = "workspace_auth_failed"
    WORKSPACE_AUTH_LOCKED = "workspace_auth_locked"
    UNSUPPORTED_FILE = "unsupported_file"
    FILE_TOO_LARGE = "file_too_large"
    REPORT_FAILED = "report_failed"
    AI_CONFIG_ERROR = "ai_config_error"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_REQUEST_FAILED = "ai_request_failed"
    AI_FREE_QUOTA_EXHAUSTED = "ai_free_quota_exhausted"
    INTERNAL_ERROR = "internal_error"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR
    field: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorPayload(BaseModel):
    code: ErrorCode
    message: str
    issues: list[ValidationIssue] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class DataWorkError(ValueError):
    """可安全暴露给 API/CLI 的领域错误。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 422,
        issues: list[ValidationIssue] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.issues = issues or []
        self.details = details or {}

    def to_payload(self) -> ErrorPayload:
        return ErrorPayload(
            code=self.code,
            message=self.message,
            issues=self.issues,
            details=self.details,
        )


class PlanValidationError(DataWorkError):
    def __init__(self, issues: list[ValidationIssue], message: str = "") -> None:
        if not message:
            message = "；".join(issue.message for issue in issues) or "分析计划校验失败"
        super().__init__(
            ErrorCode.INVALID_PLAN,
            message,
            status_code=422,
            issues=issues,
        )


class DatasetValidationError(DataWorkError):
    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.INVALID_DATASET,
        status_code: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, status_code=status_code, details=details)


class ResourceNotFoundError(DataWorkError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"未找到{resource}: {resource_id}",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )
