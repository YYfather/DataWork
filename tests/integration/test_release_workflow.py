from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import openpyxl
from fastapi.testclient import TestClient

from datawork.web.app import create_app


def _factorial_csv() -> bytes:
    rng = np.random.default_rng(20260718)
    rows = ["A,B,C,y,y1,y2"]
    for a in ["A1", "A2"]:
        for b in ["B1", "B2"]:
            for c in ["C1", "C2"]:
                for _ in range(8):
                    av, bv, cv = a == "A2", b == "B2", c == "C2"
                    latent = rng.normal()
                    y = 10 + 1.1 * av + 0.7 * bv + 0.4 * cv + 0.5 * av * bv + rng.normal(scale=0.7)
                    y1 = 3 + 0.8 * av + 0.4 * bv + latent + rng.normal(scale=0.5)
                    y2 = 2 + 0.5 * av - 0.3 * cv + 0.45 * latent + rng.normal(scale=0.6)
                    rows.append(f"{a},{b},{c},{y},{y1},{y2}")
    return ("\n".join(rows) + "\n").encode()


def test_fixed_twoway_preflight_parameter_transfer_and_batch_execution(tmp_path) -> None:
    client = TestClient(create_app(workspace_root=tmp_path))
    csv = _factorial_csv()

    profile = client.post("/api/profile", files={"file": ("design.csv", csv, "text/csv")})
    assert profile.status_code == 200
    assert profile.json()["profile"]["n_rows"] == 64

    plan = {
        "dependent_variables": ["y"],
        "fixed_factors": ["A", "B", "C"],
        "method": "twoway_anova",
        "factor_combinations_enabled": True,
        "factor_combination_min_order": 2,
        "factor_combination_max_order": 2,
        "combination_p_adjust": "holm",
        "method_parameters": {
            "posthoc_methods": ["tukey", "duncan"],
            "simple_effect_correction": "holm",
        },
    }
    preflight = client.post(
        "/api/preflight", files={"file": ("design.csv", csv, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert preflight.status_code == 200, preflight.text
    preflight_payload = preflight.json()
    assert preflight_payload["ready"] is True
    assert preflight_payload["batch_summary"]["factor_combination_count"] == 3
    assert preflight_payload["batch_summary"]["group_count"] == 3

    response = client.post(
        "/api/analyze", files={"file": ("design.csv", csv, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "batch"
    batch = payload["result"]
    assert len(batch["results"]) == 3
    assert all(not item["error"] for item in batch["results"])
    combinations = {item["subset_info"]["factor_combination"] for item in batch["results"]}
    assert combinations == {"A × B", "A × C", "B × C"}
    assert batch["settings"]["method"] == "twoway_anova"
    assert batch["settings"]["method_parameters"]["posthoc_methods"] == ["tukey", "duncan"]
    assert all(item["result"]["method"]["name"] == "twoway_anova" for item in batch["results"])
    assert batch["overview"]
    test_rows = [row for row in batch["summary"] if row["result_type"] == "test"]
    assert test_rows
    assert all(row["p_adjust_method"] == "holm" for row in test_rows)
    assert {row["p_adjust_family"] for row in test_rows} == {"F"}
    assert payload["batch_export"]["sheet_name"] == "结果总览"
    assert payload["batch_export"]["sheet_names"][:4] == ["结果总览", "批次_001", "批次_002", "批次_003"]


def test_manova_order_control_and_report_with_cld_round_trip(tmp_path) -> None:
    client = TestClient(create_app(workspace_root=tmp_path))
    csv = _factorial_csv()
    manova_plan = {
        "dependent_variables": ["y1", "y2"],
        "fixed_factors": ["A", "B", "C"],
        "method": "oneway_manova",
        "factor_combinations_enabled": True,
        "combination_p_adjust": "holm",
        "method_parameters": {
            "multivariate_test": "all",
            "primary_multivariate_test": "pillai",
            "follow_up_mode": "significant",
            "posthoc_methods": ["tukey", "duncan"],
            "covariance_test": True,
        },
    }
    response = client.post(
        "/api/analyze", files={"file": ("design.csv", csv, "text/csv")},
        data={"plan_json": json.dumps(manova_plan)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "batch"
    assert len(payload["result"]["results"]) == 3
    assert {item["subset_info"]["factor_combination"] for item in payload["result"]["results"]} == {"A", "B", "C"}
    test_rows = [row for row in payload["result"]["summary"] if row["result_type"] == "test"]
    assert {row["p_adjust_family"] for row in test_rows} == {
        "Pillai 轨迹", "Wilks' Lambda", "Hotelling–Lawley 轨迹", "Roy 最大根"
    }

    # 项目工作区：保存计划、执行、生成报告并验证字母分组工作表。
    one_way_csv = (
        "group,y\n"
        "CK,1.0\nCK,1.2\nCK,1.1\nCK,1.3\n"
        "T1,2.0\nT1,2.2\nT1,2.1\nT1,2.3\n"
        "T2,3.0\nT2,3.2\nT2,3.1\nT2,3.3\n"
    ).encode()
    project = client.post("/api/projects", json={"name": "Release audit", "description": "workflow"}).json()
    dataset = client.post(
        f"/api/projects/{project['id']}/datasets",
        files={"file": ("oneway.csv", one_way_csv, "text/csv")}, data={"name": "oneway"},
    ).json()
    plan = client.post(
        f"/api/projects/{project['id']}/plans",
        json={
            "dataset_id": dataset["id"], "name": "CLD",
            "plan": {
                "dependent_variables": ["y"], "fixed_factors": ["group"],
                "method": "oneway_anova",
                "method_parameters": {"posthoc_methods": ["tukey", "duncan"]},
            },
        },
    ).json()
    run_response = client.post(f"/api/plans/{plan['id']}/runs")
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    letters = run["result_json"]["result"]["significance_letters"]
    assert letters and {item["method"] for item in letters} == {"Tukey–Kramer HSD", "Duncan 多重极差（宽松）"}

    report = client.post(f"/api/runs/{run['id']}/reports", json={"title": "Release audit"})
    assert report.status_code == 201, report.text
    download = client.get(f"/api/reports/{report.json()['id']}/download")
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert {"statistical_report.md", "canonical_result.json", "results.xlsx"} <= set(archive.namelist())
        workbook = openpyxl.load_workbook(io.BytesIO(archive.read("results.xlsx")), read_only=True)
        assert "显著性字母分组" in workbook.sheetnames
        text = archive.read("statistical_report.md").decode("utf-8")
        assert "显著性字母分组" in text
        assert "Tukey" in text and "Duncan" in text
