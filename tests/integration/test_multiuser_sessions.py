from __future__ import annotations

from fastapi.testclient import TestClient

from datawork.web.app import create_app
from datawork.web.sessions import SessionRegistry


SESSION_ID = "11111111-1111-4111-8111-111111111111"
FIRST_PAGE_ID = "22222222-2222-4222-8222-222222222222"
SECOND_PAGE_ID = "33333333-3333-4333-8333-333333333333"


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_three_users_are_isolated_and_fourth_is_rejected(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(tmp_path, max_sessions=3, timeout_seconds=600, clock=clock)
    app = create_app(session_registry=registry)
    clients = [TestClient(app) for _ in range(4)]

    admitted = [client.get("/api/session") for client in clients[:3]]
    assert [response.status_code for response in admitted] == [200, 200, 200]
    assert [response.json()["session_label"] for response in admitted] == [
        "用户 1", "用户 2", "用户 3",
    ]
    assert admitted[-1].json()["active_users"] == 3

    project = clients[0].post(
        "/api/projects",
        json={"name": "仅用户一可见", "description": "隔离检查"},
    )
    assert project.status_code == 201
    assert len(clients[0].get("/api/projects").json()) == 1
    assert clients[1].get("/api/projects").json() == []
    assert clients[2].get("/api/projects").json() == []

    rejected = clients[3].get("/api/session")
    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "session_capacity_reached"
    assert rejected.json()["error"]["details"]["active_users"] == 3


def test_idle_session_expires_without_passive_status_poll_touching_it(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(tmp_path, max_sessions=3, timeout_seconds=600, clock=clock)
    app = create_app(session_registry=registry)
    first, second, third, waiting = [TestClient(app) for _ in range(4)]

    first.get("/api/session")
    second.get("/api/session")
    third.get("/api/session")
    clock.advance(300)
    second.get("/api/projects")
    third.get("/api/projects")
    clock.advance(301)

    expired_status = first.get("/api/session/status")
    assert expired_status.status_code == 200
    assert expired_status.json()["active"] is False
    assert expired_status.json()["expired"] is True
    assert expired_status.json()["active_users"] == 2

    replacement = waiting.get("/api/session")
    assert replacement.status_code == 200
    assert replacement.json()["active_users"] == 3
    assert replacement.json()["session_label"] == "用户 1"

    kicked_request = first.get("/api/projects")
    assert kicked_request.status_code == 440
    assert kicked_request.json()["error"]["code"] == "session_expired"


def test_two_minute_heartbeat_does_not_extend_ten_minute_activity_timeout(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(
        tmp_path,
        max_sessions=3,
        timeout_seconds=600,
        presence_timeout_seconds=300,
        clock=clock,
    )
    registry.acquire(SESSION_ID, FIRST_PAGE_ID)

    for _ in range(4):
        clock.advance(120)
        assert registry.heartbeat(SESSION_ID, FIRST_PAGE_ID)["active"] is True

    clock.advance(120)
    expired = registry.heartbeat(SESSION_ID, FIRST_PAGE_ID)
    assert expired["active"] is False
    assert expired["expired"] is True
    assert expired["active_users"] == 0


def test_releasing_last_page_frees_slot_but_one_of_two_pages_does_not(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(
        tmp_path,
        timeout_seconds=600,
        presence_timeout_seconds=300,
        clock=clock,
    )
    registry.acquire(SESSION_ID, FIRST_PAGE_ID)
    registry.acquire(SESSION_ID, SECOND_PAGE_ID)

    one_left = registry.release(SESSION_ID, FIRST_PAGE_ID)
    assert one_left["active"] is True
    assert one_left["active_users"] == 1
    assert one_left["connected_pages"] == 1

    released = registry.release(SESSION_ID, SECOND_PAGE_ID)
    assert released["active"] is False
    assert released["expired"] is False
    assert released["active_users"] == 0
    assert registry.acquire(SESSION_ID, FIRST_PAGE_ID).session_id == SESSION_ID


def test_missing_two_minute_heartbeats_releases_disconnected_browser(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(
        tmp_path,
        timeout_seconds=600,
        presence_timeout_seconds=300,
        clock=clock,
    )
    registry.acquire(SESSION_ID, FIRST_PAGE_ID)
    clock.advance(301)

    status = registry.status(SESSION_ID)
    assert status["active"] is False
    assert status["expired"] is False
    assert status["active_users"] == 0


def test_real_activity_extends_idle_timeout_while_heartbeat_alone_does_not(tmp_path):
    clock = FakeClock()
    registry = SessionRegistry(
        tmp_path,
        timeout_seconds=600,
        presence_timeout_seconds=300,
        clock=clock,
    )
    registry.acquire(SESSION_ID, FIRST_PAGE_ID)
    for _ in range(3):
        clock.advance(120)
        registry.heartbeat(SESSION_ID, FIRST_PAGE_ID)
    clock.advance(120)
    active = registry.record_activity(SESSION_ID, FIRST_PAGE_ID)
    assert active["expires_in_seconds"] == 600
    for _ in range(4):
        clock.advance(120)
        assert registry.heartbeat(SESSION_ID, FIRST_PAGE_ID)["active"] is True
    clock.advance(120)
    assert registry.heartbeat(SESSION_ID, FIRST_PAGE_ID)["expired"] is True


def test_heartbeat_and_release_http_endpoints_track_individual_pages(tmp_path):
    registry = SessionRegistry(tmp_path, timeout_seconds=600, presence_timeout_seconds=300)
    app = create_app(session_registry=registry)
    client = TestClient(app)
    headers = {
        "X-DataWork-Session": SESSION_ID,
        "X-DataWork-Client": FIRST_PAGE_ID,
    }

    admitted = client.get("/api/session", headers=headers)
    assert admitted.status_code == 200
    assert admitted.json()["connected_pages"] == 1
    heartbeat = client.post("/api/session/heartbeat", headers=headers)
    assert heartbeat.status_code == 200
    assert heartbeat.json()["active"] is True
    activity = client.post("/api/session/activity", headers=headers)
    assert activity.status_code == 200
    assert activity.json()["active"] is True

    released = client.post(
        "/api/session/release",
        json={"session_id": SESSION_ID, "client_id": FIRST_PAGE_ID},
    )
    assert released.status_code == 200
    assert released.json()["active"] is False
    assert released.json()["active_users"] == 0
