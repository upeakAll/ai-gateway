"""MCP RBAC (Role-Based Access Control) implementation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class Permission(str, Enum):
    """MCP permissions."""

    # Tool permissions
    TOOLS_LIST = "tools:list"
    TOOLS_CALL = "tools:call"
    TOOLS_MANAGE = "tools:manage"

    # Resource permissions
    RESOURCES_LIST = "resources:list"
    RESOURCES_READ = "resources:read"
    RESOURCES_SUBSCRIBE = "resources:subscribe"

    # Prompt permissions
    PROMPTS_LIST = "prompts:list"
    PROMPTS_GET = "prompts:get"
    PROMPTS_MANAGE = "prompts:manage"

    # Server permissions
    SERVER_MANAGE = "server:manage"
    SERVER_CONFIGURE = "server:configure"


@dataclass
class MCPRole:
    """Role for MCP access control."""

    name: str
    description: str | None = None
    permissions: set[Permission] = field(default_factory=set)

    def has_permission(self, permission: Permission) -> bool:
        """Check if role has a permission."""
        return permission in self.permissions


# Predefined roles
DEFAULT_ROLES: dict[str, MCPRole] = {
    "admin": MCPRole(
        name="admin",
        description="Full access to all MCP features",
        permissions=set(Permission),
    ),
    "developer": MCPRole(
        name="developer",
        description="Can use tools and resources",
        permissions={
            Permission.TOOLS_LIST,
            Permission.TOOLS_CALL,
            Permission.RESOURCES_LIST,
            Permission.RESOURCES_READ,
            Permission.RESOURCES_SUBSCRIBE,
            Permission.PROMPTS_LIST,
            Permission.PROMPTS_GET,
        },
    ),
    "viewer": MCPRole(
        name="viewer",
        description="Read-only access",
        permissions={
            Permission.TOOLS_LIST,
            Permission.RESOURCES_LIST,
            Permission.PROMPTS_LIST,
        },
    ),
    "tool_user": MCPRole(
        name="tool_user",
        description="Can only use tools",
        permissions={
            Permission.TOOLS_LIST,
            Permission.TOOLS_CALL,
        },
    ),
}


@dataclass
class MCPUser:
    """User context for MCP access control."""

    user_id: str
    roles: set[str] = field(default_factory=set)
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a permission through any of their roles."""
        for role_name in self.roles:
            role = DEFAULT_ROLES.get(role_name)
            if role and role.has_permission(permission):
                return True
        return False

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return role_name in self.roles


class MCPAccessControl:
    """Access control for MCP operations."""

    def __init__(self) -> None:
        self._custom_roles: dict[str, MCPRole] = {}
        self._tool_permissions: dict[str, set[Permission]] = {}  # tool_name -> required permissions

    def register_role(self, role: MCPRole) -> None:
        """Register a custom role."""
        self._custom_roles[role.name] = role

    def set_tool_permission(self, tool_name: str, permission: Permission) -> None:
        """Set required permission for a tool."""
        if tool_name not in self._tool_permissions:
            self._tool_permissions[tool_name] = set()
        self._tool_permissions[tool_name].add(permission)

    def check_permission(self, user: MCPUser, permission: Permission) -> bool:
        """Check if user has a permission."""
        return user.has_permission(permission)

    def check_tool_access(
        self,
        user: MCPUser,
        tool_name: str,
        allowed_roles: list[str] | None = None,
        allowed_tenant_ids: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Check if user can access a tool.

        Args:
            user: User context
            tool_name: Tool name
            allowed_roles: List of roles that can access (None = all)
            allowed_tenant_ids: List of tenant IDs that can access (None = all)

        Returns:
            Tuple of (allowed, reason)
        """
        # Check tenant restriction
        if allowed_tenant_ids is not None:
            if user.tenant_id is None:
                return False, "No tenant context"
            if user.tenant_id not in allowed_tenant_ids:
                return False, "Tool not available for your tenant"

        # Check role restriction
        if allowed_roles is not None:
            if not any(user.has_role(role) for role in allowed_roles):
                return False, "Insufficient role permissions"

        # Check tool-specific permissions
        required_permissions = self._tool_permissions.get(tool_name)
        if required_permissions:
            for perm in required_permissions:
                if not user.has_permission(perm):
                    return False, f"Missing permission: {perm.value}"

        return True, ""

    def check_resource_access(
        self,
        user: MCPUser,
        uri: str,
        permission: Permission = Permission.RESOURCES_READ,
    ) -> tuple[bool, str]:
        """Check if user can access a resource."""
        if not user.has_permission(permission):
            return False, f"Missing permission: {permission.value}"
        return True, ""

    def get_user_permissions(self, user: MCPUser) -> set[Permission]:
        """Get all permissions for a user."""
        permissions: set[Permission] = set()

        for role_name in user.roles:
            # Check default roles
            if role_name in DEFAULT_ROLES:
                permissions.update(DEFAULT_ROLES[role_name].permissions)
            # Check custom roles
            elif role_name in self._custom_roles:
                permissions.update(self._custom_roles[role_name].permissions)

        return permissions


# Global access control
mcp_access_control = MCPAccessControl()
