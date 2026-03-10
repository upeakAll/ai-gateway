"""Anthropic adapter implementation with OpenAI protocol conversion."""

import time
from typing import Any, AsyncIterator

import httpx
import structlog
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicMessage

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

# Model prefixes for Anthropic
ANTHROPIC_MODEL_PREFIXES = [
    "claude-",
    "claude3-",
]


@register_adapter(Provider.ANTHROPIC)
class AnthropicAdapter(BaseAdapter):
    """Anthropic API adapter supporting Claude models.

    Handles conversion between OpenAI-compatible and Anthropic formats.
    """

    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        api_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, api_version, **kwargs)

        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=api_base,
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
        """Execute a chat completion request using Anthropic API."""
        start_time = time.time()

        try:
            # Convert OpenAI format to Anthropic format
            system_prompt, messages = self._convert_messages(request.messages)

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_tokens or 4096,
            }

            if system_prompt:
                request_params["system"] = system_prompt

            if request.temperature != 1.0:
                request_params["temperature"] = request.temperature
            if request.top_p != 1.0:
                request_params["top_p"] = request.top_p
            if request.stop:
                request_params["stop_sequences"] = request.stop
            if request.user:
                request_params["metadata"] = {"user_id": request.user}

            if request.tools:
                request_params["tools"] = [
                    tool.to_anthropic_format() for tool in request.tools
                ]

            # Execute request
            response = await self.client.messages.create(**request_params)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Convert response to unified format
            return self._convert_response(response, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("anthropic_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise AdapterRateLimitError(
                    provider=self.provider,
                    retry_after=int(retry_after) if retry_after else None,
                ) from e
            logger.error("anthropic_http_error", status=e.response.status_code)
            raise AdapterError(
                f"Anthropic API error: {e.response.status_code}",
                provider=self.provider,
            ) from e

        except Exception as e:
            logger.error("anthropic_error", model=request.model, error=str(e))
            raise AdapterError(f"Anthropic API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute a streaming chat completion request."""
        request_id = f"msg-{int(time.time())}"

        try:
            # Convert messages
            system_prompt, messages = self._convert_messages(request.messages)

            request_params: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_tokens or 4096,
                "stream": True,
            }

            if system_prompt:
                request_params["system"] = system_prompt
            if request.temperature != 1.0:
                request_params["temperature"] = request.temperature
            if request.tools:
                request_params["tools"] = [
                    tool.to_anthropic_format() for tool in request.tools
                ]

            # Execute streaming request
            async with self.client.messages.stream(**request_params) as stream:
                async for event in stream:
                    chunk = self._convert_stream_event(event, request_id, request.model)
                    if chunk:
                        yield chunk

                # Get final message for usage
                final_message = await stream.get_final_message()
                yield StreamChunk(
                    id=request_id,
                    model=request.model,
                    delta={},
                    finish_reason=final_message.stop_reason or "end_turn",
                    usage=Usage(
                        prompt_tokens=final_message.usage.input_tokens,
                        completion_tokens=final_message.usage.output_tokens,
                        total_tokens=final_message.usage.input_tokens
                        + final_message.usage.output_tokens,
                    ),
                    provider=self.provider,
                )

        except httpx.TimeoutException as e:
            logger.error("anthropic_stream_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("anthropic_stream_error", model=request.model, error=str(e))
            raise AdapterError(
                f"Anthropic streaming error: {str(e)}", provider=self.provider
            ) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Anthropic doesn't support embeddings natively.

        This raises an error - use OpenAI or another provider for embeddings.
        """
        raise AdapterError(
            "Anthropic does not support embeddings. Use a different provider.",
            provider=self.provider,
        )

    async def list_models(self) -> list[str]:
        """List available Claude models."""
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]

    def supports_model(self, model: str) -> bool:
        """Check if model is supported by Anthropic."""
        model_lower = model.lower()
        for prefix in ANTHROPIC_MODEL_PREFIXES:
            if model_lower.startswith(prefix):
                return True
        return False

    def _convert_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert unified messages to Anthropic format.

        Anthropic uses a separate system parameter and requires specific content format.

        Returns:
            Tuple of (system_prompt, messages_list)
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Extract system prompt
                if isinstance(msg.content, str):
                    system_prompt = msg.content
                else:
                    # Handle structured content for system
                    system_prompt = " ".join(
                        c.get("text", "") for c in msg.content if c.get("type") == "text"
                    )
            else:
                # Convert content to Anthropic format
                content = self._convert_content(msg.content)

                anthropic_msg: dict[str, Any] = {
                    "role": msg.role.value,
                    "content": content,
                }

                anthropic_messages.append(anthropic_msg)

        return system_prompt, anthropic_messages

    def _convert_content(
        self, content: str | list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert content to Anthropic's content block format."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}]

        converted = []
        for block in content:
            block_type = block.get("type", "text")

            if block_type == "text":
                converted.append({"type": "text", "text": block.get("text", "")})
            elif block_type == "image_url":
                # Convert OpenAI image format to Anthropic format
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")

                if url.startswith("data:"):
                    # Base64 encoded image
                    media_type, data = url.split(",", 1)
                    media_type = media_type.split(":")[1].split(";")[0]
                    converted.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    })
                else:
                    # URL image - Anthropic requires base64, so we need to fetch
                    # For now, log a warning
                    logger.warning("anthropic_url_image_not_supported", url=url)
            elif block_type == "tool_use":
                converted.append({
                    "type": "tool_use",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                })
            elif block_type == "tool_result":
                converted.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "content": block.get("content", ""),
                })

        return converted

    def _convert_response(
        self, response: AnthropicMessage, model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Convert Anthropic response to unified format."""
        # Extract content
        text_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": str(block.input),
                    },
                })

        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
        )

        choice = ChatCompletionChoice(
            index=0,
            message=message,
            finish_reason=response.stop_reason or "end_turn",
        )

        usage = Usage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        return ChatCompletionResponse(
            id=response.id,
            model=response.model,
            choices=[choice],
            usage=usage,
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _convert_stream_event(
        self, event: Any, request_id: str, model: str
    ) -> StreamChunk | None:
        """Convert Anthropic stream event to unified chunk format."""
        event_type = getattr(event, "type", None)

        if event_type == "content_block_delta":
            delta = event.delta
            if hasattr(delta, "type") and delta.type == "text_delta":
                return StreamChunk(
                    id=request_id,
                    model=model,
                    delta={"content": delta.text},
                    provider=self.provider,
                )
            elif hasattr(delta, "type") and delta.type == "input_json_delta":
                # Tool use partial
                return StreamChunk(
                    id=request_id,
                    model=model,
                    delta={
                        "tool_calls": [{
                            "function": {"arguments": delta.partial_json},
                        }]
                    },
                    provider=self.provider,
                )

        elif event_type == "content_block_start":
            block = event.content_block
            if hasattr(block, "type") and block.type == "tool_use":
                return StreamChunk(
                    id=request_id,
                    model=model,
                    delta={
                        "tool_calls": [{
                            "id": block.id,
                            "type": "function",
                            "function": {"name": block.name, "arguments": ""},
                        }]
                    },
                    provider=self.provider,
                )

        return None

    async def close(self) -> None:
        """Close the Anthropic client."""
        await self.client.close()


# Register model prefixes
for prefix in ANTHROPIC_MODEL_PREFIXES:
    AdapterRegistry.register_model_prefix(prefix, Provider.ANTHROPIC)
