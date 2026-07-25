"""单进程网页部署的匿名会话、容量限制与工作区隔离。"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Callable, Generic, TypeVar
from uuid import UUID, uuid4

from datawork.application.ai_assistant_service import AIAssistantService
from datawork.application.workspace_service import WorkspaceService
from datawork.ai.settings import AISettingsService
from datawork.infrastructure.paths import default_workspace_root


@dataclass
class SessionResources:
    session_id: str
    label: str
    slot: int
    last_active: float
    workspace: WorkspaceService
    ai_settings: AISettingsService
    ai_assistant: AIAssistantService
    workspace_authenticated: bool = False
    workspace_auth_failures: int = 0
    workspace_auth_locked_until: float = 0.0
    client_activity: dict[str, float] = field(default_factory=dict)
    presence_tracking: bool = False


class SessionCapacityError(RuntimeError):
    pass


class SessionExpiredError(RuntimeError):
    pass


def normalize_session_id(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def normalize_client_id(value: str | None) -> str | None:
    return normalize_session_id(value)


class SessionRegistry:
    """维护最多 N 个活跃会话，并分别跟踪实际操作与浏览器页面在线状态。"""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        max_sessions: int = 3,
        timeout_seconds: int = 10 * 60,
        presence_timeout_seconds: int = 5 * 60,
        ai_guest_question_limit: int = 10,
        clock: Callable[[], float] = time.monotonic,
        quota_clock: Callable[[], float] = time.time,
    ) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions 必须大于 0")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds 必须大于 0")
        if presence_timeout_seconds < 1:
            raise ValueError("presence_timeout_seconds 必须大于 0")
        if ai_guest_question_limit < 0:
            raise ValueError("ai_guest_question_limit 不能小于 0")
        self.root = Path(root).expanduser().resolve() if root else default_workspace_root().resolve()
        self.users_root = self.root / "users"
        self.users_root.mkdir(parents=True, exist_ok=True)
        self.max_sessions = max_sessions
        self.timeout_seconds = timeout_seconds
        self.presence_timeout_seconds = presence_timeout_seconds
        self.ai_guest_question_limit = ai_guest_question_limit
        self._clock = clock
        self._quota_clock = quota_clock
        self._lock = threading.RLock()
        self._active: dict[str, SessionResources] = {}
        self._expired: dict[str, float] = {}
        self._ai_quota_path = self.root / "ai_guest_quota.json"
        self._ai_guest_usage = self._load_ai_guest_usage()
        self.cleanup_expired_data = False

    def _load_ai_guest_usage(self) -> dict[str, tuple[int, float]]:
        if not self._ai_quota_path.is_file():
            return {}
        now = self._quota_clock()
        try:
            payload = json.loads(self._ai_quota_path.read_text(encoding="utf-8"))
            raw_usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
            usage: dict[str, tuple[int, float]] = {}
            for session_id, entry in raw_usage.items():
                normalized = normalize_session_id(session_id)
                if not normalized or not isinstance(entry, dict):
                    continue
                used = int(entry.get("used", 0))
                started = float(entry.get("window_started_at", 0))
                if 0 < used <= self.ai_guest_question_limit and 0 <= now - started < 24 * 60 * 60:
                    usage[normalized] = (used, started)
            return usage
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _write_ai_guest_usage_locked(self) -> None:
        payload = {
            "schema_version": 1,
            "usage": {
                session_id: {"used": used, "window_started_at": started}
                for session_id, (used, started) in self._ai_guest_usage.items()
            },
        }
        temporary = self._ai_quota_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self._ai_quota_path)
        os.chmod(self._ai_quota_path, 0o600)

    def _purge_locked(self, now: float, quota_now: float | None = None) -> None:
        disconnected_ids: list[str] = []
        for session_id, record in self._active.items():
            record.client_activity = {
                client_id: seen_at
                for client_id, seen_at in record.client_activity.items()
                if now - seen_at < self.presence_timeout_seconds
            }
            if record.presence_tracking and not record.client_activity:
                disconnected_ids.append(session_id)

        for session_id in disconnected_ids:
            self._remove_locked(session_id, now, expired=False)

        expired_ids = [
            session_id
            for session_id, record in self._active.items()
            if now - record.last_active >= self.timeout_seconds
        ]
        for session_id in expired_ids:
            self._remove_locked(session_id, now, expired=True)

        remember_for = max(self.timeout_seconds * 2, 3600)
        stale_ids = [
            session_id
            for session_id, expired_at in self._expired.items()
            if now - expired_at >= remember_for
        ]
        for session_id in stale_ids:
            self._expired.pop(session_id, None)

        quota_now = self._quota_clock() if quota_now is None else quota_now
        stale_ai_usage = [
            session_id
            for session_id, (_, window_started_at) in self._ai_guest_usage.items()
            if quota_now - window_started_at >= 24 * 60 * 60
        ]
        for session_id in stale_ai_usage:
            self._ai_guest_usage.pop(session_id, None)
        if stale_ai_usage:
            self._write_ai_guest_usage_locked()

    def _remove_locked(self, session_id: str, now: float, *, expired: bool) -> None:
        record = self._active.pop(session_id, None)
        if record is None:
            return
        if expired:
            self._expired[session_id] = now
        else:
            self._expired.pop(session_id, None)
        if self.cleanup_expired_data:
            shutil.rmtree(record.workspace.paths.root, ignore_errors=True)

    @staticmethod
    def _register_client(record: SessionResources, client_id: str | None, now: float) -> None:
        normalized = normalize_client_id(client_id)
        if normalized:
            record.presence_tracking = True
            record.client_activity[normalized] = now

    def _workspace_root(self, session_id: str) -> Path:
        safe_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return self.users_root / safe_id

    def acquire(self, session_id: str | None, client_id: str | None = None) -> SessionResources:
        normalized = normalize_session_id(session_id) or str(uuid4())
        now = self._clock()
        with self._lock:
            self._purge_locked(now, self._quota_clock())
            if normalized in self._expired:
                raise SessionExpiredError("该会话已因超过 10 分钟未实际操作而退出")
            existing = self._active.get(normalized)
            if existing is not None:
                existing.last_active = now
                self._register_client(existing, client_id, now)
                return existing
            if len(self._active) >= self.max_sessions:
                raise SessionCapacityError(
                    f"当前已有 {self.max_sessions} 位用户正在使用，请稍后再试"
                )

            used_slots = {record.slot for record in self._active.values()}
            slot = next(index for index in range(1, self.max_sessions + 1) if index not in used_slots)
            workspace = WorkspaceService(self._workspace_root(normalized))
            ai_settings = AISettingsService(workspace.paths)
            record = SessionResources(
                session_id=normalized,
                label=f"用户 {slot}",
                slot=slot,
                last_active=now,
                workspace=workspace,
                ai_settings=ai_settings,
                ai_assistant=AIAssistantService(ai_settings),
            )
            self._register_client(record, client_id, now)
            self._active[normalized] = record
            return record

    def heartbeat(self, session_id: str | None, client_id: str | None) -> dict[str, object]:
        normalized = normalize_session_id(session_id)
        now = self._clock()
        quota_now = self._quota_clock()
        with self._lock:
            self._purge_locked(now, quota_now)
            record = self._active.get(normalized or "")
            if record is not None:
                self._register_client(record, client_id, now)
            return self._status_locked(normalized, now, quota_now)

    def record_activity(self, session_id: str | None, client_id: str | None) -> dict[str, object]:
        normalized = normalize_session_id(session_id)
        now = self._clock()
        quota_now = self._quota_clock()
        with self._lock:
            self._purge_locked(now, quota_now)
            record = self._active.get(normalized or "")
            if record is not None:
                record.last_active = now
                self._register_client(record, client_id, now)
            return self._status_locked(normalized, now, quota_now)

    def status(self, session_id: str | None, *, touch: bool = False) -> dict[str, object]:
        normalized = normalize_session_id(session_id)
        now = self._clock()
        quota_now = self._quota_clock()
        with self._lock:
            self._purge_locked(now, quota_now)
            record = self._active.get(normalized or "")
            if record is not None and touch:
                record.last_active = now
            return self._status_locked(normalized, now, quota_now)

    def _status_locked(
        self, normalized: str | None, now: float, quota_now: float
    ) -> dict[str, object]:
        record = self._active.get(normalized or "")
        ai_used, ai_window_started = self._ai_guest_usage.get(
            normalized or "", (0, now)
        )
        return {
            "active": record is not None,
            "expired": bool(normalized and normalized in self._expired),
            "active_users": len(self._active),
            "max_users": self.max_sessions,
            "idle_timeout_seconds": self.timeout_seconds,
            "presence_timeout_seconds": self.presence_timeout_seconds,
            "session_label": record.label if record else None,
            "connected_pages": len(record.client_activity) if record else 0,
            "expires_in_seconds": max(0, int(self.timeout_seconds - (now - record.last_active))) if record else 0,
            "ai_guest_questions_used": ai_used,
            "ai_guest_questions_limit": self.ai_guest_question_limit,
            "ai_guest_questions_remaining": max(0, self.ai_guest_question_limit - ai_used),
            "ai_guest_quota_resets_in_seconds": (
                max(0, int(24 * 60 * 60 - (quota_now - ai_window_started)))
                if ai_used else 0
            ),
        }

    def ai_quota_status(self, session_id: str | None) -> dict[str, int]:
        normalized = normalize_session_id(session_id)
        now = self._clock()
        quota_now = self._quota_clock()
        with self._lock:
            self._purge_locked(now, quota_now)
            used, window_started = self._ai_guest_usage.get(
                normalized or "", (0, quota_now)
            )
            return {
                "used": used,
                "limit": self.ai_guest_question_limit,
                "remaining": max(0, self.ai_guest_question_limit - used),
                "resets_in_seconds": (
                    max(0, int(24 * 60 * 60 - (quota_now - window_started)))
                    if used else 0
                ),
            }

    def consume_ai_guest_question(self, session_id: str) -> dict[str, int] | None:
        normalized = normalize_session_id(session_id)
        if not normalized:
            return None
        now = self._clock()
        quota_now = self._quota_clock()
        with self._lock:
            self._purge_locked(now, quota_now)
            used, window_started = self._ai_guest_usage.get(normalized, (0, quota_now))
            if used >= self.ai_guest_question_limit:
                return None
            self._ai_guest_usage[normalized] = (
                used + 1,
                window_started if used else quota_now,
            )
            self._write_ai_guest_usage_locked()
            return {
                "used": used + 1,
                "limit": self.ai_guest_question_limit,
                "remaining": max(0, self.ai_guest_question_limit - used - 1),
                "resets_in_seconds": 24 * 60 * 60 if not used else max(
                    0, int(24 * 60 * 60 - (quota_now - window_started))
                ),
            }

    def release(self, session_id: str | None, client_id: str | None = None) -> dict[str, object]:
        normalized = normalize_session_id(session_id)
        if not normalized:
            return self.status(None)
        normalized_client = normalize_client_id(client_id)
        with self._lock:
            now = self._clock()
            quota_now = self._quota_clock()
            self._purge_locked(now, quota_now)
            record = self._active.get(normalized)
            if record is not None and normalized_client and record.presence_tracking:
                record.client_activity.pop(normalized_client, None)
                if record.client_activity:
                    return self._status_locked(normalized, now, quota_now)
            self._remove_locked(normalized, now, expired=False)
            return self._status_locked(normalized, now, quota_now)


CURRENT_SESSION: ContextVar[SessionResources | None] = ContextVar(
    "datawork_current_session", default=None,
)


T = TypeVar("T")


class SessionResourceProxy(Generic[T]):
    def __init__(self, getter: Callable[[SessionResources], T]) -> None:
        self._getter = getter

    def current(self) -> T:
        session = CURRENT_SESSION.get()
        if session is None:
            raise RuntimeError("当前请求没有 DataWork 会话上下文")
        return self._getter(session)

    def __getattr__(self, name: str):
        return getattr(self.current(), name)
