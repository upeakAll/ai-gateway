"""MCP Prompts module."""

from app.mcp.prompts.manager import (
    Prompt,
    PromptArgument,
    PromptManager,
    PromptMessage,
    prompt_manager,
    BUILTIN_PROMPTS,
)

__all__ = [
    "Prompt",
    "PromptArgument",
    "PromptMessage",
    "PromptManager",
    "prompt_manager",
    "BUILTIN_PROMPTS",
]
