"""SQLite 工作区仓储。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from datawork.core.errors import ResourceNotFoundError
from datawork.infrastructure.paths import WorkspacePaths, resolve_workspace_paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _decode_record(row: sqlite3.Row | None, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for field in json_fields:
        raw = result.get(field)
        result[field] = json.loads(raw) if raw else None
    return result


SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    percentage_scale TEXT NOT NULL DEFAULT 'percent_points',
    source_sha256 TEXT NOT NULL,
    cleaned_sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    profile_json TEXT NOT NULL,
    fingerprint_json TEXT NOT NULL,
    cleaning_log_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_datasets_project ON datasets(project_id, created_at);
CREATE TABLE IF NOT EXISTS analysis_plans (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    plan_sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    parent_plan_id TEXT REFERENCES analysis_plans(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_project ON analysis_plans(project_id, updated_at);
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES analysis_plans(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    result_json TEXT,
    error_json TEXT,
    provenance_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON analysis_runs(project_id, started_at);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    format TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_run ON reports(run_id, created_at);
"""


class WorkspaceRepository:
    def __init__(self, root: str | Path | None = None) -> None:
        self.paths: WorkspacePaths = resolve_workspace_paths(root)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.paths.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO workspace_meta(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            row = connection.execute(
                "SELECT value FROM workspace_meta WHERE key='schema_version'"
            ).fetchone()
            actual = int(row[0]) if row else 0
            if actual > SCHEMA_VERSION:
                raise RuntimeError(
                    f"工作区数据库版本 {actual} 高于当前程序支持的 {SCHEMA_VERSION}"
                )

    @property
    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM workspace_meta WHERE key='schema_version'"
            ).fetchone()
        return int(row[0]) if row else 0

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        project_id = _id("prj")
        now = _now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO projects(id,name,description,created_at,updated_at) VALUES(?,?,?,?,?)",
                (project_id, name.strip(), description.strip(), now, now),
            )
        return self.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT p.*,
                   (SELECT COUNT(*) FROM datasets d WHERE d.project_id=p.id) AS dataset_count,
                   (SELECT COUNT(*) FROM analysis_plans ap WHERE ap.project_id=p.id) AS plan_count,
                   (SELECT COUNT(*) FROM analysis_runs ar WHERE ar.project_id=p.id) AS run_count
                   FROM projects p ORDER BY p.updated_at DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        record = _decode_record(row)
        if not record:
            raise ResourceNotFoundError("项目", project_id)
        return record

    def touch_project(self, project_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project_id))

    def add_dataset(self, record: dict[str, Any]) -> dict[str, Any]:
        dataset_id = record.get("id") or _id("ds")
        created_at = _now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO datasets(
                id,project_id,name,original_filename,stored_path,sheet_name,percentage_scale,
                source_sha256,cleaned_sha256,size_bytes,profile_json,fingerprint_json,
                cleaning_log_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dataset_id, record["project_id"], record["name"], record["original_filename"],
                    record["stored_path"], record.get("sheet_name", ""),
                    record.get("percentage_scale", "percent_points"), record["source_sha256"],
                    record["cleaned_sha256"], record["size_bytes"], _json(record["profile"]),
                    _json(record["fingerprint"]), _json(record["cleaning_log"]), created_at,
                ),
            )
        self.touch_project(record["project_id"])
        return self.get_dataset(dataset_id)

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        record = _decode_record(row, ("profile_json", "fingerprint_json", "cleaning_log_json"))
        if not record:
            raise ResourceNotFoundError("数据集", dataset_id)
        return record

    def list_datasets(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM datasets WHERE project_id=? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        return [
            _decode_record(row, ("profile_json", "fingerprint_json", "cleaning_log_json"))
            for row in rows
        ]

    def create_plan(
        self,
        *,
        project_id: str,
        dataset_id: str,
        name: str,
        plan: dict[str, Any],
        plan_sha256: str,
        parent_plan_id: str | None = None,
    ) -> dict[str, Any]:
        plan_id = _id("plan")
        now = _now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO analysis_plans(
                id,project_id,dataset_id,name,plan_json,plan_sha256,revision,parent_plan_id,
                created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?,?)""",
                (plan_id, project_id, dataset_id, name, _json(plan), plan_sha256, parent_plan_id, now, now),
            )
        self.touch_project(project_id)
        return self.get_plan(plan_id)

    def update_plan(self, plan_id: str, *, name: str, plan: dict[str, Any], plan_sha256: str) -> dict[str, Any]:
        existing = self.get_plan(plan_id)
        with self.connect() as connection:
            connection.execute(
                """UPDATE analysis_plans SET name=?, plan_json=?, plan_sha256=?,
                revision=revision+1, updated_at=? WHERE id=?""",
                (name, _json(plan), plan_sha256, _now(), plan_id),
            )
        self.touch_project(existing["project_id"])
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM analysis_plans WHERE id=?", (plan_id,)).fetchone()
        record = _decode_record(row, ("plan_json",))
        if not record:
            raise ResourceNotFoundError("分析计划", plan_id)
        return record

    def list_plans(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_plans WHERE project_id=? ORDER BY updated_at DESC", (project_id,)
            ).fetchall()
        return [_decode_record(row, ("plan_json",)) for row in rows]

    def begin_run(self, project_id: str, dataset_id: str, plan_id: str, *, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or _id("run")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO analysis_runs(
                id,project_id,dataset_id,plan_id,status,started_at) VALUES(?,?,?,?,?,?)""",
                (run_id, project_id, dataset_id, plan_id, "running", _now()),
            )
        return self.get_run(run_id)

    def complete_run(
        self,
        run_id: str,
        *,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = "failed" if error else "completed"
        with self.connect() as connection:
            connection.execute(
                """UPDATE analysis_runs SET status=?, result_json=?, error_json=?, provenance_json=?,
                completed_at=? WHERE id=?""",
                (
                    status,
                    _json(result) if result is not None else None,
                    _json(error) if error is not None else None,
                    _json(provenance) if provenance is not None else None,
                    _now(), run_id,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
        record = _decode_record(row, ("result_json", "error_json", "provenance_json"))
        if not record:
            raise ResourceNotFoundError("分析运行", run_id)
        return record

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.*, p.name AS plan_name, d.name AS dataset_name
                FROM analysis_runs r
                JOIN analysis_plans p ON p.id=r.plan_id
                JOIN datasets d ON d.id=r.dataset_id
                WHERE r.project_id=? ORDER BY r.started_at DESC""",
                (project_id,),
            ).fetchall()
        return [_decode_record(row, ("result_json", "error_json", "provenance_json")) for row in rows]

    def count_plan_runs(self, plan_id: str) -> int:
        """返回同一已保存计划已经创建的运行次数，不读取历史结果正文。"""
        self.get_plan(plan_id)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS run_count FROM analysis_runs WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
        return int(row["run_count"] if row else 0)

    def add_report(
        self,
        *,
        run_id: str,
        title: str,
        format: str,
        stored_path: str,
        sha256: str,
        size_bytes: int,
    ) -> dict[str, Any]:
        report_id = _id("report")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reports(id,run_id,title,format,stored_path,sha256,size_bytes,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (report_id, run_id, title, format, stored_path, sha256, size_bytes, _now()),
            )
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        record = _decode_record(row)
        if not record:
            raise ResourceNotFoundError("报告", report_id)
        return record

    def list_reports(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM reports WHERE run_id=? ORDER BY created_at DESC", (run_id,)
            ).fetchall()
        return [dict(row) for row in rows]
