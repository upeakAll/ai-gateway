"""Tool-level access control for MCP."""

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ToolAccessRule:
    """Access rule for a tool."""

    tool_name: str
    allowed_roles: list[str] | None = None
    allowed_tenant_ids: list[str] | None = None
    rate_limit_per_minute: int | None = None
    requires_confirmation: bool = False
    is_dangerous: bool = False
    custom_validator: str | None = None  # Python expression for validation


class ToolAccessController:
    """Controller for tool-level access control."""

    def __init__(self) -> None:
        self._rules: dict[str, ToolAccessRule] = {}

    def set_rule(self, rule: ToolAccessRule) -> None:
        """Set access rule for a tool."""
        self._rules[rule.tool_name] = rule

    def get_rule(self, tool_name: str) -> ToolAccessRule | None:
        """Get access rule for a tool."""
        return self._rules.get(tool_name)

    def remove_rule(self, tool_name: str) -> None:
        """Remove access rule for a tool."""
        self._rules.pop(tool_name, None)

    def check_access(
        self,
        tool_name: str,
        user_roles: list[str],
        tenant_id: str | None = None,
    ) -> tuple[bool, str]:
        """Check if access is allowed for a tool.

        Args:
            tool_name: Name of the tool
            user_roles: User's roles
            tenant_id: User's tenant ID

        Returns:
            Tuple of (allowed, reason)
        """
        rule = self._rules.get(tool_name)

        # No rule = allow by default (can be changed)
        if not rule:
            return True, ""

        # Check role restriction
        if rule.allowed_roles:
            if not any(role in rule.allowed_roles for role in user_roles):
                return False, f"Tool requires one of roles: {rule.allowed_roles}"

        # Check tenant restriction
        if rule.allowed_tenant_ids:
            if not tenant_id:
                return False, "Tool requires tenant context"
            if tenant_id not in rule.allowed_tenant_ids:
                return False, "Tool not available for your tenant"

        return True, ""

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if tool requires user confirmation."""
        rule = self._rules.get(tool_name)
        return rule.requires_confirmation if rule else False

    def is_dangerous(self, tool_name: str) -> bool:
        """Check if tool is marked as dangerous."""
        rule = self._rules.get(tool_name)
        return rule.is_dangerous if rule else False

    def get_rate_limit(self, tool_name: str) -> int | None:
        """Get rate limit for a tool."""
        rule = self._rules.get(tool_name)
        return rule.rate_limit_per_minute if rule else None

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate tool arguments using custom validator.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tuple of (valid, error_message)
        """
        rule = self._rules.get(tool_name)

        if not rule or not rule.custom_validator:
            return True, ""

        try:
            # Safe evaluation of simple expressions
            # Only allow basic comparisons and attribute access
            allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.!=<>\"' ")
            if not all(c in allowed_chars for c in rule.custom_validator):
                return False, "Invalid validator expression"

            # Create a safe evaluation context
            context = {"args": arguments}

            # Evaluate the expression
            result = eval(rule.custom_validator, {"__builtins__": {}}, context)

            if not result:
                return False, "Argument validation failed"

            return True, ""

        except Exception as e:
            logger.warning(
                "tool_validation_error",
                tool_name=tool_name,
                error=str(e),
            )
            return False, f"Validation error: {str(e)}"


# Global tool access controller
tool_access_controller = ToolAccessController()
