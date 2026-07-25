"""数据集读取、保守清洗、画像与指纹服务。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from datawork.core.errors import DatasetValidationError, ErrorCode
from datawork.core.provenance import DatasetFingerprint, dataframe_hash, sha256_bytes
from datawork.io.profiler import DataProfile, profile_dataframe
from datawork.io.reader import (
    auto_clean_percentage, clean_dataframe, inspect_excluded_columns, read_file,
)


SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}
DEFAULT_MAX_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class CleaningStep:
    operation: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedDataset:
    frame: pd.DataFrame
    selected_sheet: str
    sheet_names: list[str]
    profile: DataProfile
    fingerprint: DatasetFingerprint
    cleaning_log: list[CleaningStep]
    source_filename: str
    percentage_scale: str

    def profile_payload(self) -> dict[str, Any]:
        return asdict(self.profile)

    def cleaning_payload(self) -> list[dict[str, Any]]:
        return [asdict(step) for step in self.cleaning_log]


class DatasetService:
    def __init__(self, *, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.max_bytes = max_bytes

    def load_path(
        self,
        path: str | Path,
        *,
        sheet: str | None = None,
        percentage_scale: str = "percent_points",
        fill_merged_like_cells: bool = False,
    ) -> LoadedDataset:
        source = Path(path).expanduser().resolve()
        if not source.exists():
            raise DatasetValidationError(f"文件不存在: {source}", status_code=404)
        content = source.read_bytes()
        return self.load_bytes(
            content,
            source.name,
            sheet=sheet,
            percentage_scale=percentage_scale,
            fill_merged_like_cells=fill_merged_like_cells,
        )

    def load_bytes(
        self,
        content: bytes,
        filename: str,
        *,
        sheet: str | None = None,
        percentage_scale: str = "percent_points",
        fill_merged_like_cells: bool = False,
    ) -> LoadedDataset:
        if len(content) > self.max_bytes:
            raise DatasetValidationError(
                f"文件超过 {self.max_bytes // (1024 * 1024)} MB 限制",
                code=ErrorCode.FILE_TOO_LARGE,
                status_code=413,
                details={"max_bytes": self.max_bytes, "actual_bytes": len(content)},
            )
        safe_name = Path(filename or "upload.csv").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise DatasetValidationError(
                f"不支持的文件格式: {suffix or '(无扩展名)'}",
                code=ErrorCode.UNSUPPORTED_FILE,
                status_code=415,
                details={"supported": sorted(SUPPORTED_SUFFIXES)},
            )

        with tempfile.TemporaryDirectory(prefix="datawork_dataset_") as directory:
            path = Path(directory) / f"source{suffix}"
            path.write_bytes(content)
            try:
                sheets = read_file(path, sheet_name=sheet)
            except Exception as exc:
                raise DatasetValidationError(f"文件读取失败: {exc}") from exc

        if not sheets:
            raise DatasetValidationError("文件中没有可用数据")
        selected_sheet = next(iter(sheets))
        source_frame = sheets[selected_sheet]
        cleaning_log: list[CleaningStep] = []

        before_shape = source_frame.shape
        excluded_columns = inspect_excluded_columns(source_frame)
        frame = clean_dataframe(
            source_frame,
            fill_merged_like_cells=fill_merged_like_cells,
        )
        cleaning_log.append(CleaningStep(
            operation="conservative_clean",
            details={
                "before_rows": before_shape[0],
                "before_columns": before_shape[1],
                "after_rows": frame.shape[0],
                "after_columns": frame.shape[1],
                "fill_merged_like_cells": fill_merged_like_cells,
                "excluded_columns": excluded_columns,
            },
        ))

        frame, percentage_columns = auto_clean_percentage(frame, scale=percentage_scale)
        if percentage_columns:
            cleaning_log.append(CleaningStep(
                operation="convert_percentage",
                details={"columns": percentage_columns, "scale": percentage_scale},
            ))

        data_profile = profile_dataframe(frame, safe_name, selected_sheet)
        fingerprint = DatasetFingerprint(
            source_sha256=sha256_bytes(content),
            cleaned_sha256=dataframe_hash(frame),
            source_size_bytes=len(content),
            n_rows=int(frame.shape[0]),
            n_columns=int(frame.shape[1]),
            source_filename=safe_name,
            sheet_name=selected_sheet,
        )
        return LoadedDataset(
            frame=frame,
            selected_sheet=selected_sheet,
            sheet_names=list(sheets),
            profile=data_profile,
            fingerprint=fingerprint,
            cleaning_log=cleaning_log,
            source_filename=safe_name,
            percentage_scale=percentage_scale,
        )
