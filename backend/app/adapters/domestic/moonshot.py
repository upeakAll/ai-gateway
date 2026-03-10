"""Moonshot (月之暗面/Kimi) adapter implementation."""

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx
import structlog
from openai import AsyncOpenAI

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

# Moonshot models
MOONSHOT_MODELS = [
    "moonshot-v1-8k",
    "moonshot-v1-32k",
    "moonshot-v1-128k",
]


@register_adapter(Provider.MOONSHOT)
class MoonshotAdapter(BaseAdapter):
    """Moonshot (Kimi) adapter (OpenAI-compatible API)."""

    provider = "moonshot"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)

        self.base_url = api_base or "https://api.moonshot.cn/v1"
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
            max_retries=0,
        )

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion using Moonshot."""
        start_time = time.time()

        try:
            messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": False,
            }

            if request.max_tokens:
                request_params["max_tokens"] = request.max_tokens
            if request.stop:
                request_params["stop"] = request.stop
            if request.tools:
                request_params["tools"] = [
                    {"type": "function", "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }}
                    for t in request.tools
                ]

            response = await self.client.chat.completions.create(**request_params)

            latency_ms = (time.time() - start_time) * 1000

            choices = []
            for idx, choice in enumerate(response.choices):
                message = ChatMessage(
                    role=MessageRole(choice.message.role),
                    content=choice.message.content or "",
                )
                choices.append(ChatCompletionChoice(
                    index=idx,
                    message=message,
                    finish_reason=choice.finish_reason or "stop",
                ))

            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

            return ChatCompletionResponse(
                id=response.id,
                model=response.model,
                choices=choices,
                usage=usage,
                created=response.created,
                provider=self.provider,
                latency_ms=latency_ms,
            )

        except httpx.TimeoutException as e:
            logger.error("moonshot_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("moonshot_error", model=request.model, error=str(e))
            raise AdapterError(f"Moonshot API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        try:
            messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
            }

            if request.max_tokens:
                request_params["max_tokens"] = request.max_tokens

            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                delta = {}
                finish_reason = None

                if chunk.choices:
                    choice = chunk.choices[0]
                    if choice.delta:
                        if choice.delta.content:
                            delta["content"] = choice.delta.content
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                yield StreamChunk(
                    id=chunk.id or request_id,
                    model=chunk.model or request.model,
                    delta=delta,
                    finish_reason=finish_reason,
                    provider=self.provider,
                )

        except Exception as e:
            logger.error("moonshot_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Moonshot streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            texts = request.input if isinstance(request.input, list) else [request.input]

            response = await self.client.embeddings.create(
                model=request.model,
                input=texts,
            )

            embeddings = [
                Embedding(index=e.index, embedding=e.embedding)
                for e in response.data
            ]

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=response.model,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=0,
                    total_tokens=response.usage.total_tokens,
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("moonshot_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Moonshot embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        return MOONSHOT_MODELS

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model.startswith("moonshot-")

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()


# Register model prefixes
AdapterRegistry.register_model_prefix("moonshot-", Provider.MOONSHOT)
