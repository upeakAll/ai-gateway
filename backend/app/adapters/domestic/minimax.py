"""MiniMax adapter implementation."""

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

# MiniMax models
MINIMAX_MODELS = [
    "abab6.5s-chat",
    "abab6.5g-chat",
    "abab6.5t-chat",
    "abab5.5-chat",
    "abab5.5s-chat",
    "embo-01",
]


@register_adapter(Provider.MINIMAX)
class MiniMaxAdapter(BaseAdapter):
    """MiniMax adapter."""

    provider = "minimax"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)

        # api_key format: "group_id:api_key"
        if ":" not in api_key:
            raise AdapterError(
                "MiniMax API key must be in format 'group_id:api_key'",
                provider=self.provider,
            )

        self.group_id, self.api_key = api_key.split(":", 1)
        self.base_url = api_base or "https://api.minimax.chat/v1"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion using MiniMax."""
        start_time = time.time()

        try:
            # Convert messages
            messages = []
            system_prompt = None

            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if msg.role == MessageRole.SYSTEM:
                    system_prompt = content
                else:
                    messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
            }

            if system_prompt:
                body["bot_setting"] = [{"bot_name": "AI助手", "content": system_prompt}]

            if request.max_tokens:
                body["max_tokens"] = request.max_tokens
            if request.stop:
                body["stop"] = request.stop

            response = await self._client.post(
                f"{self.base_url}/text/chatcompletion_v2",
                json=body,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                raise AdapterRateLimitError(provider=self.provider)

            response.raise_for_status()
            result = response.json()

            if result.get("base_resp", {}).get("status_code") != 0:
                raise AdapterError(
                    f"MiniMax API error: {result.get('base_resp', {}).get('status_msg')}",
                    provider=self.provider,
                )

            return self._parse_response(result, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("minimax_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("minimax_error", model=request.model, error=str(e))
            raise AdapterError(f"MiniMax API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        try:
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if msg.role != MessageRole.SYSTEM:
                    messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
            }

            async with self._client.stream(
                "POST",
                f"{self.base_url}/text/chatcompletion_v2",
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
            logger.error("minimax_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"MiniMax streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            texts = request.input if isinstance(request.input, list) else [request.input]

            response = await self._client.post(
                f"{self.base_url}/embeddings",
                json={
                    "model": request.model or "embo-01",
                    "texts": texts,
                    "type": "query" if len(texts) == 1 else "document",
                },
            )

            response.raise_for_status()
            result = response.json()

            embeddings = [
                Embedding(index=idx, embedding=vec)
                for idx, vec in enumerate(result.get("vectors", []))
            ]

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=request.model,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=result.get("total_tokens", 0),
                    completion_tokens=0,
                    total_tokens=result.get("total_tokens", 0),
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("minimax_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"MiniMax embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        return MINIMAX_MODELS

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model.startswith("abab") or model.startswith("embo-")

    def _parse_response(
        self, result: dict[str, Any], model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse MiniMax response."""
        choices_data = result.get("choices", [])

        choices = []
        for idx, choice in enumerate(choices_data):
            msg = choice.get("message", {})
            message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=msg.get("content", ""),
            )
            choices.append(ChatCompletionChoice(
                index=idx,
                message=message,
                finish_reason=choice.get("finish_reason", "stop"),
            ))

        usage = result.get("usage", {})

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            model=model,
            choices=choices,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            created=int(time.time()),
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
            finish_reason = choice.get("finish_reason")

        return StreamChunk(
            id=request_id,
            model=model,
            delta=delta,
            finish_reason=finish_reason,
            provider=self.provider,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Register model prefixes
AdapterRegistry.register_model_prefix("abab", Provider.MINIMAX)
