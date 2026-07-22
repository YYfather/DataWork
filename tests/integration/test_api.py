import json

import numpy as np
from fastapi.testclient import TestClient

from datawork.web.app import app


client = TestClient(app)
CSV = "group,value\nA,1\nA,2\nA,3\nB,3\nB,4\nB,5\n".encode()


def test_health_and_methods():
    health = client.get("/api/health")
    assert health.status_code == 200
    methods = client.get("/api/methods").json()
    ancova = next(item for item in methods if item["name"] == "ancova")
    assert ancova["runnable"] is True
    assert ancova["purpose"]
    assert ancova["variable_requirements"]
    assert ancova["output_metrics"]

    chi_square = next(item for item in methods if item["name"] == "chi_square_independence")
    assert chi_square["runnable"] is True
    parameter_names = {item["key"] for item in chi_square["parameters"]}
    assert {"continuity_correction", "p_value_method", "n_resamples"} <= parameter_names

    manova_methods = {item["name"]: item for item in methods if item["name"].endswith("way_manova")}
    assert set(manova_methods) == {"oneway_manova", "twoway_manova", "threeway_manova"}
    assert manova_methods["oneway_manova"]["min_fixed_factors"] == manova_methods["oneway_manova"]["max_fixed_factors"] == 1
    assert manova_methods["twoway_manova"]["min_fixed_factors"] == manova_methods["twoway_manova"]["max_fixed_factors"] == 2
    assert manova_methods["threeway_manova"]["min_fixed_factors"] == manova_methods["threeway_manova"]["max_fixed_factors"] == 3
    assert all("factor_model_order" not in {parameter["key"] for parameter in item["parameters"]} for item in manova_methods.values())
    manova_parameter = next(item for item in manova_methods["twoway_manova"]["parameters"] if item["key"] == "multivariate_test")
    assert {option["value"] for option in manova_parameter["options"]} == {"all", "pillai", "wilks", "hotelling_lawley", "roy"}

    method_names = {item["name"] for item in methods}
    assert "factorial_anova" not in method_names
    assert {
        "cohen_kappa",
        "fleiss_kappa",
        "cochran_armitage_trend",
        "multinomial_logistic_regression",
        "ordinal_logistic_regression",
    } <= method_names


