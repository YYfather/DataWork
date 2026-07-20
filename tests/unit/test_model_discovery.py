import asyncio
import json

import httpx
from pydantic import BaseModel

from datawork.ai.provider import (
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderConfig,
    ProviderKind,
)


def test_openai_model_discovery_normalizes_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "gpt-test-b", "owned_by": "openai", "created": 2},
                    {"id": "gpt-test-a", "owned_by": "openai", "created": 1},
                ],
            },
        )

    provider = OpenAIProvider(
        ProviderConfig(
            kind=ProviderKind.OPENAI,
            api_key="secret",
            base_url="https://example.test/v1",
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async def run():
        try:
            return await provider.list_models()
        finally:
            await provider.close()

    models = asyncio.run(run())
    assert [item.id for item in models] == ["gpt-test-a", "gpt-test-b"]
    assert models[0].owned_by == "openai"


def test_openai_structured_request_uses_json_mode_and_accepts_content_parts():
    class TinyResult(BaseModel):
        status: str

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_tokens"] == 8192
        return httpx.Response(
            200,
            json={
                "model": "structured-test",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": '{"status":"ok"}'}
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    provider = OpenAIProvider(
        ProviderConfig(
            kind=ProviderKind.OPENAI,
            api_key="secret",
            base_url="https://example.test/v1",
            model="structured-test",
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        try:
            return await provider.generate_structured(
                [{"role": "user", "content": "return status"}],
                TinyResult,
                max_tokens=8192,
            )
        finally:
            await provider.close()

    response = asyncio.run(run())
    assert response.error is None
    assert response.parsed == TinyResult(status="ok")


def test_structured_response_accepts_a_preface_before_complete_json_object():
    assert OpenAIProvider._extract_json(
        '以下为所需结构：\n{"status":"ok"}\n请查收。'
    ) == {"status": "ok"}


def test_gemini_model_discovery_exposes_limits_and_selectability():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-test-001",
                        "baseModelId": "gemini-test",
                        "displayName": "Gemini Test",
                        "inputTokenLimit": 1000,
                        "outputTokenLimit": 200,
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding-test",
                        "baseModelId": "embedding-test",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )

    provider = GeminiProvider(
        ProviderConfig(
            kind=ProviderKind.GEMINI,
            api_key="secret",
            base_url="https://example.test/v1beta",
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async def run():
        try:
            return await provider.list_models()
        finally:
            await provider.close()

    models = asyncio.run(run())
    by_id = {item.id: item for item in models}
    assert by_id["gemini-test"].input_token_limit == 1000
    assert by_id["gemini-test"].selectable is True
    assert by_id["embedding-test"].selectable is False


def test_ollama_model_discovery_exposes_local_model_details():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/tags")
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen:test",
                        "model": "qwen:test",
                        "size": 123456,
                        "details": {
                            "family": "qwen",
                            "parameter_size": "7B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            },
        )

    provider = OllamaProvider(
        ProviderConfig(
            kind=ProviderKind.OLLAMA,
            base_url="http://localhost:11434/api",
            allow_no_api_key=True,
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async def run():
        try:
            return await provider.list_models()
        finally:
            await provider.close()

    models = asyncio.run(run())
    assert models[0].id == "qwen:test"
    assert models[0].parameter_size == "7B"
    assert models[0].quantization_level == "Q4_K_M"
