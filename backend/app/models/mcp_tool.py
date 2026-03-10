"""MCP Tool model for tool registration and execution."""

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.mcp_server import MCPServer


class ToolStatus(StrEnum):
    """Status of an MCP tool."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class MCPTool(BaseModel):
    """MCP Tool definition with input schema and permissions."""

    __tablename__ = "mcp_tools"

    # Foreign keys
    server_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tool identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Tool name (unique within server)",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Tool description for LLM to understand usage",
    )

    # Input schema (JSON Schema format)
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="JSON Schema for tool input parameters",
    )

    # OpenAPI mapping (for OPENAPI-generated tools)
    openapi_operation_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="OpenAPI operationId this tool maps to",
    )
    openapi_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="OpenAPI path",
    )
    openapi_method: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="HTTP method (GET, POST, etc.)",
    )

    # Execution configuration
    execution_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Configuration for tool execution (headers, timeout, etc.)",
    )

    # Permission control
    required_permission: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Required permission to use this tool",
    )
    allowed_roles: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of roles allowed to use this tool",
    )
    allowed_tenant_ids: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of tenant IDs allowed to use this tool (null = all)",
    )

    # Status
    status: Mapped[ToolStatus] = mapped_column(
        Enum(ToolStatus),
        nullable=False,
        default=ToolStatus.ACTIVE,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # Safety configuration
    is_dangerous: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether tool requires additional confirmation",
    )
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether tool requires user confirmation before execution",
    )
    rate_limit_per_minute: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Rate limit per minute for this tool",
    )

    # Usage tracking
    total_invocations: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
    failed_invocations: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    # Relationships
    server: Mapped["MCPServer"] = relationship("MCPServer", back_populates="tools")

    @property
    def is_available(self) -> bool:
        """Check if tool is available for use."""
        return (
            self.is_active
            and self.status == ToolStatus.ACTIVE
            and self.server.is_available
        )

    def is_allowed_for_tenant(self, tenant_id: str | None) -> bool:
        """Check if tool is allowed for a specific tenant."""
        if self.allowed_tenant_ids is None:
            return True  # No tenant restriction
        if tenant_id is None:
            return False  # Tool has tenant restriction but no tenant provided
        return tenant_id in self.allowed_tenant_ids

    def is_allowed_for_role(self, role: str | None) -> bool:
        """Check if tool is allowed for a specific role."""
        if self.allowed_roles is None:
            return True  # No role restriction
        if role is None:
            return False  # Tool has role restriction but no role provided
        return role in self.allowed_roles

    def record_invocation(self, success: bool) -> None:
        """Record a tool invocation."""
        self.total_invocations += 1
        if not success:
            self.failed_invocations += 1

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP protocol tool format."""
        return {
            "name": self.name,
            "description": self.description or "",
            "inputSchema": self.input_schema,
        }
