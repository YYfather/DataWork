"""项目工作区的服务器端密码验证。"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspaceAuthConfig:
    algorithm: str
    iterations: int
    salt: bytes
    digest: bytes
    cleanup_expired_sessions: bool = False


class WorkspaceAuthService:
    """读取加盐密码摘要；明文密码只在一次验证调用中存在。"""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.config_path = self.data_root / "workspace_auth.json"
        self.config = self._load_config()

    @property
    def configured(self) -> bool:
        return self.config is not None

    @property
    def cleanup_expired_sessions(self) -> bool:
        return bool(self.config and self.config.cleanup_expired_sessions)

    def _load_config(self) -> WorkspaceAuthConfig | None:
        raw: dict[str, Any] | None = None
        encoded = os.getenv("DATAWORK_WORKSPACE_AUTH_JSON", "").strip()
        if encoded:
            try:
                raw = json.loads(encoded)
            except json.JSONDecodeError as exc:
                raise RuntimeError("DATAWORK_WORKSPACE_AUTH_JSON 不是有效 JSON") from exc
        elif self.config_path.is_file():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("工作区认证配置无法读取") from exc
        if raw is None:
            return None

        try:
            algorithm = str(raw["algorithm"])
            iterations = int(raw["iterations"])
            salt = base64.b64decode(str(raw["salt"]), validate=True)
            digest = base64.b64decode(str(raw["digest"]), validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("工作区认证配置字段无效") from exc
        if algorithm != "pbkdf2_sha256" or iterations < 200_000 or not salt or not digest:
            raise RuntimeError("工作区认证配置不符合安全要求")
        return WorkspaceAuthConfig(
            algorithm=algorithm,
            iterations=iterations,
            salt=salt,
            digest=digest,
            cleanup_expired_sessions=bool(raw.get("cleanup_expired_sessions", False)),
        )

    def verify(self, password: str) -> bool:
        if self.config is None or not password:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            self.config.salt,
            self.config.iterations,
        )
        return hmac.compare_digest(candidate, self.config.digest)

