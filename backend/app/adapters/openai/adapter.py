"""OpenAI adapter implementation."""

import time
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
    ThinkingConfig,
    ThinkingContent,
    ThinkingEffort,
    ThinkingMode,
    ToolDefinition,
    Usage,
)
from app.adapters.registry import AdapterRegistry, register_adapter
from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()

# Model prefixes for OpenAI
OPENAI_MODEL_PREFIXES = [
    "gpt-",
    "o1-",
    "o1",
    "o3-",
    "o3",
    "chatgpt-",
    "text-embedding-",
    "text-davinci-",
]

# Thinking-capable models
THINKING_MODELS = [
    "o1-preview",
    "o1-mini",
    "o3-mini",
    "o3",
]


@register_adapter(Provider.OPENAI)
class OpenAIAdapter(BaseAdapter):
    """OpenAI API adapter supporting GPT and embedding models."""

    provider = "openai"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        api_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, api_version, **kwargs)

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base or "https://api.openai.com/v1",
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
            max_retries=0,  # We handle retries ourselves
        )

    def _is_thinking_model(self, model: str) -> bool:
        """Check if model supports thinking/reasoning."""
        model_lower = model.lower()
        return any(m in model_lower for m in ["o1", "o3"])

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute a chat completion request using OpenAI API."""
        start_time = time.time()

        try:
            # Build OpenAI request
            openai_messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": openai_messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": False,
            }

            if request.max_tokens:
                request_params["max_tokens"] = request.max_tokens
            if request.stop:
                request_params["stop"] = request.stop
            if request.frequency_penalty:
                request_params["frequency_penalty"] = request.frequency_penalty
            if request.presence_penalty:
                request_params["presence_penalty"] = request.presence_penalty
            if request.user:
                request_params["user"] = request.user
            if request.tools:
                request_params["tools"] = [
                    tool.to_openai_format() for tool in request.tools
                ]
            if request.tool_choice:
                request_params["tool_choice"] = request.tool_choice

            # Add thinking/reasoning parameters for supported models
            if request.thinking and self._is_thinking_model(request.model):
                thinking_params = request.thinking.to_openai_format()
                request_params.update(thinking_params)

            # Execute request
            response = await self.client.chat.completions.create(**request_params)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Build unified response with thinking support
            choices = []
            for idx, choice in enumerate(response.choices):
                # Extract thinking/reasoning content
                thinking = None
                if hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                    thinking = ThinkingContent(
                        content=choice.message.reasoning_content,
                        metadata={"source": "openai"}
                    )

                message = ChatMessage(
                    role=MessageRole(choice.message.role),
                    content=choice.message.content or "",
                    tool_calls=self._convert_tool_calls(choice.message.tool_calls),
                    thinking=thinking,
                )
                choices.append(
                    ChatCompletionChoice(
                        index=idx,
                        message=message,
                        finish_reason=choice.finish_reason or "stop",
                    )
                )

            # Extract usage with thinking tokens
            usage = self._extract_usage(response.usage)

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
            logger.error("openai_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise AdapterRateLimitError(
                    provider=self.provider,
                    retry_after=int(retry_after) if retry_after else None,
                ) from e
            logger.error("openai_http_error", status=e.response.status_code, error=str(e))
            raise AdapterError(
                f"OpenAI API error: {e.response.status_code}",
                provider=self.provider,
            ) from e

        except Exception as e:
            logger.error("openai_error", model=request.model, error=str(e))
            raise AdapterError(f"OpenAI API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute a streaming chat completion request."""
        request_id = f"chatcmpl-{int(time.time())}"

        try:
            # Build OpenAI request
            openai_messages = [msg.to_openai_format() for msg in request.messages]

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": openai_messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
                "stream_options": {"include_usage": True},  # Get usage in final chunk
            }

            if request.max_tokens:
                request_params["max_tokens"] = request.max_tokens
            if request.stop:
                request_params["stop"] = request.stop
            if request.tools:
                request_params["tools"] = [
                    tool.to_openai_format() for tool in request.tools
                ]

            # Add thinking/reasoning parameters for supported models
            if request.thinking and self._is_thinking_model(request.model):
                thinking_params = request.thinking.to_openai_format()
                request_params.update(thinking_params)

            # Execute streaming request
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                delta = {}
                finish_reason = None
                usage = None
                thinking_delta = None

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
                        # Extract thinking delta
                        if hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content:
                            thinking_delta = choice.delta.reasoning_content
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                if chunk.usage:
                    usage = self._extract_usage(chunk.usage)

                yield StreamChunk(
                    id=chunk.id or request_id,
                    model=chunk.model or request.model,
                    delta=delta,
                    finish_reason=finish_reason,
                    usage=usage,
                    provider=self.provider,
                    thinking_delta=thinking_delta,
                )

        except httpx.TimeoutException as e:
            logger.error("openai_stream_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("openai_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"OpenAI streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute an embedding request."""
        try:
            # Prepare input
            input_texts = request.input if isinstance(request.input, list) else [request.input]

            request_params: dict[str, Any] = {
                "model": request.model,
                "input": input_texts,
                "encoding_format": request.encoding_format,
            }

            if request.dimensions:
                request_params["dimensions"] = request.dimensions

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
            logger.error("openai_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"OpenAI embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        try:
            response = await self.client.models.list()
            return [model.id for model in response.data]
        except Exception as e:
            logger.warning("openai_list_models_error", error=str(e))
            # Return common models if API fails
            return [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                "text-embedding-3-large",
                "text-embedding-3-small",
                "text-embedding-ada-002",
            ]

    def supports_model(self, model: str) -> bool:
        """Check if model is supported by OpenAI."""
        model_lower = model.lower()
        for prefix in OPENAI_MODEL_PREFIXES:
            if model_lower.startswith(prefix):
                return True
        return False

    def _extract_usage(self, usage_obj: Any) -> Usage:
        """Extract usage including thinking tokens."""
        reasoning_tokens = None

        # OpenAI returns reasoning_tokens in completion_tokens_details
        if hasattr(usage_obj, 'completion_tokens_details'):
            details = usage_obj.completion_tokens_details
            reasoning_tokens = getattr(details, 'reasoning_tokens', None)

        return Usage(
            prompt_tokens=usage_obj.prompt_tokens,
            completion_tokens=usage_obj.completion_tokens,
            total_tokens=usage_obj.total_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def _convert_tool_calls(
        self, tool_calls: list[Any] | None
    ) -> list[dict[str, Any]] | None:
        """Convert OpenAI tool calls to unified format."""
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
        """Close the OpenAI client."""
        await self.client.close()


# Register model prefixes
for prefix in OPENAI_MODEL_PREFIXES:
    AdapterRegistry.register_model_prefix(prefix, Provider.OPENAI)