def test_desktop_origins_can_probe_health():
    for origin in (
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ):
        response = client.get("/api/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_profile_and_analyze_upload():
    response = client.post(
        "/api/profile",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"percentage_scale": "percent_points"},
    )
    assert response.status_code == 200
    assert response.json()["profile"]["n_rows"] == 6

    plan = {
        "dependent_variables": ["value"],
        "fixed_factors": ["group"],
        "method": "welch_ttest",
    }
    response = client.post(
        "/api/analyze",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "single"
    assert payload["result"]["method"]["name"] == "welch_ttest"


def test_derived_preview_and_professional_analysis():
    response = client.post(
        "/api/derived/preview",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={
            "derived_columns_json": json.dumps([{
                "name": "double_value",
                "formula": "[value] * 2",
                "source_columns": ["value"],
            }]),
        },
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert "double_value" in preview["columns"]
    assert preview["preview"][0]["double_value"] == 2

    plan = {
        "interface_mode": "professional",
        "dependent_variables": ["double_value"],
        "fixed_factors": ["group"],
        "derived_columns": [{
            "name": "double_value",
            "formula": "[value] * 2",
            "source_columns": ["value"],
        }],
        "method": "welch_ttest",
    }
    response = client.post(
        "/api/analyze",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan"]["derived_columns"][0]["name"] == "double_value"
    operations = payload["provenance"]["cleaning_log"]
    assert any(item["operation"] == "derive_column" for item in operations)


def test_professional_split_factor_overlap_is_validated_per_group():
    csv = (
        "factor,value\n"
        "A,1\nA,2\nB,3\nB,4\nC,5\nC,6\nD,7\nD,8\n"
    ).encode()
    plan = {
        "interface_mode": "professional",
        "dependent_variables": ["value"],
        "fixed_factors": ["factor"],
        "split_by": ["factor"],
        "split_rules": [{
            "column": "factor", "kind": "categorical",
            "groups": [
                {"label": "front", "values": ["A", "B"]},
                {"label": "back", "values": ["C", "D"]},
            ],
        }],
        "method": "oneway_anova",
    }
    response = client.post(
        "/api/preflight",
        files={"file": ("factor.csv", csv, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True
    assert response.json()["batch_summary"]["group_count"] == 2


def test_mixed_anova_returns_role_validation_error():
    plan = {
        "dependent_variables": ["value"],
        "fixed_factors": ["group"],
        "method": "mixed_anova",
    }
    response = client.post(
        "/api/analyze",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 422
    assert "受试者/样本 ID" in response.json()["detail"]


def test_phase3_capabilities_endpoint():
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_contract"] == "phase3-v1"
    assert payload["statistics"]["mixed_anova"] is True
    assert payload["statistics"]["random_slopes"] is True
    assert payload["statistics"]["method_count"] == payload["statistics"]["runnable_method_count"]


def test_unexpected_api_error_is_structured_and_actionable(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("internal details must not leak")

    import importlib
    app_module = importlib.import_module("datawork.web.app")
    monkeypatch.setattr(app_module.AnalysisService, "execute", explode)
    safe_client = TestClient(app, raise_server_exceptions=False)
    plan = {"dependent_variables": ["value"], "fixed_factors": ["group"], "method": "welch_ttest"}
    response = safe_client.post(
        "/api/analyze",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "internal_error"
    assert "不会被修改" in payload["detail"]
    assert "internal details" not in response.text


def test_two_factor_manova_and_selected_statistic_via_http():
    rng = np.random.default_rng(20260718)
    rows = ["treatment,variety,y1,y2"]
    for treatment in ["CK", "T"]:
        for variety in ["V1", "V2"]:
            for _ in range(18):
                t = 1 if treatment == "T" else 0
                v = 1 if variety == "V2" else 0
                interaction = 0.45 if t and v else 0.0
                latent = rng.normal()
                y1 = 4 + 0.8 * t + 0.4 * v + interaction + latent + rng.normal(scale=0.5)
                y2 = 2 + 0.5 * t - 0.3 * v + 0.3 * interaction + 0.45 * latent + rng.normal(scale=0.6)
                rows.append(f"{treatment},{variety},{y1},{y2}")
    csv_bytes = ("\n".join(rows) + "\n").encode()
    plan = {
        "dependent_variables": ["y1", "y2"],
        "fixed_factors": ["treatment", "variety"],
        "method": "twoway_manova",
        "method_parameters": {"multivariate_test": "pillai"},
    }
    response = client.post(
        "/api/analyze",
        files={"file": ("manova.csv", csv_bytes, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["method"]["name"] == "manova"
    assert len(result["omnibus_tests"]) == 3
    assert {item["effect"] for item in result["omnibus_tests"]} == {
        "treatment", "variety", "treatment × variety"
    }
    assert {item["statistic_name"] for item in result["omnibus_tests"]} == {"Pillai 轨迹"}
    assert all(item["statistic_value"] is not None for item in result["omnibus_tests"])


def test_instant_single_result_can_download_excel_and_complete_report(tmp_path):
    import io
    import zipfile
    from datawork.web.app import create_app

    local_client = TestClient(create_app(workspace_root=tmp_path / "instant-report"))
    plan = {"dependent_variables": ["value"], "fixed_factors": ["group"], "method": "welch_ttest"}
    analysis = local_client.post(
        "/api/analyze",
        files={"file": ("sample.csv", CSV, "text/csv")},
        data={"plan_json": json.dumps(plan)},
    )
    assert analysis.status_code == 200, analysis.text
    report = local_client.post(
        "/api/instant/reports",
        json={"execution": analysis.json(), "title": "Simple test report"},
    )
    assert report.status_code == 201, report.text
    payload = report.json()
    excel = local_client.get(payload["xlsx_download_url"])
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    archive = local_client.get(payload["download_url"])
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert {"results.xlsx", "statistical_report.md", "canonical_result.json"} <= set(bundle.namelist())
