from itertools import product
import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from datawork.web.app import create_app


def _csv() -> bytes:
    rng = np.random.default_rng(77)
    rows: list[dict[str, object]] = []
    for levels in product([0, 1], repeat=4):
        for replicate in range(6):
            signal = levels[0] + 0.6 * levels[1] + 0.4 * levels[0] * levels[1]
            rows.append({
                **{f"F{index + 1}": f"L{level}" for index, level in enumerate(levels)},
                "y1": signal + rng.normal(scale=0.45),
                "y2": 0.5 * signal + rng.normal(scale=0.55),
                "batch": f"B{replicate % 2 + 1}",
            })
    return pd.DataFrame(rows).to_csv(index=False).encode()


def test_four_factor_anova_runs_through_http(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path / "anova"))
    response = client.post(
        "/api/analyze",
        files={"file": ("four-factor.csv", _csv(), "text/csv")},
        data={"plan_json": json.dumps({
            "dependent_variables": ["y1"],
            "fixed_factors": ["F1", "F2", "F3", "F4"],
            "method": "multifactor_anova",
            "method_parameters": {"factor_model_order": 4},
            "ss_type": 3,
            "diagnostic_plots": False,
        })},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["method"]["name"] == "multifactor_anova"
    assert len(result["omnibus_tests"]) == 15
    assert result["data_snapshot"]["factor_count"] == 4


def test_four_factor_manova_runs_through_http(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path / "manova"))
    response = client.post(
        "/api/analyze",
        files={"file": ("four-factor-manova.csv", _csv(), "text/csv")},
        data={"plan_json": json.dumps({
            "dependent_variables": ["y1", "y2"],
            "fixed_factors": ["F1", "F2", "F3", "F4"],
            "method": "multifactor_manova",
            "method_parameters": {
                "factor_model_order": 4,
                "multivariate_test": "pillai",
                "primary_multivariate_test": "pillai",
                "follow_up_mode": "none",
                "covariance_test": False,
                "normality_test": False,
                "correlation_diagnostics": False,
            },
        })},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["method"]["name"] == "manova"
    assert len(result["omnibus_tests"]) == 15
    assert result["data_snapshot"]["factor_count"] == 4


def test_four_factor_anova_can_split_by_professional_group_columns(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path / "split"))
    response = client.post(
        "/api/analyze",
        files={"file": ("four-factor-split.csv", _csv(), "text/csv")},
        data={"plan_json": json.dumps({
            "dependent_variables": ["y1"],
            "fixed_factors": ["F1", "F2", "F3", "F4"],
            "split_by": ["batch"],
            "split_rules": [{
                "column": "batch",
                "kind": "categorical",
                "groups": [{"label": "合并批次", "values": ["B1", "B2"]}],
            }],
            "method": "multifactor_anova",
            "method_parameters": {"factor_model_order": 4},
            "ss_type": 3,
            "diagnostic_plots": False,
            "factor_combinations_enabled": False,
        })},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "batch"
    assert payload["result"]["split_cols"] == ["batch"]
    assert len(payload["result"]["results"]) == 1
    assert payload["result"]["results"][0]["subset_info"]["batch"] == "合并批次"
    assert all(not item["error"] for item in payload["result"]["results"])
