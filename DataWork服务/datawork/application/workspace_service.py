"""项目工作区应用服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4
import zipfile

import pandas as pd

from datawork.application.analysis_service import AnalysisService, ExecutionContext
from datawork.application.batch_export_service import GenericBatchExportService
from datawork.application.dataset_service import DatasetService
from datawork.application.preflight_service import PreflightService
from datawork.application.report_service import ReportService
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.core.plan import AnalysisPlan
from datawork.core.provenance import DatasetFingerprint, canonical_json_hash, sha256_bytes
from datawork.core.validation import validate_plan_dataframe
from datawork.engine.result import StatisticalResult
from datawork.infrastructure.workspace_repository import WorkspaceRepository


class WorkspaceService:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        repository: WorkspaceRepository | None = None,
    ) -> None:
        self.repository = repository or WorkspaceRepository(root)
        self.paths = self.repository.paths
        self.datasets = DatasetService()
        self.analyses = AnalysisService()
        self.reports = ReportService()
        self.preflight = PreflightService()

    def info(self, *, include_paths: bool = False) -> dict[str, Any]:
        payload = {
            "enabled": True,
            "storage": "sqlite",
            "project_count": len(self.repository.list_projects()),
            "database_name": self.paths.database.name,
            "schema_version": self.repository.schema_version,
        }
        if include_paths:
            payload["root"] = str(self.paths.root)
            payload["database"] = str(self.paths.database)
        return payload

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        if not name.strip():
            raise DataWorkError(ErrorCode.WORKSPACE_CONFLICT, "项目名称不能为空")
        return self.repository.create_project(name, description)

    def add_dataset(
        self,
        project_id: str,
        *,
        content: bytes,
        filename: str,
        name: str | None = None,
        sheet: str | None = None,
        percentage_scale: str = "percent_points",
        fill_merged_like_cells: bool = False,
    ) -> dict[str, Any]:
        self.repository.get_project(project_id)
        loaded = self.datasets.load_bytes(
            content,
            filename,
            sheet=sheet,
            percentage_scale=percentage_scale,
            fill_merged_like_cells=fill_merged_like_cells,
        )
        dataset_id = f"ds_{uuid4().hex}"
        suffix = Path(filename).suffix.lower()
        relative = Path("files") / project_id / "datasets" / f"{dataset_id}{suffix}"
        target = (self.paths.root / relative).resolve()
        if self.paths.root not in target.parents:
            raise DataWorkError(ErrorCode.WORKSPACE_CONFLICT, "数据集存储路径越界")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return self.repository.add_dataset({
            "id": dataset_id,
            "project_id": project_id,
            "name": (name or Path(filename).stem).strip() or Path(filename).stem,
            "original_filename": Path(filename).name,
            "stored_path": relative.as_posix(),
            "sheet_name": loaded.selected_sheet,
            "percentage_scale": percentage_scale,
            "source_sha256": loaded.fingerprint.source_sha256,
            "cleaned_sha256": loaded.fingerprint.cleaned_sha256,
            "size_bytes": len(content),
            "profile": loaded.profile_payload(),
            "fingerprint": loaded.fingerprint.model_dump(mode="json"),
            "cleaning_log": loaded.cleaning_payload(),
        })

    def _dataset_path(self, dataset: dict[str, Any]) -> Path:
        path = (self.paths.root / dataset["stored_path"]).resolve()
        if self.paths.root != path and self.paths.root not in path.parents:
            raise DataWorkError(ErrorCode.WORKSPACE_CONFLICT, "数据集路径不在工作区内")
        if not path.exists():
            raise DataWorkError(ErrorCode.INVALID_DATASET, f"数据集源文件缺失: {path}", status_code=404)
        return path

    def load_dataset(self, dataset_id: str):
        record = self.repository.get_dataset(dataset_id)
        loaded = self.datasets.load_path(
            self._dataset_path(record),
            sheet=record["sheet_name"] or None,
            percentage_scale=record["percentage_scale"],
        )
        if loaded.fingerprint.source_sha256 != record["source_sha256"]:
            raise DataWorkError(
                ErrorCode.INVALID_DATASET,
                "数据集源文件哈希与登记值不一致，分析已停止",
                details={
                    "expected": record["source_sha256"],
                    "actual": loaded.fingerprint.source_sha256,
                },
            )
        return record, loaded

    def create_plan(
        self,
        project_id: str,
        dataset_id: str,
        *,
        name: str,
        plan_data: dict[str, Any],
        parent_plan_id: str | None = None,
    ) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        dataset, loaded = self.load_dataset(dataset_id)
        if dataset["project_id"] != project["id"]:
            raise DataWorkError(ErrorCode.WORKSPACE_CONFLICT, "数据集不属于该项目")
        plan = AnalysisPlan.model_validate(plan_data)
        validate_plan_dataframe(plan, loaded.frame).raise_for_errors()
        return self.repository.create_plan(
            project_id=project_id,
            dataset_id=dataset_id,
            name=name.strip() or plan.method,
            plan=plan.model_dump(mode="json"),
            plan_sha256=canonical_json_hash(plan),
            parent_plan_id=parent_plan_id,
        )

    def update_plan(self, plan_id: str, *, name: str, plan_data: dict[str, Any]) -> dict[str, Any]:
        existing = self.repository.get_plan(plan_id)
        _dataset, loaded = self.load_dataset(existing["dataset_id"])
        plan = AnalysisPlan.model_validate(plan_data)
        validate_plan_dataframe(plan, loaded.frame).raise_for_errors()
        return self.repository.update_plan(
            plan_id,
            name=name.strip() or existing["name"],
            plan=plan.model_dump(mode="json"),
            plan_sha256=canonical_json_hash(plan),
        )

    def clone_plan(self, plan_id: str, *, name: str | None = None) -> dict[str, Any]:
        existing = self.repository.get_plan(plan_id)
        return self.repository.create_plan(
            project_id=existing["project_id"],
            dataset_id=existing["dataset_id"],
            name=(name or f"{existing['name']} - 副本").strip(),
            plan=existing["plan_json"],
            plan_sha256=existing["plan_sha256"],
            parent_plan_id=plan_id,
        )

    def preflight_plan(self, plan_id: str) -> dict[str, Any]:
        plan_record = self.repository.get_plan(plan_id)
        _dataset_record, loaded = self.load_dataset(plan_record["dataset_id"])
        report = self.preflight.inspect(loaded.frame, plan_record["plan_json"])
        payload = report.model_dump(mode="json")
        payload["plan_id"] = plan_id
        payload["dataset_id"] = plan_record["dataset_id"]
        payload["prior_run_count"] = self.repository.count_plan_runs(plan_id)
        return payload

    def run_plan(self, plan_id: str) -> dict[str, Any]:
        plan_record = self.repository.get_plan(plan_id)
        dataset_record, loaded = self.load_dataset(plan_record["dataset_id"])
        run_record = self.repository.begin_run(
            plan_record["project_id"],
            plan_record["dataset_id"],
            plan_id,
        )
        run_id = run_record["id"]
        try:
            plan = AnalysisPlan.model_validate(plan_record["plan_json"])
            execution = self.analyses.execute(
                loaded.frame,
                plan,
                context=ExecutionContext(
                    run_id=run_id,
                    dataset_fingerprint=DatasetFingerprint.model_validate(dataset_record["fingerprint_json"]),
                    source_filename=dataset_record["original_filename"],
                    sheet_name=dataset_record["sheet_name"],
                    cleaning_log=dataset_record["cleaning_log_json"],
                ),
            )
            payload = self.analyses.serialize_execution(execution)
            return self.repository.complete_run(
                run_id,
                result=payload,
                provenance=execution.provenance.model_dump(mode="json"),
            )
        except DataWorkError as exc:
            self.repository.complete_run(
                run_id,
                result=None,
                provenance=None,
                error=exc.to_payload().model_dump(mode="json"),
            )
            raise
        except Exception as exc:
            error = DataWorkError(
                ErrorCode.EXECUTION_FAILED,
                f"分析执行失败: {exc}",
                status_code=422,
                details={"run_id": run_id},
            )
            self.repository.complete_run(
                run_id,
                result=None,
                provenance=None,
                error=error.to_payload().model_dump(mode="json"),
            )
            raise error from exc

    def generate_report(self, run_id: str, *, title: str = "统计分析报告") -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run["status"] != "completed" or not run["result_json"]:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "只有成功完成的分析可以生成报告")
        execution = run["result_json"]
        bundle_id = uuid4().hex
        relative_dir = Path("reports") / run_id / bundle_id
        report_dir = (self.paths.root / relative_dir).resolve()
        report_dir.mkdir(parents=True, exist_ok=True)

        if execution.get("kind") == "batch":
            batch_payload = execution.get("result", {})
            if not (batch_payload.get("overview") or batch_payload.get("summary")):
                raise DataWorkError(ErrorCode.REPORT_FAILED, "批量分析没有可导出的合并结果")
            target = report_dir / "DataWork_合并批量结果.xlsx"
            exporter = GenericBatchExportService()
            exporter.export_serialized(batch_payload, target)
            # 工作区继续以 XLSX 作为主下载，另外自动附带标准 Markdown/JSON 报告。
            from datawork.engine.batch import BatchAnalysisResult, BatchResult
            import pandas as pd
            rebuilt_results = [BatchResult(
                subset_key=str(item.get("subset_key") or ""),
                subset_info=dict(item.get("subset_info") or {}),
                n_rows=int(item.get("n_rows") or 0),
                omnibus_tests=list(item.get("omnibus_tests") or []),
                records=list(item.get("records") or []),
                error=str(item.get("error") or ""),
                result=StatisticalResult.model_validate(item["result"]) if item.get("result") else None,
            ) for item in batch_payload.get("results") or []]
            rebuilt = BatchAnalysisResult(
                split_cols=list(batch_payload.get("split_cols") or []),
                method=str(batch_payload.get("method") or ""),
                dv_col=str(batch_payload.get("dv_col") or ""),
                factor_cols=list(batch_payload.get("factor_cols") or []),
                results=rebuilt_results,
                summary_df=pd.DataFrame(batch_payload.get("summary") or []),
                overview_df=pd.DataFrame(batch_payload.get("overview") or []),
                settings=dict(batch_payload.get("settings") or {}),
            )
            standard_dir = report_dir / "standardized_report"
            standard_bundle = self.reports.generate(rebuilt, standard_dir, title=title)
            standard_archive = report_dir / "DataWork_规范化批量分析报告.zip"
            temporary_archive = standard_archive.with_suffix(".zip.tmp")
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for artifact in standard_bundle.artifacts:
                    artifact_path = Path(artifact.path)
                    archive.write(
                        artifact_path,
                        arcname=artifact_path.relative_to(standard_dir).as_posix(),
                    )
            temporary_archive.replace(standard_archive)
            content = target.read_bytes()
            report = self.repository.add_report(
                run_id=run_id,
                title=title,
                format="xlsx",
                stored_path=target.relative_to(self.paths.root).as_posix(),
                sha256=sha256_bytes(content),
                size_bytes=len(content),
            )
            report["artifacts"] = [
                {"path": str(target), "format": "xlsx"},
                *[item.model_dump(mode="json") for item in standard_bundle.artifacts],
                {"path": str(standard_archive), "format": "zip"},
            ]
            report["artifact_downloads"] = {
                "xlsx": f"/api/reports/{report['id']}/artifacts/xlsx",
                "zip": f"/api/reports/{report['id']}/artifacts/zip",
                "markdown": f"/api/reports/{report['id']}/artifacts/markdown",
                "json": f"/api/reports/{report['id']}/artifacts/json",
            }
            return report

        result = StatisticalResult.model_validate(execution["result"])
        bundle = self.reports.generate(result, report_dir, title=title)
        archive = report_dir.parent / f"{bundle_id}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for artifact in bundle.artifacts:
                path = Path(artifact.path)
                zip_file.write(path, arcname=path.relative_to(report_dir).as_posix())
        content = archive.read_bytes()
        report = self.repository.add_report(
            run_id=run_id,
            title=title,
            format="zip",
            stored_path=archive.relative_to(self.paths.root).as_posix(),
            sha256=sha256_bytes(content),
            size_bytes=len(content),
        )
        report["artifacts"] = [item.model_dump(mode="json") for item in bundle.artifacts]
        return report

    def report_path(self, report_id: str) -> tuple[dict[str, Any], Path]:
        report = self.repository.get_report(report_id)
        path = (self.paths.root / report["stored_path"]).resolve()
        if self.paths.root not in path.parents or not path.exists():
            raise DataWorkError(ErrorCode.REPORT_FAILED, "报告文件不存在", status_code=404)
        if sha256_bytes(path.read_bytes()) != report["sha256"]:
            raise DataWorkError(ErrorCode.REPORT_FAILED, "报告文件校验失败")
        return report, path

    def compare_runs(self, run_ids: list[str]) -> dict[str, Any]:
        if len(run_ids) < 2:
            raise DataWorkError(ErrorCode.WORKSPACE_CONFLICT, "至少需要两个运行记录进行对比")
        rows: list[dict[str, Any]] = []
        for run_id in run_ids:
            run = self.repository.get_run(run_id)
            payload = run.get("result_json") or {}
            if run["status"] != "completed" or payload.get("kind") != "single":
                rows.append({"run_id": run_id, "status": run["status"], "error": "不是可对比的单次分析"})
                continue
            result = payload["result"]
            for test in result.get("primary_tests", []):
                rows.append({
                    "run_id": run_id,
                    "plan_id": run["plan_id"],
                    "method": result.get("method", {}).get("name", ""),
                    "effect": test.get("effect"),
                    "statistic_name": test.get("statistic_name") or "statistic",
                    "statistic_value": test.get("statistic_value"),
                    "f_value": None,
                    "p_value": test.get("p_value"),
                    "eta_sq_p": None,
                    "significant": test.get("is_significant"),
                })
            for test in result.get("omnibus_tests", []):
                rows.append({
                    "run_id": run_id,
                    "plan_id": run["plan_id"],
                    "method": result.get("method", {}).get("name", ""),
                    "effect": test.get("effect"),
                    "statistic_name": test.get("statistic_name") or "F",
                    "statistic_value": test.get("statistic_value") if test.get("statistic_value") is not None else test.get("f_value"),
                    "f_value": test.get("f_value"),
                    "p_value": test.get("p_value"),
                    "eta_sq_p": None if test.get("statistic_name") else test.get("eta_sq_p"),
                    "significant": test.get("is_significant"),
                })
        return {"run_ids": run_ids, "rows": rows}

    def export_run_json(self, run_id: str, target: str | Path) -> Path:
        run = self.repository.get_run(run_id)
        path = Path(target).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
