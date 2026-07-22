from __future__ import annotations

import base64
import hashlib
import json

from fastapi.testclient import TestClient

from datawork.ai.provider import LLMResponse
from datawork.ai.settings import (
    AISettings,
    AISettingsService,
    SecretStorage,
)
from datawork.infrastructure.paths import resolve_workspace_paths
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


class FakeProvider:
    async def generate_text(self, messages):
        return LLMResponse(content="**回答：** 已处理。", model="server-model")

    async def close(self):
        return None


def configure_server_ai(root) -> None:
    service = AISettingsService(resolve_workspace_paths(root / "server_ai"))
    service.save(
        AISettings(
            enabled=True,
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="server-model",
        ),
        api_key="server-secret",
        secret_storage=SecretStorage.SERVER_FILE,
    )


def write_auth_config(root) -> None:
    salt = b"datawork-test-salt-2026"
    digest = hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), salt, 200_000)
    (root / "workspace_auth.json").write_text(json.dumps({
        "algorithm": "pbkdf2_sha256",
        "iterations": 200_000,
        "salt": base64.b64encode(salt).decode(),
        "digest": base64.b64encode(digest).decode(),
        "cleanup_expired_sessions": True,
    }), encoding="utf-8")


def ask(client: TestClient):
    return client.post("/api/ai/ask", json={"question": "请直接回答。"})


def test_guest_can_use_server_ai_ten_times_then_must_authenticate_or_use_own_key(
    tmp_path, monkeypatch
):
    configure_server_ai(tmp_path)
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: FakeProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))

    responses = [ask(client) for _ in range(10)]
    assert all(response.status_code == 200 for response in responses)
    assert responses[-1].json()["ai_access"]["guest_quota"]["remaining"] == 0
    exhausted = ask(client)
    assert exhausted.status_code == 429
    assert exhausted.json()["error"]["code"] == "ai_free_quota_exhausted"
    assert exhausted.json()["error"]["details"]["reset_seconds"] > 0


def test_workspace_owner_bypasses_guest_quota(tmp_path, monkeypatch):
    configure_server_ai(tmp_path)
    write_auth_config(tmp_path)
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: FakeProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    for _ in range(10):
        assert ask(client).status_code == 200
    assert ask(client).status_code == 429

    login = client.post("/api/workspace-auth/login", json={"password": PASSWORD})
    assert login.status_code == 200
    owner_answer = ask(client)
    assert owner_answer.status_code == 200
    access = owner_answer.json()["ai_access"]
    assert access["owner_authenticated"] is True
    assert access["configuration_source"] == "server"


def test_personal_api_bypasses_exhausted_server_quota(tmp_path, monkeypatch):
    configure_server_ai(tmp_path)
    monkeypatch.setattr(
        "datawork.application.ai_assistant_service.create_provider",
        lambda config: FakeProvider(),
    )
    client = TestClient(create_app(workspace_root=tmp_path))
    for _ in range(10):
        assert ask(client).status_code == 200
    assert ask(client).status_code == 429

    saved = client.put("/api/ai/settings", json={
        "enabled": True,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "personal-model",
        "privacy_mode": "metadata_only",
        "remember_key": False,
        "secret_storage": "session",
        "api_key": "personal-secret",
    })
    assert saved.status_code == 200
    personal_answer = ask(client)
    assert personal_answer.status_code == 200
    assert personal_answer.json()["ai_access"]["configuration_source"] == "personal"


def test_guest_quota_resets_twenty_four_hours_after_first_question(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(
        tmp_path,
        clock=clock,
        quota_clock=clock,
        ai_guest_question_limit=10,
    )
    session_id = "11111111-1111-4111-8111-111111111111"

    for remaining in range(9, -1, -1):
        assert registry.consume_ai_guest_question(session_id)["remaining"] == remaining
    assert registry.consume_ai_guest_question(session_id) is None
    clock.advance(24 * 60 * 60 - 1)
    assert registry.ai_quota_status(session_id)["remaining"] == 0
    clock.advance(1)
    reset = registry.ai_quota_status(session_id)
    assert reset == {
        "used": 0,
        "limit": 10,
        "remaining": 10,
        "resets_in_seconds": 0,
    }


def test_guest_quota_survives_server_restart(tmp_path):
    clock = FakeClock()
    session_id = "22222222-2222-4222-8222-222222222222"
    first_registry = SessionRegistry(tmp_path, quota_clock=clock)
    assert first_registry.consume_ai_guest_question(session_id)["remaining"] == 9

    restarted_registry = SessionRegistry(tmp_path, quota_clock=clock)
    assert restarted_registry.ai_quota_status(session_id)["remaining"] == 9
    assert (tmp_path / "ai_guest_quota.json").is_file()
