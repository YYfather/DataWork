"""报告生成应用服务。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.provenance import sha256_bytes
from datawork.engine.result import StatisticalResult
from datawork.engine.batch import BatchAnalysisResult
from datawork.report.generator import generate_batch_report, generate_report


class ReportArtifact(BaseModel):
    name: str
    path: str
    size_bytes: int
    sha256: str
    media_type: str


class ReportBundle(BaseModel):
    directory: str
    artifacts: list[ReportArtifact] = Field(default_factory=list)


_MEDIA_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
}


class ReportService:
    def generate(
        self,
        result: StatisticalResult | BatchAnalysisResult,
        output_dir: str | Path,
        *,
        title: str = "统计分析报告",
        lang: str = "zh",
    ) -> ReportBundle:
        directory = Path(output_dir).expanduser().resolve()
        try:
            if isinstance(result, BatchAnalysisResult):
                generate_batch_report(result, directory, title=title, lang=lang)
            else:
                generate_report(result, directory, title=title, lang=lang)
        except Exception as exc:
            raise DataWorkError(
                ErrorCode.REPORT_FAILED,
                f"报告生成失败: {exc}",
                status_code=422,
            ) from exc

        artifacts: list[ReportArtifact] = []
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            content = path.read_bytes()
            artifacts.append(ReportArtifact(
                name=path.relative_to(directory).as_posix(),
                path=str(path),
                size_bytes=len(content),
                sha256=sha256_bytes(content),
                media_type=_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
            ))
        return ReportBundle(directory=str(directory), artifacts=artifacts)
