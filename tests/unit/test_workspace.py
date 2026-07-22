from pathlib import Path

import pytest

from datawork.application.workspace_service import WorkspaceService
from datawork.core.errors import DataWorkError
from datawork.infrastructure.paths import default_workspace_root


CSV = b"group,value\nA,1\nA,2\nA,3\nB,3\nB,4\nB,5\n"
PLAN = {
    "dependent_variables": ["value"],
    "fixed_factors": ["group"],
    "method": "welch_ttest",
}


def _make_workspace(tmp_path: Path):
    service = WorkspaceService(tmp_path)
    project = service.create_project("试验项目")
    dataset = service.add_dataset(project["id"], content=CSV, filename="sample.csv")
    plan = service.create_plan(project["id"], dataset["id"], name="Welch", plan_data=PLAN)
    return service, project, dataset, plan


def test_workspace_persists_project_dataset_plan_run_and_report(tmp_path: Path):
    service, project, dataset, plan = _make_workspace(tmp_path)
    assert service.preflight_plan(plan["id"])["prior_run_count"] == 0
    run = service.run_plan(plan["id"])
    assert run["status"] == "completed"
    assert service.preflight_plan(plan["id"])["prior_run_count"] == 1
    assert run["result_json"]["provenance"]["dataset"]["source_sha256"] == dataset["source_sha256"]

    report = service.generate_report(run["id"], title="回归测试")
    report_record, report_path = service.report_path(report["id"])
    assert report_path.exists()
    assert report_path.suffix == ".zip"
    assert report_record["sha256"] == report["sha256"]

    reopened = WorkspaceService(tmp_path)
    assert reopened.repository.get_project(project["id"])["name"] == "试验项目"
    assert reopened.repository.get_run(run["id"])["status"] == "completed"


def test_workspace_detects_modified_source_file(tmp_path: Path):
    service, _project, dataset, plan = _make_workspace(tmp_path)
    source_path = service.paths.root / dataset["stored_path"]
    source_path.write_bytes(CSV + b"A,99\n")
    with pytest.raises(DataWorkError, match="哈希"):
        service.run_plan(plan["id"])


def test_plan_clone_and_run_comparison(tmp_path: Path):
    service, _project, _dataset, plan = _make_workspace(tmp_path)
    clone = service.clone_plan(plan["id"])
    first = service.run_plan(plan["id"])
    second = service.run_plan(clone["id"])
    comparison = service.compare_runs([first["id"], second["id"]])
    assert len(comparison["rows"]) == 2
    assert {row["run_id"] for row in comparison["rows"]} == {first["id"], second["id"]}


def test_workspace_automatically_persists_saved_derived_role_migration(tmp_path: Path):
    service, project, _dataset, plan = _make_workspace(tmp_path)
    old = {
        "interface_mode": "professional", "method": "welch_ttest",
        "dependent_variables": ["custom"], "fixed_factors": ["group"],
        "split_by": ["custom"],
        "derived_columns": [{"name": "custom", "formula": "[value] + 1", "source_columns": ["value"]}],
    }
    service.repository.update_plan(plan["id"], name=plan["name"], plan=old, plan_sha256="old")

    migrated = service.list_plans(project["id"])[0]
    assert migrated["plan_json"]["split_by"] == []
    assert migrated["migration_warnings"]
    migrated_revision = migrated["revision"]

    loaded_again = service.list_plans(project["id"])[0]
    assert loaded_again["migration_warnings"] == []
    assert loaded_again["revision"] == migrated_revision


def test_datawork_home_override_is_cross_platform(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATAWORK_HOME", str(tmp_path / "portable"))
    assert default_workspace_root() == (tmp_path / "portable").resolve()
