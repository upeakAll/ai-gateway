"""Anthropic API schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============ Messages API ============


class ContentBlock(BaseModel):
    """Content block in Anthropic format."""

    type: Literal["text", "image", "tool_use", "tool_result"]
    text: str | None = None
    source: dict[str, Any] | None = None  # For images
    id: str | None = None  # For tool_use
    name: str | None = None  # For tool_use
    input: dict[str, Any] | None = None  # For tool_use
    tool_use_id: str | None = None  # For tool_result
    content: str | list[dict[str, Any]] | None = None  # For tool_result


class AnthropicMessage(BaseModel):
    """Message in Anthropic format."""

    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


class AnthropicTool(BaseModel):
    """Tool definition for Anthropic."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class AnthropicMessagesRequest(BaseModel):
    """Messages request in Anthropic format."""

    model: str
    messages: list[AnthropicMessage]
    max_tokens: int
    system: str | list[dict[str, Any]] | None = None
    temperature: float | None = Field(default=1.0, ge=0, le=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    tools: list[AnthropicTool] | None = None
    tool_choice: Literal["auto", "any", "tool"] | dict[str, str] | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class AnthropicUsage(BaseModel):
    """Usage information in Anthropic format."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class AnthropicResponseMessage(BaseModel):
    """Response message in Anthropic format."""

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock]
    model: str
    stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"] | None = None
    stop_sequence: str | None = None
    usage: AnthropicUsage

    model_config = ConfigDict(from_attributes=True)


# ============ Streaming Events ============


class AnthropicStreamEvent(BaseModel):
    """Base streaming event."""

    type: str
    index: int | None = None


class MessageStartEvent(AnthropicStreamEvent):
    """Message start event."""

    type: Literal["message_start"] = "message_start"
    message: dict[str, Any]


class ContentBlockStartEvent(AnthropicStreamEvent):
    """Content block start event."""

    type: Literal["content_block_start"] = "content_block_start"
    content_block: ContentBlock


class ContentBlockDeltaEvent(AnthropicStreamEvent):
    """Content block delta event."""

    type: Literal["content_block_delta"] = "content_block_delta"
    delta: dict[str, Any]


class ContentBlockStopEvent(AnthropicStreamEvent):
    """Content block stop event."""

    type: Literal["content_block_stop"] = "content_block_stop"


class MessageDeltaEvent(AnthropicStreamEvent):
    """Message delta event."""

    type: Literal["message_delta"] = "message_delta"
    delta: dict[str, Any]
    usage: dict[str, int] | None = None


class MessageStopEvent(AnthropicStreamEvent):
    """Message stop event."""

    type: Literal["message_stop"] = "message_stop"
