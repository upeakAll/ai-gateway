"""MCP (Model Context Protocol) module."""

from app.mcp.server import MCPServerHandler, MCPServerManager, mcp_server_manager
from app.mcp.session import MCPSession, MCPSessionManager
from app.mcp.transport import HTTPMCPClient, SSEClient, SSETransport
from app.mcp.tools import (
    ToolRegistry,
    ToolExecutor,
    OpenAPIToolGenerator,
    openapi_generator,
    tool_executor,
    register_tool_function,
)
from app.mcp.resources import (
    Resource,
    ResourceContent,
    ResourceManager,
    ResourceProvider,
    resource_manager,
)
from app.mcp.prompts import (
    Prompt,
    PromptArgument,
    PromptManager,
    prompt_manager,
)
from app.mcp.auth import (
    Permission,
    MCPRole,
    MCPUser,
    MCPAccessControl,
    mcp_access_control,
    ToolAccessController,
    tool_access_controller,
)

__all__ = [
    # Server
    "MCPServerHandler",
    "MCPServerManager",
    "mcp_server_manager",
    # Session
    "MCPSession",
    "MCPSessionManager",
    # Transport
    "SSETransport",
    "SSEClient",
    "HTTPMCPClient",
    # Tools
    "ToolRegistry",
    "ToolExecutor",
    "OpenAPIToolGenerator",
    "openapi_generator",
    "tool_executor",
    "register_tool_function",
    # Resources
    "Resource",
    "ResourceContent",
    "ResourceManager",
    "ResourceProvider",
    "resource_manager",
    # Prompts
    "Prompt",
    "PromptArgument",
    "PromptManager",
    "prompt_manager",
    # Auth
    "Permission",
    "MCPRole",
    "MCPUser",
    "MCPAccessControl",
    "mcp_access_control",
    "ToolAccessController",
    "tool_access_controller",
]
