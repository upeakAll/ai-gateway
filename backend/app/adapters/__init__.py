"""Adapters package for LLM providers."""

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

# Cloud providers
from app.adapters.openai import OpenAIAdapter
from app.adapters.anthropic import AnthropicAdapter
from app.adapters.azure import AzureOpenAIAdapter
from app.adapters.bedrock import BedrockAdapter

# Domestic (Chinese) providers
from app.adapters.domestic import (
    AliyunAdapter,
    BaiduAdapter,
    ZhipuAdapter,
    DeepSeekAdapter,
    MiniMaxAdapter,
    MoonshotAdapter,
    BaichuanAdapter,
)

# Open source / local
from app.adapters.open_source import OllamaAdapter, VLLMAdapter

__all__ = [
    # Base
    "BaseAdapter",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionChoice",
    "StreamChunk",
    "ToolDefinition",
    "Usage",
    "MessageRole",
    "Embedding",
    "EmbeddingRequest",
    "EmbeddingResponse",
    # Registry
    "AdapterRegistry",
    "register_adapter",
    # Cloud providers
    "OpenAIAdapter",
    "AnthropicAdapter",
    "AzureOpenAIAdapter",
    "BedrockAdapter",
    # Domestic providers
    "AliyunAdapter",
    "BaiduAdapter",
    "ZhipuAdapter",
    "DeepSeekAdapter",
    "MiniMaxAdapter",
    "MoonshotAdapter",
    "BaichuanAdapter",
    # Open source
    "OllamaAdapter",
    "VLLMAdapter",
]
