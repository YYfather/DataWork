import io
import zipfile

from fastapi.testclient import TestClient

from datawork.web.app import create_app


CSV = b"group,value\nA,1\nA,2\nA,3\nB,3\nB,4\nB,5\n"
PLAN = {
    "dependent_variables": ["value"],
    "fixed_factors": ["group"],
    "method": "welch_ttest",
}


def test_workspace_api_full_flow(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))

    project_response = client.post("/api/projects", json={"name": "Demo", "description": "API"})
    assert project_response.status_code == 201
    project = project_response.json()

    dataset_response = client.post(
        f"/api/projects/{project['id']}/datasets",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"name": "原始数据"},
    )
    assert dataset_response.status_code == 201, dataset_response.text
    dataset = dataset_response.json()
    assert dataset["fingerprint_json"]["n_rows"] == 6

    plan_response = client.post(
        f"/api/projects/{project['id']}/plans",
        json={"dataset_id": dataset["id"], "name": "Welch", "plan": PLAN},
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()

    run_response = client.post(f"/api/plans/{plan['id']}/runs")
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    assert run["status"] == "completed"
    assert run["result_json"]["kind"] == "single"

    report_response = client.post(
        f"/api/runs/{run['id']}/reports",
        json={"title": "Demo Report"},
    )
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()

    download = client.get(f"/api/reports/{report['id']}/download")
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert "statistical_report.md" in archive.namelist()
        assert "canonical_result.json" in archive.namelist()

    project_detail = client.get(f"/api/projects/{project['id']}").json()
    assert len(project_detail["datasets"]) == 1
    assert len(project_detail["plans"]) == 1
    assert len(project_detail["runs"]) == 1


def test_workspace_derived_preview_and_saved_plan(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path / "derived-workspace"))
    project = client.post("/api/projects", json={"name": "Derived", "description": ""}).json()
    dataset = client.post(
        f"/api/projects/{project['id']}/datasets",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"name": "原始数据"},
    ).json()
    definitions = [{"name": "value_plus_one", "formula": "[value] + 1", "source_columns": ["value"]}]
    preview = client.post(
        f"/api/datasets/{dataset['id']}/derived-preview",
        json={"derived_columns": definitions},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"][0]["value_plus_one"] == 2
    saved = client.post(
        f"/api/projects/{project['id']}/plans",
        json={
            "dataset_id": dataset["id"], "name": "Derived plan",
            "plan": {
                "interface_mode": "professional",
                "dependent_variables": ["value_plus_one"],
                "fixed_factors": ["group"],
                "derived_columns": definitions,
                "method": "welch_ttest",
            },
        },
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["plan_json"]["derived_columns"] == definitions


def test_api_returns_structured_domain_error(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.get("/api/projects/missing")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "resource_not_found"
    assert payload["detail"]


def test_workspace_batch_preflight_and_merged_xlsx_report(tmp_path):
    import openpyxl

    client = TestClient(create_app(workspace_root=tmp_path / "batch-workspace"))
    csv = (
        "batch,group,y1,y2\n"
        "one,A,1,10\none,A,2,11\none,A,3,12\n"
        "one,B,4,15\none,B,5,16\none,B,6,17\n"
        "two,A,2,11\ntwo,A,3,12\ntwo,A,4,13\n"
        "two,B,5,16\ntwo,B,6,17\ntwo,B,7,18\n"
    ).encode()
    project = client.post("/api/projects", json={"name": "Batch", "description": ""}).json()
    dataset = client.post(
        f"/api/projects/{project['id']}/datasets",
        files={"file": ("batch.csv", csv, "text/csv")},
        data={"name": "批量数据"},
    ).json()
    plan_payload = {
        "dependent_variables": ["y1", "y2"],
        "fixed_factors": ["group"],
        "split_by": ["batch"],
        "method": "welch_ttest",
        "interface_mode": "concise",
        "cross_model_p_adjust": "fdr_bh",
    }
    plan = client.post(
        f"/api/projects/{project['id']}/plans",
        json={"dataset_id": dataset["id"], "name": "Generic batch", "plan": plan_payload},
    ).json()

    check = client.get(f"/api/plans/{plan['id']}/preflight")
    assert check.status_code == 200, check.text
    assert check.json()["ready"] is True
    assert check.json()["batch_summary"]["group_count"] == 4
    assert check.json()["batch_summary"]["p_adjust"] == "fdr_bh"
    assert check.json()["prior_run_count"] == 0

    run = client.post(f"/api/plans/{plan['id']}/runs").json()
    assert run["result_json"]["kind"] == "batch"
    assert len(run["result_json"]["result"]["summary"]) == 4
    assert {row["p_adjust_method"] for row in run["result_json"]["result"]["summary"]} == {"fdr_bh"}
    assert client.get(f"/api/plans/{plan['id']}/preflight").json()["prior_run_count"] == 1

    report = client.post(
        f"/api/runs/{run['id']}/reports",
        json={"title": "Batch XLSX"},
    )
    assert report.status_code == 201, report.text
    report_payload = report.json()
    assert set(report_payload["artifact_downloads"]) == {"xlsx", "zip", "markdown", "json"}
    download = client.get(f"/api/reports/{report_payload['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = openpyxl.load_workbook(io.BytesIO(download.content), read_only=True)
    assert workbook.sheetnames == [
        "结果总览", "批次_001", "批次_002", "批次_003", "批次_004", "失败与警告", "分析设置",
    ]

    artifact_responses = {
        kind: client.get(url) for kind, url in report_payload["artifact_downloads"].items()
    }
    assert all(response.status_code == 200 for response in artifact_responses.values())
    assert artifact_responses["markdown"].headers["content-type"].startswith("text/markdown")
    assert "## 二、规范化结果摘要" in artifact_responses["markdown"].text
    assert artifact_responses["json"].json()["schema_version"] == "datawork.standard-report.v1"
    with zipfile.ZipFile(io.BytesIO(artifact_responses["zip"].content)) as archive:
        assert {"statistical_report.md", "canonical_result.json", "results.xlsx"}.issubset(archive.namelist())
