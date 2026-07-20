from __future__ import annotations

import json
import runpy
from pathlib import Path

from fastapi.testclient import TestClient

from datawork.core.method_registry import list_methods
from datawork.web.app import create_app


_MATRIX = runpy.run_path(str(Path(__file__).parents[1] / "unit" / "test_interaction_matrix.py"))
case = _MATRIX["case"]


def _csv_payload(frame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def test_every_method_completes_preflight_and_analysis_through_http(tmp_path) -> None:
    client = TestClient(create_app(workspace_root=tmp_path / "api-matrix"))
    failures: list[tuple[str, str, str]] = []
    for method in list_methods(runnable_only=True):
        frame, kwargs = case(method.name)
        plan = {**kwargs, "method": method.name}
        csv = _csv_payload(frame)
        files = {"file": (f"{method.name}.csv", csv, "text/csv")}
        preflight = client.post(
            "/api/preflight",
            files=files,
            data={"plan_json": json.dumps(plan, ensure_ascii=False)},
        )
        if preflight.status_code != 200:
            failures.append((method.name, "preflight-http", preflight.text[:500]))
            continue
        if not preflight.json().get("ready"):
            failures.append((method.name, "preflight-domain", json.dumps(preflight.json(), ensure_ascii=False)[:1000]))
            continue
        analyze = client.post(
            "/api/analyze",
            files={"file": (f"{method.name}.csv", csv, "text/csv")},
            data={"plan_json": json.dumps(plan, ensure_ascii=False)},
        )
        if analyze.status_code != 200:
            failures.append((method.name, "analyze-http", analyze.text[:1000]))
            continue
        payload = analyze.json()
        if payload.get("kind") not in {"single", "batch"}:
            failures.append((method.name, "analyze-payload", json.dumps(payload, ensure_ascii=False)[:1000]))
    assert not failures, failures
