"""Base adapter interface for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator


class MessageRole(StrEnum):
    """Message role types."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """Unified chat message representation."""

    role: MessageRole
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI message format."""
        msg: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            msg["name"] = self.name
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic message format."""
        # Anthropic uses different format for system messages
        if self.role == MessageRole.SYSTEM:
            return {"type": "system", "content": self.content}

        msg: dict[str, Any] = {"role": self.role.value}

        # Handle content
        if isinstance(self.content, str):
            msg["content"] = [{"type": "text", "text": self.content}]
        else:
            msg["content"] = self.content

        return msg


@dataclass
class ToolDefinition:
    """Unified tool definition."""

    type: str = "function"
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI tool format."""
        return {
            "type": self.type,
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ChatCompletionRequest:
    """Unified chat completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int | None = None
    stream: bool = False
    tools: list[ToolDefinition] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stop: list[str] | None = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    user: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatCompletionChoice:
    """A single completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str
    logprobs: dict[str, Any] | None = None


@dataclass
class Usage:
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_openai_format(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def to_anthropic_format(self) -> dict[str, int]:
        return {
            "input_tokens": self.prompt_tokens,
            "output_tokens": self.completion_tokens,
        }


@dataclass
class ChatCompletionResponse:
    """Unified chat completion response."""

    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage
    created: int
    system_fingerprint: str | None = None
    provider: str = "unknown"
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI response format."""
        return {
            "id": self.id,
            "object": "chat.completion",
            "created": self.created,
            "model": self.model,
            "system_fingerprint": self.system_fingerprint,
            "choices": [
                {
                    "index": c.index,
                    "message": c.message.to_openai_format(),
                    "finish_reason": c.finish_reason,
                    "logprobs": c.logprobs,
                }
                for c in self.choices
            ],
            "usage": self.usage.to_openai_format(),
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic response format."""
        choice = self.choices[0] if self.choices else None
        if not choice:
            return {}

        return {
            "id": self.id,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": choice.message.content}],
            "model": self.model,
            "stop_reason": choice.finish_reason,
            "usage": self.usage.to_anthropic_format(),
        }


@dataclass
class StreamChunk:
    """A single streaming chunk."""

    id: str
    model: str
    delta: dict[str, Any]
    finish_reason: str | None = None
    usage: Usage | None = None
    provider: str = "unknown"

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI streaming format."""
        chunk: dict[str, Any] = {
            "id": self.id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": self.delta,
                    "finish_reason": self.finish_reason,
                }
            ],
        }
        if self.usage:
            chunk["usage"] = self.usage.to_openai_format()
        return chunk

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic streaming format."""
        event_type = "content_block_delta"
        if self.finish_reason:
            event_type = "message_stop"

        return {
            "type": event_type,
            "index": 0,
            "delta": self.delta,
        }


@dataclass
class EmbeddingRequest:
    """Unified embedding request."""

    model: str
    input: str | list[str]
    encoding_format: str = "float"
    dimensions: int | None = None
    user: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Embedding:
    """A single embedding."""

    index: int
    embedding: list[float]
    object: str = "embedding"


@dataclass
class EmbeddingResponse:
    """Unified embedding response."""

    id: str
    model: str
    data: list[Embedding]
    usage: Usage
    provider: str = "unknown"


class BaseAdapter(ABC):
    """Abstract base class for LLM provider adapters.

    Each provider adapter must implement these methods to provide
    unified access to different LLM backends.
    """

    provider: str = "base"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        api_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.api_version = api_version
        self.config = kwargs

    @abstractmethod
    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute a chat completion request.

        Args:
            request: Unified chat completion request

        Returns:
            Unified chat completion response

        Raises:
            AdapterError: If the request fails
        """
        pass

    @abstractmethod
    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute a streaming chat completion request.

        Args:
            request: Unified chat completion request with stream=True

        Yields:
            StreamChunk objects as they arrive

        Raises:
            AdapterError: If the request fails
        """
        pass

    @abstractmethod
    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute an embedding request.

        Args:
            request: Unified embedding request

        Returns:
            Unified embedding response

        Raises:
            AdapterError: If the request fails
        """
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models for this provider.

        Returns:
            List of model identifiers
        """
        pass

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Check if this adapter supports the given model.

        Args:
            model: Model identifier to check

        Returns:
            True if the model is supported
        """
        pass

    async def close(self) -> None:
        """Close any open connections or resources."""
        pass

    async def __aenter__(self) -> "BaseAdapter":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
