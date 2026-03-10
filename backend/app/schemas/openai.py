"""OpenAI-compatible API schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============ Thinking Configuration ============


class ThinkingConfigSchema(BaseModel):
    """Thinking configuration for deep reasoning.

    This provides a unified interface for controlling deep thinking/reasoning
    across different LLM providers.
    """

    mode: Literal["enabled", "disabled", "auto"] = "disabled"
    budget_tokens: int | None = Field(default=None, ge=100, le=100000)
    effort: Literal["low", "medium", "high"] | None = None
    include_thinking: bool = True

    model_config = ConfigDict(extra="allow")


# ============ Chat Completions ============


class ChatCompletionMessage(BaseModel):
    """Chat message in OpenAI format."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None  # Thinking/reasoning content (DeepSeek/OpenAI style)


class ChatCompletionToolFunction(BaseModel):
    """Tool function definition."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionTool(BaseModel):
    """Tool definition for function calling."""

    type: Literal["function"] = "function"
    function: ChatCompletionToolFunction


class ChatCompletionRequest(BaseModel):
    """Chat completion request in OpenAI format."""

    model: str
    messages: list[ChatCompletionMessage]
    temperature: float | None = Field(default=1.0, ge=0, le=2)
    top_p: float | None = Field(default=1.0, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    stream: bool = False
    tools: list[ChatCompletionTool] | None = None
    tool_choice: Literal["none", "auto", "required"] | dict[str, Any] | None = None
    stop: str | list[str] | None = None
    frequency_penalty: float | None = Field(default=0, ge=-2, le=2)
    presence_penalty: float | None = Field(default=0, ge=-2, le=2)
    n: int | None = Field(default=1, ge=1, le=10)
    user: str | None = None

    # Thinking/reasoning configuration
    thinking: ThinkingConfigSchema | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None  # OpenAI native

    model_config = ConfigDict(extra="allow")  # Allow extra fields for compatibility


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""

    index: int
    message: ChatCompletionMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None
    logprobs: dict[str, Any] | None = None


class CompletionTokensDetails(BaseModel):
    """Detailed completion tokens breakdown."""

    reasoning_tokens: int = 0
    accepted_prediction_tokens: int = 0
    rejected_prediction_tokens: int = 0


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    completion_tokens_details: CompletionTokensDetails | None = None


class ChatCompletionResponse(BaseModel):
    """Chat completion response in OpenAI format."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage
    system_fingerprint: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ============ Streaming ============


class ChatCompletionStreamDelta(BaseModel):
    """Delta content in streaming response."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None  # Thinking delta (DeepSeek/OpenAI style)


class ChatCompletionStreamChoice(BaseModel):
    """A single streaming choice."""

    index: int
    delta: ChatCompletionStreamDelta
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None = None
    logprobs: dict[str, Any] | None = None


class ChatCompletionStreamResponse(BaseModel):
    """Streaming chat completion response."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    system_fingerprint: str | None = None
    choices: list[ChatCompletionStreamChoice]
    usage: Usage | None = None  # Only in final chunk


# ============ Embeddings ============


class EmbeddingRequest(BaseModel):
    """Embedding request in OpenAI format."""

    model: str
    input: str | list[str]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = None
    user: str | None = None

    model_config = ConfigDict(extra="allow")


class Embedding(BaseModel):
    """A single embedding."""

    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float] | str  # float array or base64 string


class EmbeddingResponse(BaseModel):
    """Embedding response in OpenAI format."""

    object: Literal["list"] = "list"
    data: list[Embedding]
    model: str
    usage: Usage

    model_config = ConfigDict(from_attributes=True)


# ============ Models ============


class ModelInfo(BaseModel):
    """Model information."""

    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "ai-gateway"
    permission: list[dict[str, Any]] = Field(default_factory=list)
    root: str | None = None
    parent: str | None = None


class ModelListResponse(BaseModel):
    """Model list response."""

    object: Literal["list"] = "list"
    data: list[ModelInfo]
