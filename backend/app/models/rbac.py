"""RBAC (Role-Based Access Control) models."""

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class RoleType(StrEnum):
    """Predefined role types."""

    SUPER_ADMIN = "super_admin"  # Full system access
    TENANT_ADMIN = "tenant_admin"  # Tenant administrator
    DEVELOPER = "developer"  # API access with full features
    VIEWER = "viewer"  # Read-only access


class Role(BaseModel):
    """Role definition for RBAC."""

    __tablename__ = "roles"

    # Basic info
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Role type
    role_type: Mapped[RoleType] = mapped_column(
        nullable=False,
        default=RoleType.VIEWER,
    )

    # Is this a system role (cannot be deleted)?
    is_system: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    # Permissions (list of permission strings)
    permissions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(BaseModel):
    """Permission definition."""

    __tablename__ = "permissions"

    # Permission identification
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Permission grouping
    resource: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Resource this permission applies to (e.g., 'api_keys', 'channels')",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action (e.g., 'create', 'read', 'update', 'delete', 'list')",
    )

    @property
    def full_name(self) -> str:
        """Get full permission name (resource:action)."""
        return f"{self.resource}:{self.action}"


class UserRole(BaseModel):
    """User-Role association for RBAC."""

    __tablename__ = "user_roles"

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Tenant scope for the role (NULL for system-wide roles)",
    )

    # Additional scope constraints
    scope: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional scope constraints",
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    tenant: Mapped["Tenant | None"] = relationship("Tenant")


class User(BaseModel):
    """User for admin access (separate from API keys)."""

    __tablename__ = "users"

    # Basic info
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Profile
    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    # OAuth info
    oauth_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    oauth_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Metadata
    last_login_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        backref="user",
        cascade="all, delete-orphan",
    )


# Predefined permissions
DEFAULT_PERMISSIONS: list[dict[str, str]] = [
    # API Keys
    {"name": "api_keys:create", "display_name": "Create API Keys", "resource": "api_keys", "action": "create"},
    {"name": "api_keys:read", "display_name": "Read API Keys", "resource": "api_keys", "action": "read"},
    {"name": "api_keys:update", "display_name": "Update API Keys", "resource": "api_keys", "action": "update"},
    {"name": "api_keys:delete", "display_name": "Delete API Keys", "resource": "api_keys", "action": "delete"},
    {"name": "api_keys:list", "display_name": "List API Keys", "resource": "api_keys", "action": "list"},
    # Channels
    {"name": "channels:create", "display_name": "Create Channels", "resource": "channels", "action": "create"},
    {"name": "channels:read", "display_name": "Read Channels", "resource": "channels", "action": "read"},
    {"name": "channels:update", "display_name": "Update Channels", "resource": "channels", "action": "update"},
    {"name": "channels:delete", "display_name": "Delete Channels", "resource": "channels", "action": "delete"},
    {"name": "channels:list", "display_name": "List Channels", "resource": "channels", "action": "list"},
    # Tenants
    {"name": "tenants:create", "display_name": "Create Tenants", "resource": "tenants", "action": "create"},
    {"name": "tenants:read", "display_name": "Read Tenants", "resource": "tenants", "action": "read"},
    {"name": "tenants:update", "display_name": "Update Tenants", "resource": "tenants", "action": "update"},
    {"name": "tenants:delete", "display_name": "Delete Tenants", "resource": "tenants", "action": "delete"},
    {"name": "tenants:list", "display_name": "List Tenants", "resource": "tenants", "action": "list"},
    # Usage/Logs
    {"name": "usage:read", "display_name": "Read Usage", "resource": "usage", "action": "read"},
    {"name": "usage:list", "display_name": "List Usage", "resource": "usage", "action": "list"},
    {"name": "usage:export", "display_name": "Export Usage", "resource": "usage", "action": "export"},
    # MCP
    {"name": "mcp:create", "display_name": "Create MCP Servers", "resource": "mcp", "action": "create"},
    {"name": "mcp:read", "display_name": "Read MCP Servers", "resource": "mcp", "action": "read"},
    {"name": "mcp:update", "display_name": "Update MCP Servers", "resource": "mcp", "action": "update"},
    {"name": "mcp:delete", "display_name": "Delete MCP Servers", "resource": "mcp", "action": "delete"},
    {"name": "mcp:list", "display_name": "List MCP Servers", "resource": "mcp", "action": "list"},
    {"name": "mcp:execute", "display_name": "Execute MCP Tools", "resource": "mcp", "action": "execute"},
]
