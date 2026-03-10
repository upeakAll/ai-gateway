"""Aliyun (Alibaba Cloud/通义千问) adapter implementation."""

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

# Aliyun Qwen models
ALIYUN_MODELS = [
    "qwen-turbo",
    "qwen-turbo-latest",
    "qwen-plus",
    "qwen-plus-latest",
    "qwen-max",
    "qwen-max-latest",
    "qwen-max-longcontext",
    "qwen-long",
    "qwen-vl-max",
    "qwen-vl-plus",
    "qwen-audio-turbo",
    "text-embedding-v1",
    "text-embedding-v2",
    "text-embedding-v3",
]


@register_adapter(Provider.ALIYUN)
class AliyunAdapter(BaseAdapter):
    """Aliyun Tongyi Qianwen (通义千问) adapter.

    Supports Qwen series models via DashScope API.
    """

    provider = "aliyun"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)

        self.base_url = api_base or "https://dashscope.aliyuncs.com/api/v1"
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
        """Execute chat completion using Aliyun Qwen."""
        start_time = time.time()

        try:
            # Convert messages
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if msg.role == MessageRole.SYSTEM:
                    messages.append({"role": "system", "content": content})
                elif msg.role == MessageRole.USER:
                    messages.append({"role": "user", "content": content})
                elif msg.role == MessageRole.ASSISTANT:
                    messages.append({"role": "assistant", "content": content})

            body = {
                "model": request.model,
                "input": {
                    "messages": messages,
                },
                "parameters": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "max_tokens": request.max_tokens or 2000,
                    "result_format": "message",
                },
            }

            if request.stop:
                body["parameters"]["stop"] = request.stop

            response = await self._client.post(
                f"{self.base_url}/services/aigc/text-generation/generation",
                json=body,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                raise AdapterRateLimitError(provider=self.provider)

            response.raise_for_status()
            result = response.json()

            return self._parse_response(result, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("aliyun_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except httpx.HTTPStatusError as e:
            logger.error("aliyun_http_error", status=e.response.status_code)
            raise AdapterError(
                f"Aliyun API error: {e.response.status_code}",
                provider=self.provider,
            ) from e

        except Exception as e:
            logger.error("aliyun_error", model=request.model, error=str(e))
            raise AdapterError(f"Aliyun API error: {str(e)}", provider=self.provider) from e

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
                "input": {
                    "messages": messages,
                },
                "parameters": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "max_tokens": request.max_tokens or 2000,
                    "result_format": "message",
                    "incremental_output": True,
                },
            }

            async with self._client.stream(
                "POST",
                f"{self.base_url}/services/aigc/text-generation/generation",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "enable",
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "":
                        continue

                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                chunk = json.loads(data)
                                yield self._parse_stream_chunk(chunk, request_id, request.model)
                            except json.JSONDecodeError:
                                continue

            # Final chunk
            yield StreamChunk(
                id=request_id,
                model=request.model,
                delta={},
                finish_reason="stop",
                provider=self.provider,
            )

        except Exception as e:
            logger.error("aliyun_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Aliyun streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            texts = request.input if isinstance(request.input, list) else [request.input]

            embeddings = []
            total_tokens = 0

            for idx, text in enumerate(texts):
                response = await self._client.post(
                    f"{self.base_url}/services/embeddings/text-embedding/text-embedding",
                    json={
                        "model": request.model,
                        "input": {"texts": [text]},
                        "parameters": {"text_type": "query"},
                    },
                )

                response.raise_for_status()
                result = response.json()

                output = result.get("output", {})
                embeddings_list = output.get("embeddings", [])

                if embeddings_list:
                    embeddings.append(Embedding(
                        index=idx,
                        embedding=embeddings_list[0].get("embedding", []),
                    ))
                    total_tokens += output.get("usage", {}).get("total_tokens", 0)

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=request.model,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=total_tokens,
                    completion_tokens=0,
                    total_tokens=total_tokens,
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("aliyun_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Aliyun embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        return ALIYUN_MODELS

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model.startswith("qwen-") or model.startswith("text-embedding-")

    def _parse_response(
        self, result: dict[str, Any], model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse Aliyun response."""
        output = result.get("output", {})
        choices_data = output.get("choices", [])

        choices = []
        for idx, choice in enumerate(choices_data):
            message_data = choice.get("message", {})
            message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=message_data.get("content", ""),
            )
            choices.append(ChatCompletionChoice(
                index=idx,
                message=message,
                finish_reason=choice.get("finish_reason", "stop"),
            ))

        usage_data = result.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            model=model,
            choices=choices if choices else [ChatCompletionChoice(
                index=0,
                message=ChatMessage(role=MessageRole.ASSISTANT, content=output.get("text", "")),
                finish_reason="stop",
            )],
            usage=usage,
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_stream_chunk(
        self, chunk: dict[str, Any], request_id: str, model: str
    ) -> StreamChunk:
        """Parse streaming chunk."""
        output = chunk.get("output", {})
        choices = output.get("choices", [])

        delta = {}
        finish_reason = None

        if choices:
            choice = choices[0]
            message = choice.get("message", {})
            if message.get("content"):
                delta["content"] = message["content"]
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
AdapterRegistry.register_model_prefix("qwen-", Provider.ALIYUN)
AdapterRegistry.register_model_prefix("text-embedding-", Provider.ALIYUN)
