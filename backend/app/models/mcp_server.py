"""MCP Server model for managing MCP protocol servers."""

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.mcp_tool import MCPTool
    from app.models.tenant import Tenant


class MCPTransport(StrEnum):
    """MCP transport types."""

    SSE = "sse"  # Server-Sent Events
    STREAMABLE_HTTP = "streamable_http"  # HTTP with streaming
    STDIO = "stdio"  # Standard I/O (for local processes)


class MCPServerStatus(StrEnum):
    """Status of an MCP server."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    INITIALIZING = "initializing"


class MCPServerType(StrEnum):
    """Type of MCP server configuration."""

    OPENAPI = "openapi"  # Generated from OpenAPI spec
    MANUAL = "manual"  # Manually configured tools
    REMOTE = "remote"  # Remote MCP server


class MCPServer(BaseModel):
    """MCP Server configuration for tool/resource/prompt serving."""

    __tablename__ = "mcp_servers"

    # Foreign keys
    tenant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL means shared server available to all tenants",
    )

    # Basic info
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Unique server name for identification",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Server type and transport
    server_type: Mapped[MCPServerType] = mapped_column(
        Enum(MCPServerType),
        nullable=False,
        default=MCPServerType.MANUAL,
    )
    transport: Mapped[MCPTransport] = mapped_column(
        Enum(MCPTransport),
        nullable=False,
        default=MCPTransport.SSE,
    )

    # OpenAPI configuration (for OPENAPI type)
    openapi_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="URL to OpenAPI specification",
    )
    openapi_spec: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Cached OpenAPI specification",
    )
    base_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Base URL for API calls",
    )

    # Transport configuration
    sse_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="SSE endpoint URL",
    )
    http_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="HTTP endpoint URL for streamable HTTP",
    )

    # Authentication
    auth_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Authentication type: api_key, bearer, basic, oauth2",
    )
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Authentication configuration (encrypted)",
    )

    # Status
    status: Mapped[MCPServerStatus] = mapped_column(
        Enum(MCPServerStatus),
        nullable=False,
        default=MCPServerStatus.ACTIVE,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    last_error_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Configuration
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional server configuration",
    )

    # MCP protocol info (populated after initialization)
    protocol_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    server_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Server information from initialize response",
    )
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Server capabilities",
    )

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship("Tenant")
    tools: Mapped[list["MCPTool"]] = relationship(
        "MCPTool",
        back_populates="server",
        cascade="all, delete-orphan",
    )

    @property
    def is_available(self) -> bool:
        """Check if server is available for use."""
        return (
            self.is_active
            and self.status == MCPServerStatus.ACTIVE
            and not self.last_error
        )
