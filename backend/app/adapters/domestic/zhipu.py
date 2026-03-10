"""Zhipu AI (智谱/ChatGLM) adapter implementation."""

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx
import structlog

from app.adapters.base import (
    BaseAdapter,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Embedding,
    EmbeddingRequest,
    EmbeddingResponse,
    MessageRole,
    StreamChunk,
    Usage,
)
from app.adapters.registry import AdapterRegistry, register_adapter
from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()

# Zhipu models
ZHIPU_MODELS = [
    "glm-4-plus",
    "glm-4-0520",
    "glm-4",
    "glm-4-air",
    "glm-4-airx",
    "glm-4-flash",
    "glm-4-long",
    "glm-4v",
    "glm-3-turbo",
    "embedding-2",
    "embedding-3",
]


@register_adapter(Provider.ZHIPU)
class ZhipuAdapter(BaseAdapter):
    """Zhipu AI (智谱清言/ChatGLM) adapter."""

    provider = "zhipu"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)

        self.base_url = api_base or "https://open.bigmodel.cn/api/paas/v4"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion using Zhipu."""
        start_time = time.time()

        try:
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
            }

            if request.max_tokens:
                body["max_tokens"] = request.max_tokens
            if request.stop:
                body["stop"] = request.stop
            if request.tools:
                body["tools"] = [
                    {"type": "function", "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }}
                    for t in request.tools
                ]

            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=body,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                raise AdapterRateLimitError(provider=self.provider)

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("zhipu_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("zhipu_error", model=request.model, error=str(e))
            raise AdapterError(f"Zhipu API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        try:
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
            }

            if request.max_tokens:
                body["max_tokens"] = request.max_tokens

            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "":
                        continue

                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            try:
                                chunk = json.loads(data)
                                yield self._parse_stream_chunk(chunk, request_id, request.model)
                            except json.JSONDecodeError:
                                continue

            yield StreamChunk(
                id=request_id,
                model=request.model,
                delta={},
                finish_reason="stop",
                provider=self.provider,
            )

        except Exception as e:
            logger.error("zhipu_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Zhipu streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            texts = request.input if isinstance(request.input, list) else [request.input]

            response = await self._client.post(
                f"{self.base_url}/embeddings",
                json={
                    "model": request.model,
                    "input": texts,
                },
            )

            response.raise_for_status()
            result = response.json()

            embeddings = [
                Embedding(index=e["index"], embedding=e["embedding"])
                for e in result.get("data", [])
            ]

            usage = result.get("usage", {})

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=request.model,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=0,
                    total_tokens=usage.get("total_tokens", 0),
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("zhipu_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Zhipu embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        return ZHIPU_MODELS

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model.startswith("glm-") or model.startswith("embedding-")

    def _parse_response(
        self, result: dict[str, Any], model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse Zhipu response (OpenAI-compatible)."""
        choices = []
        for idx, choice in enumerate(result.get("choices", [])):
            msg = choice.get("message", {})
            message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls"),
            )
            choices.append(ChatCompletionChoice(
                index=idx,
                message=message,
                finish_reason=choice.get("finish_reason", "stop"),
            ))

        usage = result.get("usage", {})

        return ChatCompletionResponse(
            id=result.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            model=model,
            choices=choices,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            created=result.get("created", int(time.time())),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_stream_chunk(
        self, chunk: dict[str, Any], request_id: str, model: str
    ) -> StreamChunk:
        """Parse streaming chunk."""
        choices = chunk.get("choices", [])
        delta = {}
        finish_reason = None

        if choices:
            choice = choices[0]
            d = choice.get("delta", {})
            if d.get("content"):
                delta["content"] = d["content"]
            if d.get("role"):
                delta["role"] = d["role"]
            finish_reason = choice.get("finish_reason")

        return StreamChunk(
            id=chunk.get("id", request_id),
            model=chunk.get("model", model),
            delta=delta,
            finish_reason=finish_reason,
            provider=self.provider,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Register model prefixes
AdapterRegistry.register_model_prefix("glm-", Provider.ZHIPU)
