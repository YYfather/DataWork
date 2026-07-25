"""可复现性元数据与稳定哈希。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import platform
import sys
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field


_TRACKED_PACKAGES = (
    "datawork",
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "pydantic",
    "fastapi",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def dataframe_hash(frame: pd.DataFrame) -> str:
    """对清洗后的表结构和值生成稳定 SHA-256。"""
    normalized = frame.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    value_hash = pd.util.hash_pandas_object(normalized, index=True, categorize=True).values.tobytes()
    schema = json.dumps(
        [(column, str(normalized[column].dtype)) for column in normalized.columns],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(schema + value_hash)


def package_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in _TRACKED_PACKAGES:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result


class DatasetFingerprint(BaseModel):
    source_sha256: str
    cleaned_sha256: str
    source_size_bytes: int
    n_rows: int
    n_columns: int
    source_filename: str = ""
    sheet_name: str = ""


class RuntimeEnvironment(BaseModel):
    python_version: str = Field(default_factory=platform.python_version)
    python_implementation: str = Field(default_factory=platform.python_implementation)
    operating_system: str = Field(default_factory=platform.system)
    operating_system_release: str = Field(default_factory=platform.release)
    machine: str = Field(default_factory=platform.machine)
    executable: str = Field(default_factory=lambda: sys.executable)
    packages: dict[str, str] = Field(default_factory=package_versions)


class ReproducibilityMetadata(BaseModel):
    created_at: str = Field(default_factory=utc_now_iso)
    run_id: str = ""
    plan_sha256: str
    dataset: DatasetFingerprint
    environment: RuntimeEnvironment = Field(default_factory=RuntimeEnvironment)
    cleaning_log: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = None
