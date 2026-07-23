"""AI Provider 抽象层：多厂商 LLM 调用与模型发现统一接口。"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel


class ProviderKind(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass
class ProviderConfig:
    """单个 LLM 服务商的运行配置。"""

    kind: ProviderKind
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout_seconds: int = 120
    max_retries: int = 2
    temperature: float = 0.3
    max_tokens: int = 4096
    allow_no_api_key: bool = False

    @property
    def is_discovery_configured(self) -> bool:
        has_endpoint = bool(self.base_url)
        has_auth = bool(
            self.api_key
            or self.kind == ProviderKind.OLLAMA
            or self.allow_no_api_key
        )
        return has_endpoint and has_auth

    @property
    def is_configured(self) -> bool:
        return self.is_discovery_configured and bool(self.model)


@dataclass
class ModelInfo:
    """模型发现接口返回的跨服务商统一结构。"""

    id: str
    display_name: str = ""
    owned_by: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    parameter_size: str = ""
    quantization_level: str = ""
    size_bytes: int | None = None
    created_at: int | str | None = None
    selectable: bool = True
    source: str = "api"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LLMResponse:
    """LLM 调用的统一返回。"""

    content: str = ""
    parsed: Optional[BaseModel] = None
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    cost_usd: float = 0.0
    error: Optional[str] = None


class ProviderRequestError(RuntimeError):
    """服务商 HTTP 请求失败。"""


class LLMProvider:
    """LLM Provider 基类。"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        try:
            await self.list_models()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """生成 JSON 并用 Pydantic 模型校验。"""

        msgs = self._inject_json_schema(messages, schema)
        response_format = (
            {"type": "json_object"}
            if self.config.kind
            in {
                ProviderKind.OPENAI,
                ProviderKind.DEEPSEEK,
                ProviderKind.OPENAI_COMPATIBLE,
            }
            else None
        )
        response = await self.generate_text(
            msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        if response.content:
            try:
                extracted = self._extract_json(response.content)
                response.parsed = schema.model_validate(extracted)
            except (json.JSONDecodeError, ValueError) as exc:
                response.error = f"JSON parsing failed: {exc}"
        return response

    @staticmethod
    def _inject_json_schema(
        messages: list[dict[str, str]], schema: type[BaseModel]
    ) -> list[dict[str, str]]:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        instruction = (
            "\n\n必须只返回满足以下 JSON Schema 的 JSON 对象，"
            "不要输出 Markdown 代码围栏或额外解释：\n"
            f"{schema_json}"
        )
        msgs = [dict(message) for message in messages]
        for message in msgs:
            if message["role"] == "system":
                message["content"] += instruction
                return msgs
        msgs.insert(0, {"role": "system", "content": instruction.strip()})
        return msgs

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as original_error:
            # Some compatible endpoints prepend a short sentence even when JSON
            # mode is requested. Accept the first complete JSON object, while
            # leaving schema validation to the caller.
            decoder = json.JSONDecoder()
            for index, character in enumerate(content):
                if character != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(content[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return value
            raise original_error

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        """兼容 OpenAI 风格接口常见的字符串与内容分段返回。"""

        raw = message.get("content")
        if isinstance(raw, str):
            text = raw.strip()
            if text:
                return text
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    value = item.get("text") or item.get("output_text") or item.get("content")
                    if isinstance(value, str):
                        parts.append(value)
            text = "".join(parts).strip()
            if text:
                return text
        for key in ("output_text", "text"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        # 部分推理模型偶尔把最终 JSON 放在 reasoning_content，而 content 为空。
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str):
            candidate = reasoning.strip()
            unwrapped = candidate.removeprefix("```json").removeprefix("```").strip()
            if unwrapped.startswith("{"):
                return candidate
        return ""

    @staticmethod
    def _estimate_cost(
        kind: ProviderKind,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> float:
        """仅提供粗略估算；实际计费以服务商账单为准。"""

        pricing = {
            ProviderKind.OPENAI: (2.5, 10.0),
            ProviderKind.DEEPSEEK: (0.27, 1.10),
            ProviderKind.GEMINI: (0.15, 0.60),
            ProviderKind.OLLAMA: (0, 0),
            ProviderKind.OPENAI_COMPATIBLE: (0, 0),
        }
        input_price, output_price = pricing.get(kind, (0, 0))
        return (
            prompt_tokens * input_price + completion_tokens * output_price
        ) / 1_000_000


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _http_error(response: httpx.Response, action: str) -> ProviderRequestError:
    detail = response.text.strip().replace("\n", " ")[:500]
    return ProviderRequestError(
        f"{action}失败：HTTP {response.status_code}"
        + (f"，{detail}" if detail else "")
    )


class OpenAIProvider(LLMProvider):
    async def list_models(self) -> list[ModelInfo]:
        client = await self._get_client()
        response = await client.get(
            f"{self.config.base_url.rstrip('/')}/models",
            headers=_auth_headers(self.config.api_key),
        )
        if response.status_code != 200:
            raise _http_error(response, "模型列表读取")
        payload = response.json()
        models: list[ModelInfo] = []
        for item in payload.get("data", []):
            model_id = str(item.get("id", "")).strip()
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    display_name=str(item.get("display_name") or model_id),
                    owned_by=str(item.get("owned_by", "")),
                    created_at=item.get("created"),
                    capabilities=_openai_model_capabilities(item),
                    source="models_endpoint",
                )
            )
        return sorted(models, key=lambda item: item.id.lower())

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> LLMResponse:
        if not self.config.model:
            return LLMResponse(error="尚未选择 Model ID。")
        client = await self._get_client()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self.config.temperature
            ),
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        **_auth_headers(self.config.api_key),
                        "Content-Type": "application/json",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    choice = data["choices"][0]
                    message = choice.get("message") or {}
                    content = self._message_text(message)
                    usage = data.get("usage", {})
                    return LLMResponse(
                        content=content,
                        usage={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                        },
                        model=data.get("model", self.config.model),
                        cost_usd=self._estimate_cost(
                            self.config.kind,
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            self.config.model,
                        ),
                        error=(
                            None
                            if content
                            else "AI 响应未包含可读取正文"
                            + (
                                f"（finish_reason={choice.get('finish_reason')}）"
                                if choice.get("finish_reason")
                                else ""
                            )
                        ),
                    )
                if response.status_code == 429 and attempt < self.config.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                return LLMResponse(error=str(_http_error(response, "AI 请求")))
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    continue
                return LLMResponse(error="AI 请求超时。")
            except Exception as exc:
                return LLMResponse(error=str(exc))
        return LLMResponse(error="已达到最大重试次数。")


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek 使用 OpenAI 兼容的模型列表和 Chat Completions 接口。"""


class GeminiProvider(LLMProvider):
    async def list_models(self) -> list[ModelInfo]:
        client = await self._get_client()
        url = f"{self.config.base_url.rstrip('/')}/models"
        page_token = ""
        models: list[ModelInfo] = []
        while True:
            params: dict[str, Any] = {
                "key": self.config.api_key,
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(url, params=params)
            if response.status_code != 200:
                raise _http_error(response, "模型列表读取")
            payload = response.json()
            for item in payload.get("models", []):
                raw_name = str(item.get("name", ""))
                model_id = str(item.get("baseModelId") or raw_name.removeprefix("models/"))
                if not model_id:
                    continue
                capabilities = list(
                    item.get("supportedGenerationMethods")
                    or item.get("supportedActions")
                    or []
                )
                if item.get("thinking") is True and "thinking" not in capabilities:
                    capabilities.append("thinking")
                selectable = any(
                    action in {"generateContent", "generateMessage", "generateText"}
                    for action in capabilities
                )
                models.append(
                    ModelInfo(
                        id=model_id,
                        display_name=str(item.get("displayName") or model_id),
                        description=str(item.get("description", "")),
                        capabilities=capabilities,
                        input_token_limit=_optional_int(item.get("inputTokenLimit")),
                        output_token_limit=_optional_int(item.get("outputTokenLimit")),
                        selectable=selectable,
                        source="models.list",
                    )
                )
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                break
        return sorted(models, key=lambda item: item.id.lower())

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> LLMResponse:
        if not self.config.model:
            return LLMResponse(error="尚未选择 Model ID。")
        client = await self._get_client()
        model_id = self.config.model.removeprefix("models/")
        url = f"{self.config.base_url.rstrip('/')}/models/{model_id}:generateContent"
        payload = {
            "contents": self._to_gemini_messages(messages),
            "generationConfig": {
                "temperature": (
                    temperature if temperature is not None else self.config.temperature
                ),
                "maxOutputTokens": max_tokens or self.config.max_tokens,
            },
        }
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    params={"key": self.config.api_key},
                )
                if response.status_code == 200:
                    data = response.json()
                    text = ""
                    for candidate in data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            text += part.get("text", "")
                    usage = data.get("usageMetadata", {})
                    return LLMResponse(
                        content=text,
                        usage={
                            "prompt_tokens": usage.get("promptTokenCount", 0),
                            "completion_tokens": usage.get("candidatesTokenCount", 0),
                        },
                        model=model_id,
                        cost_usd=self._estimate_cost(
                            self.config.kind,
                            usage.get("promptTokenCount", 0),
                            usage.get("candidatesTokenCount", 0),
                            model_id,
                        ),
                    )
                if response.status_code == 429 and attempt < self.config.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                return LLMResponse(error=str(_http_error(response, "AI 请求")))
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    continue
                return LLMResponse(error="AI 请求超时。")
            except Exception as exc:
                return LLMResponse(error=str(exc))
        return LLMResponse(error="已达到最大重试次数。")

    @staticmethod
    def _to_gemini_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "user" if message["role"] in {"user", "system"} else "model"
            contents.append(
                {"role": role, "parts": [{"text": message["content"]}]}
            )
        return contents


class OllamaProvider(LLMProvider):
    async def list_models(self) -> list[ModelInfo]:
        client = await self._get_client()
        response = await client.get(f"{self.config.base_url.rstrip('/')}/tags")
        if response.status_code != 200:
            raise _http_error(response, "模型列表读取")
        payload = response.json()
        models: list[ModelInfo] = []
        for item in payload.get("models", []):
            model_id = str(item.get("model") or item.get("name") or "").strip()
            if not model_id:
                continue
            details = item.get("details") or {}
            capabilities = [str(value) for value in details.get("families", [])]
            family = str(details.get("family", ""))
            if family and family not in capabilities:
                capabilities.insert(0, family)
            models.append(
                ModelInfo(
                    id=model_id,
                    display_name=str(item.get("name") or model_id),
                    capabilities=capabilities,
                    parameter_size=str(details.get("parameter_size", "")),
                    quantization_level=str(details.get("quantization_level", "")),
                    size_bytes=_optional_int(item.get("size")),
                    created_at=item.get("modified_at"),
                    source="api/tags",
                )
            )
        return sorted(models, key=lambda item: item.id.lower())

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> LLMResponse:
        if not self.config.model:
            return LLMResponse(error="尚未选择 Model ID。")
        client = await self._get_client()
        url = f"{self.config.base_url.rstrip('/')}/chat"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": (
                    temperature if temperature is not None else self.config.temperature
                ),
                "num_predict": max_tokens or self.config.max_tokens,
            },
        }
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                return LLMResponse(
                    content=data.get("message", {}).get("content", ""),
                    usage={
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                    },
                    model=data.get("model", self.config.model),
                    cost_usd=0,
                )
            return LLMResponse(error=str(_http_error(response, "AI 请求")))
        except Exception as exc:
            return LLMResponse(error=str(exc))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _openai_model_capabilities(item: dict[str, Any]) -> list[str]:
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict):
        return sorted(str(key) for key, enabled in capabilities.items() if enabled)
    if isinstance(capabilities, list):
        return [str(value) for value in capabilities]
    return []


_PROVIDER_REGISTRY = {
    ProviderKind.OPENAI: OpenAIProvider,
    ProviderKind.DEEPSEEK: DeepSeekProvider,
    ProviderKind.GEMINI: GeminiProvider,
    ProviderKind.OLLAMA: OllamaProvider,
    ProviderKind.OPENAI_COMPATIBLE: OpenAIProvider,
}

DEFAULT_PROVIDERS = {
    ProviderKind.DEEPSEEK: ProviderConfig(
        kind=ProviderKind.DEEPSEEK,
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url="https://api.deepseek.com",
        model=os.getenv("DEEPSEEK_MODEL", ""),
    ),
    ProviderKind.OPENAI: ProviderConfig(
        kind=ProviderKind.OPENAI,
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url="https://api.openai.com/v1",
        model=os.getenv("OPENAI_MODEL", ""),
    ),
    ProviderKind.GEMINI: ProviderConfig(
        kind=ProviderKind.GEMINI,
        api_key=os.getenv("GEMINI_API_KEY", ""),
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model=os.getenv("GEMINI_MODEL", ""),
    ),
    ProviderKind.OLLAMA: ProviderConfig(
        kind=ProviderKind.OLLAMA,
        base_url="http://localhost:11434/api",
        model=os.getenv("OLLAMA_MODEL", ""),
    ),
}


def create_provider(
    kind: Optional[ProviderKind] = None,
    config: Optional[ProviderConfig] = None,
) -> Optional[LLMProvider]:
    """创建 Provider；显式配置允许在尚未选择模型时执行模型发现。"""

    if config and config.is_discovery_configured:
        provider_class = _PROVIDER_REGISTRY.get(config.kind, OpenAIProvider)
        return provider_class(config)

    if config is None:
        try:
            from datawork.ai.settings import AISettingsService
            from datawork.infrastructure.paths import resolve_workspace_paths

            settings_service = AISettingsService(resolve_workspace_paths())
            if settings_service.config_path.exists():
                settings = settings_service.load()
                if not settings.enabled:
                    return None
                configured = settings_service.provider_config()
                provider_class = _PROVIDER_REGISTRY.get(
                    configured.kind, OpenAIProvider
                )
                return provider_class(configured)
        except Exception:
            if (
                "settings_service" in locals()
                and settings_service.config_path.exists()
            ):
                return None

    priority = [
        ProviderKind.DEEPSEEK,
        ProviderKind.OPENAI,
        ProviderKind.GEMINI,
    ]
    if kind:
        priority = [kind] + [item for item in priority if item != kind]
    for provider_kind in priority:
        provider_config = DEFAULT_PROVIDERS[provider_kind]
        if provider_config.is_configured:
            provider_class = _PROVIDER_REGISTRY.get(
                provider_kind, OpenAIProvider
            )
            return provider_class(provider_config)
    return None


def is_ai_available() -> bool:
    return create_provider() is not None
