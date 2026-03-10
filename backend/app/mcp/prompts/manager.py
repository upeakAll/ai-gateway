"""MCP Prompts implementation."""

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class PromptArgument:
    """Argument definition for a prompt."""

    name: str
    description: str | None = None
    required: bool = False

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP format."""
        result: dict[str, Any] = {"name": self.name}
        if self.description:
            result["description"] = self.description
        if self.required:
            result["required"] = True
        return result


@dataclass
class PromptMessage:
    """Message in a prompt template."""

    role: str  # "user" or "assistant"
    content: str

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP format."""
        return {
            "role": self.role,
            "content": {"type": "text", "text": self.content},
        }


@dataclass
class Prompt:
    """MCP Prompt definition."""

    name: str
    description: str | None = None
    arguments: list[PromptArgument] = field(default_factory=list)
    messages: list[PromptMessage] = field(default_factory=list)
    template: str | None = None

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP protocol format."""
        result: dict[str, Any] = {"name": self.name}
        if self.description:
            result["description"] = self.description
        if self.arguments:
            result["arguments"] = [arg.to_mcp_format() for arg in self.arguments]
        return result

    def render(self, arguments: dict[str, Any] | None = None) -> list[PromptMessage]:
        """Render prompt with given arguments."""
        arguments = arguments or {}

        if self.template:
            # Render template with arguments
            rendered = self._render_template(self.template, arguments)
            return [PromptMessage(role="user", content=rendered)]

        # Use pre-defined messages
        rendered_messages = []
        for msg in self.messages:
            content = self._render_template(msg.content, arguments)
            rendered_messages.append(PromptMessage(role=msg.role, content=content))

        return rendered_messages

    def _render_template(self, template: str, arguments: dict[str, Any]) -> str:
        """Render a template string with arguments."""
        result = template
        for key, value in arguments.items():
            placeholder = f"{{{key}}}"
            result = result.replace(placeholder, str(value))
        return result


class PromptManager:
    """Manager for MCP prompts."""

    def __init__(self) -> None:
        self._prompts: dict[str, Prompt] = {}

    def register_prompt(self, prompt: Prompt) -> None:
        """Register a prompt."""
        self._prompts[prompt.name] = prompt
        logger.info("prompt_registered", name=prompt.name)

    def unregister_prompt(self, name: str) -> None:
        """Unregister a prompt."""
        self._prompts.pop(name, None)

    def list_prompts(self) -> list[Prompt]:
        """List all registered prompts."""
        return list(self._prompts.values())

    def get_prompt(self, name: str) -> Prompt | None:
        """Get a prompt by name."""
        return self._prompts.get(name)

    def get_prompt_messages(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get rendered messages for a prompt."""
        prompt = self._prompts.get(name)
        if not prompt:
            raise ValueError(f"Prompt not found: {name}")

        # Validate required arguments
        if prompt.arguments:
            provided = set(arguments or {})
            required = {arg.name for arg in prompt.arguments if arg.required}

            missing = required - provided
            if missing:
                raise ValueError(f"Missing required arguments: {missing}")

        messages = prompt.render(arguments)
        return [msg.to_mcp_format() for msg in messages]


# Built-in prompts
BUILTIN_PROMPTS = [
    Prompt(
        name="code-review",
        description="Review code for potential issues and improvements",
        arguments=[
            PromptArgument(name="code", description="Code to review", required=True),
            PromptArgument(name="language", description="Programming language"),
        ],
        template="Please review the following {language} code and provide feedback on potential issues, improvements, and best practices:\n\n{code}",
    ),
    Prompt(
        name="explain-code",
        description="Explain what a piece of code does",
        arguments=[
            PromptArgument(name="code", description="Code to explain", required=True),
        ],
        template="Please explain what the following code does, including its purpose, inputs, outputs, and any important details:\n\n{code}",
    ),
    Prompt(
        name="write-tests",
        description="Generate unit tests for code",
        arguments=[
            PromptArgument(name="code", description="Code to test", required=True),
            PromptArgument(name="framework", description="Test framework to use"),
        ],
        template="Write unit tests for the following code using {framework}:\n\n{code}",
    ),
    Prompt(
        name="refactor",
        description="Refactor code for better quality",
        arguments=[
            PromptArgument(name="code", description="Code to refactor", required=True),
            PromptArgument(name="goal", description="Refactoring goal (e.g., readability, performance)"),
        ],
        template="Refactor the following code with the goal of {goal}:\n\n{code}",
    ),
    Prompt(
        name="translate",
        description="Translate code from one language to another",
        arguments=[
            PromptArgument(name="code", description="Code to translate", required=True),
            PromptArgument(name="from_lang", description="Source language", required=True),
            PromptArgument(name="to_lang", description="Target language", required=True),
        ],
        template="Translate the following {from_lang} code to {to_lang}, maintaining the same functionality:\n\n{code}",
    ),
]


# Global prompt manager
prompt_manager = PromptManager()

# Register built-in prompts
for prompt in BUILTIN_PROMPTS:
    prompt_manager.register_prompt(prompt)
