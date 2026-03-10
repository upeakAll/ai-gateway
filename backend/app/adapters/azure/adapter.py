"""Azure OpenAI adapter implementation."""

import time
from typing import Any, AsyncIterator

import httpx
import structlog
from openai import AsyncAzureOpenAI

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
    ToolDefinition,
    Usage,
)
from app.adapters.registry import AdapterRegistry, register_adapter
from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()

# Azure OpenAI deployment naming patterns
AZURE_MODEL_PATTERNS = [
    "gpt-35-turbo",
    "gpt-35-turbo-16k",
    "gpt-4",
    "gpt-4-32k",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "text-embedding-ada-002",
    "text-embedding-3-small",
    "text-embedding-3-large",
]


@register_adapter(Provider.AZURE_OPENAI)
class AzureOpenAIAdapter(BaseAdapter):
    """Azure OpenAI API adapter.

    Uses the Azure OpenAI service with deployment-based model access.
    """

    provider = "azure_openai"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        api_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, api_version, **kwargs)

        # Azure requires api_base and api_version
        if not api_base:
            raise AdapterError(
                "Azure OpenAI requires api_base (endpoint)",
                provider=self.provider,
            )

        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=api_base,
            api_version=api_version or "2024-02-15-preview",
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
        """Execute a chat completion request using Azure OpenAI API."""
        start_time = time.time()

        try:
            # Build Azure OpenAI request (similar to OpenAI)
            openai_messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,  # In Azure, this is the deployment name
                "messages": openai_messages,
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
                    tool.to_openai_format() for tool in request.tools
                ]
            if request.tool_choice:
                request_params["tool_choice"] = request.tool_choice

            # Execute request
            response = await self.client.chat.completions.create(**request_params)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Build unified response
            choices = []
            for idx, choice in enumerate(response.choices):
                message = ChatMessage(
                    role=MessageRole(choice.message.role),
                    content=choice.message.content or "",
                    tool_calls=self._convert_tool_calls(choice.message.tool_calls),
                )
                choices.append(
                    ChatCompletionChoice(
                        index=idx,
                        message=message,
                        finish_reason=choice.finish_reason or "stop",
                    )
                )

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
                system_fingerprint=response.system_fingerprint,
                provider=self.provider,
                latency_ms=latency_ms,
            )

        except httpx.TimeoutException as e:
            logger.error("azure_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise AdapterRateLimitError(
                    provider=self.provider,
                    retry_after=int(retry_after) if retry_after else None,
                ) from e
            logger.error("azure_http_error", status=e.response.status_code)
            raise AdapterError(
                f"Azure OpenAI API error: {e.response.status_code}",
                provider=self.provider,
            ) from e

        except Exception as e:
            logger.error("azure_error", model=request.model, error=str(e))
            raise AdapterError(f"Azure OpenAI API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute a streaming chat completion request."""
        request_id = f"chatcmpl-{int(time.time())}"

        try:
            openai_messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": openai_messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
                "stream_options": {"include_usage": True},
            }

            if request.max_tokens:
                request_params["max_tokens"] = request.max_tokens
            if request.tools:
                request_params["tools"] = [
                    tool.to_openai_format() for tool in request.tools
                ]

            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                delta = {}
                finish_reason = None
                usage = None

                if chunk.choices:
                    choice = chunk.choices[0]
                    if choice.delta:
                        if choice.delta.content:
                            delta["content"] = choice.delta.content
                        if choice.delta.role:
                            delta["role"] = choice.delta.role
                        if choice.delta.tool_calls:
                            delta["tool_calls"] = [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in choice.delta.tool_calls
                            ]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                if chunk.usage:
                    usage = Usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )

                yield StreamChunk(
                    id=chunk.id or request_id,
                    model=chunk.model or request.model,
                    delta=delta,
                    finish_reason=finish_reason,
                    usage=usage,
                    provider=self.provider,
                )

        except httpx.TimeoutException as e:
            logger.error("azure_stream_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("azure_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Azure streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute an embedding request."""
        try:
            input_texts = request.input if isinstance(request.input, list) else [request.input]

            request_params: dict[str, Any] = {
                "model": request.model,
                "input": input_texts,
            }

            response = await self.client.embeddings.create(**request_params)

            embeddings = [
                Embedding(
                    index=item.index,
                    embedding=item.embedding,
                    object="embedding",
                )
                for item in response.data
            ]

            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=0,
                total_tokens=response.usage.total_tokens,
            )

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=response.model,
                data=embeddings,
                usage=usage,
                provider=self.provider,
            )

        except Exception as e:
            logger.error("azure_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Azure embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List Azure deployments (requires management API or manual configuration)."""
        # Azure doesn't have a simple list models API for deployments
        # Return common deployment names
        return AZURE_MODEL_PATTERNS

    def supports_model(self, model: str) -> bool:
        """Check if model looks like an Azure deployment name."""
        model_lower = model.lower()
        for pattern in AZURE_MODEL_PATTERNS:
            if model_lower.startswith(pattern):
                return True
        # Azure deployments can have custom names
        return True

    def _convert_tool_calls(
        self, tool_calls: list[Any] | None
    ) -> list[dict[str, Any]] | None:
        """Convert tool calls to unified format."""
        if not tool_calls:
            return None

        return [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()


# Register Azure OpenAI model patterns
for pattern in AZURE_MODEL_PATTERNS:
    AdapterRegistry.register_model_prefix(pattern, Provider.AZURE_OPENAI)
