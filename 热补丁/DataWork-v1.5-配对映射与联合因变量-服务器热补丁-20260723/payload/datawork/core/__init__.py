"""DataWork 核心领域模型。"""

from .errors import (
    DataWorkError,
    DatasetValidationError,
    ErrorCode,
    ErrorPayload,
    IssueSeverity,
    PlanValidationError,
    ResourceNotFoundError,
    ValidationIssue,
)
from .method_registry import MethodSpec, MethodStatus, get_method, list_methods
from .plan import AnalysisPlan, MissingPolicy
from .provenance import DatasetFingerprint, ReproducibilityMetadata, RuntimeEnvironment
from .roles import RoleAssignment, RoleMap, VariableRole
from .validation import ValidationReport, validate_plan_dataframe

__all__ = [
    "AnalysisPlan",
    "MissingPolicy",
    "MethodSpec",
    "MethodStatus",
    "get_method",
    "list_methods",
    "DataWorkError",
    "DatasetValidationError",
    "ErrorCode",
    "ErrorPayload",
    "IssueSeverity",
    "PlanValidationError",
    "ResourceNotFoundError",
    "ValidationIssue",
    "DatasetFingerprint",
    "ReproducibilityMetadata",
    "RuntimeEnvironment",
    "RoleAssignment",
    "RoleMap",
    "VariableRole",
    "ValidationReport",
    "validate_plan_dataframe",
]
