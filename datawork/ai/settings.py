"""AI 助手配置与跨平台密钥存储。

非敏感设置写入工作区 JSON；API 密钥仅保存在当前进程内存或操作系统密钥库。
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator

from datawork.ai.provider import ProviderConfig, ProviderKind
from datawork.core.errors import DataWorkError, ErrorCode
from datawork.infrastructure.paths import WorkspacePaths


LOGGER = logging.getLogger(__name__)


class SecretStorage(str, Enum):
    SESSION = "session"
    KEYRING = "keyring"


class PrivacyMode(str, Enum):
    METADATA_ONLY = "metadata_only"
    INCLUDE_PREVIEW = "include_preview"


class AISettings(BaseModel):
    enabled: bool = False
    provider: ProviderKind = ProviderKind.DEEPSEEK
    base_url: str = "https://api.deepseek.com"
    model: str = ""
    privacy_mode: PrivacyMode = PrivacyMode.METADATA_ONLY
    remember_key: bool = False
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=256, le=16384)
    allow_no_api_key: bool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("API 地址必须以 http:// 或 https:// 开头")
        return value

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str) -> str:
        return value.strip().removeprefix("models/")


PROVIDER_PRESETS: dict[ProviderKind, dict[str, Any]] = {
    ProviderKind.DEEPSEEK: {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "",
        "requires_key": True,
        "supports_discovery": True,
        "help": "测试连接后从 /models 自动读取当前密钥可用的 Model ID。",
    },
    ProviderKind.OPENAI: {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "",
        "requires_key": True,
        "supports_discovery": True,
        "help": "测试连接后通过 Models API 拉取当前项目可见的 Model ID。",
    },
    ProviderKind.GEMINI: {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "",
        "requires_key": True,
        "supports_discovery": True,
        "help": "测试连接后读取模型能力、上下文限制和支持的生成方法。",
    },
    ProviderKind.OLLAMA: {
        "label": "Ollama（本地模型）",
        "base_url": "http://127.0.0.1:11434/api",
        "model": "",
        "requires_key": False,
        "supports_discovery": True,
        "help": "从本机 /api/tags 读取已经安装的模型、参数规模和量化信息。",
    },
    ProviderKind.OPENAI_COMPATIBLE: {
        "label": "OpenAI 兼容接口",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "",
        "requires_key": False,
        "supports_discovery": True,
        "help": "尝试从兼容的 /models 接口读取 Model ID；若服务未实现该接口会明确提示。",
    },
}


_SESSION_SECRETS: dict[str, str] = {}


class AISettingsService:
    """管理 AI 设置、密钥和 ProviderConfig。"""

    def __init__(self, paths: WorkspacePaths) -> None:
        self.paths = paths
        self.config_path = paths.root / "ai_settings.json"
        workspace_key = hashlib.sha256(str(paths.root).encode("utf-8")).hexdigest()[:16]
        self.service_name = "DataWork AI"
        self.account_prefix = f"workspace:{workspace_key}"

    def load(self) -> AISettings:
        if not self.config_path.exists():
            return AISettings()
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            payload.pop("api_key", None)
            return AISettings.model_validate(payload)
        except Exception:
            return AISettings()

    def save(
        self,
        settings: AISettings,
        *,
        api_key: str | None = None,
        secret_storage: SecretStorage = SecretStorage.SESSION,
    ) -> dict[str, Any]:
        warning = ""
        actual_storage = secret_storage
        if api_key is not None and api_key.strip():
            if secret_storage == SecretStorage.KEYRING:
                if not self.keyring_available():
                    actual_storage = SecretStorage.SESSION
                    warning = "系统密钥库不可用，API 密钥仅保留到本次程序关闭。"
                else:
                    self._set_keyring_secret(settings.provider, api_key.strip())
            _SESSION_SECRETS[self._account(settings.provider)] = api_key.strip()
        settings.remember_key = actual_storage == SecretStorage.KEYRING
        self._write_non_secret(settings)
        return {
            "settings": self.public_status(settings),
            "warning": warning,
            "secret_storage": actual_storage.value,
        }

    def _write_non_secret(self, settings: AISettings) -> None:
        payload = settings.model_dump(mode="json")
        payload["schema_version"] = 2
        temporary = self.config_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.config_path)

    def clear_key(self, provider: ProviderKind | None = None) -> None:
        provider = provider or self.load().provider
        _SESSION_SECRETS.pop(self._account(provider), None)
        if self.keyring_available():
            try:
                import keyring

                keyring.delete_password(self.service_name, self._account(provider))
            except Exception as exc:
                # 清除本地配置仍应继续，但密钥库失败不能静默吞掉，否则用户会
                # 误以为系统密钥已经删除。日志不得包含密钥本身。
                LOGGER.warning("无法从系统密钥库删除 %s 的 AI 凭据：%s", provider.value, exc)
        settings = self.load()
        if settings.provider == provider:
            settings.remember_key = False
            self._write_non_secret(settings)

    def resolve_api_key(self, provider: ProviderKind | None = None) -> str:
        provider = provider or self.load().provider
        account = self._account(provider)
        if _SESSION_SECRETS.get(account):
            return _SESSION_SECRETS[account]
        if self.keyring_available():
            try:
                import keyring

                secret = keyring.get_password(self.service_name, account) or ""
                if secret:
                    _SESSION_SECRETS[account] = secret
                return secret
            except Exception:
                return ""
        return ""

    def provider_config(self, *, require_model: bool = True) -> ProviderConfig:
        settings = self.load()
        api_key = self.resolve_api_key(settings.provider)
        preset = PROVIDER_PRESETS[settings.provider]
        requires_key = bool(preset["requires_key"]) and not settings.allow_no_api_key
        if requires_key and not api_key:
            raise DataWorkError(
                ErrorCode.AI_UNAVAILABLE,
                "尚未配置 API 密钥，请在“AI 设置”中填写后测试连接。",
                status_code=409,
            )
        if require_model and not settings.model:
            raise DataWorkError(
                ErrorCode.AI_UNAVAILABLE,
                "尚未选择 Model ID。请先测试连接，等待模型列表加载后手动选择。",
                status_code=409,
            )
        return ProviderConfig(
            kind=settings.provider,
            api_key=api_key,
            base_url=settings.base_url,
            model=settings.model,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            allow_no_api_key=settings.allow_no_api_key or not preset["requires_key"],
        )

    def public_status(self, settings: AISettings | None = None) -> dict[str, Any]:
        settings = settings or self.load()
        key_present = bool(self.resolve_api_key(settings.provider))
        preset = PROVIDER_PRESETS[settings.provider]
        auth_ready = bool(
            key_present or not preset["requires_key"] or settings.allow_no_api_key
        )
        configured = bool(settings.model and settings.base_url and auth_ready)
        return {
            **settings.model_dump(mode="json"),
            "has_api_key": key_present,
            "requires_api_key": bool(preset["requires_key"])
            and not settings.allow_no_api_key,
            "keyring_available": self.keyring_available(),
            "configured": configured,
            "connection_ready": bool(settings.base_url and auth_ready),
            "selection_required": bool(settings.base_url and auth_ready and not settings.model),
            "api_key_masked": "••••••••" if key_present else "",
        }

    def provider_catalog(self) -> list[dict[str, Any]]:
        return [
            {"kind": kind.value, **details}
            for kind, details in PROVIDER_PRESETS.items()
        ]

    def keyring_available(self) -> bool:
        try:
            import keyring

            backend = keyring.get_keyring()
            priority = getattr(backend, "priority", 0)
            return bool(priority and float(priority) > 0)
        except Exception:
            return False

    def _set_keyring_secret(self, provider: ProviderKind, api_key: str) -> None:
        try:
            import keyring

            keyring.set_password(self.service_name, self._account(provider), api_key)
        except Exception as exc:
            raise DataWorkError(
                ErrorCode.AI_CONFIG_ERROR,
                f"无法写入系统密钥库: {exc}",
                status_code=422,
            ) from exc

    def _account(self, provider: ProviderKind) -> str:
        return f"{self.account_prefix}:{provider.value}"
