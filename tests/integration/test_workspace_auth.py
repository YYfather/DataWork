from __future__ import annotations

import base64
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from datawork.web.app import create_app
from datawork.web.sessions import SessionRegistry


PASSWORD = "owner-test-password"


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def write_auth_config(root, password: str = PASSWORD) -> None:
    salt = b"datawork-test-salt-2026"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    (root / "workspace_auth.json").write_text(json.dumps({
        "algorithm": "pbkdf2_sha256",
        "iterations": 200_000,
        "salt": base64.b64encode(salt).decode(),
        "digest": base64.b64encode(digest).decode(),
        "cleanup_expired_sessions": True,
    }), encoding="utf-8")


@pytest.mark.parametrize("path", [
    "/api/workspace",
    "/api/projects",
    "/api/projects/example",
    "/api/datasets/example",
    "/api/plans/example",
    "/api/runs/example",
    "/api/reports/example/download",
])
def test_workspace_routes_require_owner_authentication(tmp_path, path):
    write_auth_config(tmp_path)
    client = TestClient(create_app(workspace_root=tmp_path))
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "workspace_auth_required"


def test_authenticated_browsers_share_one_owner_workspace(tmp_path):
    write_auth_config(tmp_path)
    app = create_app(workspace_root=tmp_path)
    first = TestClient(app)
    second = TestClient(app)

    assert first.get("/api/workspace-auth/status").json()["authenticated"] is False
    wrong = first.post("/api/workspace-auth/login", json={"password": "wrong"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "workspace_auth_failed"
    assert first.post("/api/workspace-auth/login", json={"password": PASSWORD}).status_code == 200

    project = first.post("/api/projects", json={"name": "所有者项目", "description": "持久"})
    assert project.status_code == 201
    info = first.get("/api/workspace").json()
    assert info["owner_only"] is True
    assert info["project_count"] == 1
    assert info["used_bytes"] > 0

    assert second.get("/api/projects").status_code == 401
    assert second.post("/api/workspace-auth/login", json={"password": PASSWORD}).status_code == 200
    assert [item["name"] for item in second.get("/api/projects").json()] == ["所有者项目"]
    assert second.post("/api/workspace-auth/logout").json()["authenticated"] is False
    assert second.get("/api/projects").status_code == 401


def test_five_bad_passwords_lock_only_that_browser_session(tmp_path):
    write_auth_config(tmp_path)
    app = create_app(workspace_root=tmp_path)
    attacker = TestClient(app)
    owner = TestClient(app)
    responses = [
        attacker.post("/api/workspace-auth/login", json={"password": "wrong"})
        for _ in range(5)
    ]
    assert [response.status_code for response in responses] == [401, 401, 401, 401, 429]
    assert responses[-1].json()["error"]["code"] == "workspace_auth_locked"
    assert owner.post("/api/workspace-auth/login", json={"password": PASSWORD}).status_code == 200


def test_expiry_removes_temporary_session_data_but_keeps_owner_workspace(tmp_path):
    write_auth_config(tmp_path)
    clock = FakeClock()
    registry = SessionRegistry(tmp_path, max_sessions=3, timeout_seconds=600, clock=clock)
    app = create_app(session_registry=registry)
    owner = TestClient(app)
    assert owner.post("/api/workspace-auth/login", json={"password": PASSWORD}).status_code == 200
    assert owner.post("/api/projects", json={"name": "保留项目", "description": ""}).status_code == 201

    session_root = next((tmp_path / "users").iterdir())
    (session_root / "temporary.txt").write_text("temporary", encoding="utf-8")
    clock.advance(601)
    expired = owner.get("/api/session/status")
    assert expired.json()["expired"] is True
    assert not session_root.exists()
    assert (tmp_path / "owner" / "workspace.sqlite3").is_file()

    replacement = TestClient(app)
    assert replacement.post("/api/workspace-auth/login", json={"password": PASSWORD}).status_code == 200
    assert [item["name"] for item in replacement.get("/api/projects").json()] == ["保留项目"]
