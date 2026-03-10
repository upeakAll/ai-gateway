"""MCP (Model Context Protocol) server implementation."""

import asyncio
import json
from typing import Any, Callable

import structlog

from app.core.exceptions import MCPServerNotFoundError
from app.mcp.session import MCPSessionManager
from app.mcp.tools.registry import ToolRegistry
from app.mcp.transport.sse import SSETransport
from app.models import MCPServer, MCPServerStatus

logger = structlog.get_logger()

# MCP Protocol Version
MCP_VERSION = "2024-11-05"


class MCPServerHandler:
    """Handler for MCP protocol requests.

    Implements the Model Context Protocol (MCP) specification
    for tool, resource, and prompt management.
    """

    def __init__(
        self,
        server: MCPServer,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.server = server
        self.tool_registry = tool_registry or ToolRegistry()
        self.session_manager = MCPSessionManager()
        self._capabilities: dict[str, Any] = {
            "tools": {"listChanged": True},
            "resources": {"subscribe": True, "listChanged": True},
            "prompts": {"listChanged": True},
        }
        self._server_info: dict[str, Any] = {
            "name": server.display_name or server.name,
            "version": "1.0.0",
        }

    async def handle_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle an MCP request.

        Args:
            method: MCP method name
            params: Request parameters
            session_id: Optional session identifier

        Returns:
            Response dict
        """
        params = params or {}
        handlers: dict[str, Callable[..., Any]] = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
        }

        handler = handlers.get(method)
        if not handler:
            return self._error_response(
                -32601,
                f"Method not found: {method}",
            )

        try:
            result = await handler(params, session_id)
            return {"jsonrpc": "2.0", "result": result}
        except Exception as e:
            logger.error(
                "mcp_request_error",
                server=self.server.name,
                method=method,
                error=str(e),
            )
            return self._error_response(-32603, str(e))

    async def _handle_initialize(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        client_capabilities = params.get("capabilities", {})

        # Create session
        if session_id:
            session = self.session_manager.create_session(
                session_id,
                client_info,
                client_capabilities,
            )

        logger.info(
            "mcp_initialize",
            server=self.server.name,
            client_info=client_info,
        )

        return {
            "protocolVersion": MCP_VERSION,
            "capabilities": self._capabilities,
            "serverInfo": self._server_info,
        }

    async def _handle_ping(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle ping request."""
        return {}

    async def _handle_tools_list(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle tools/list request."""
        tools = await self.tool_registry.list_tools(str(self.server.id))

        return {
            "tools": [
                tool.to_mcp_format()
                for tool in tools
            ],
        }

    async def _handle_tools_call(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return self._error_response(-32602, "Missing tool name")

        result = await self.tool_registry.execute_tool(
            str(self.server.id),
            tool_name,
            arguments,
            session_id=session_id,
        )

        return {
            "content": result.get("content", []),
            "isError": result.get("isError", False),
        }

    async def _handle_resources_list(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle resources/list request."""
        # TODO: Implement resources
        return {"resources": []}

    async def _handle_resources_read(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        if not uri:
            return self._error_response(-32602, "Missing resource URI")

        # TODO: Implement resources
        return {"contents": []}

    async def _handle_prompts_list(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle prompts/list request."""
        # TODO: Implement prompts
        return {"prompts": []}

    async def _handle_prompts_get(
        self,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name")
        if not name:
            return self._error_response(-32602, "Missing prompt name")

        # TODO: Implement prompts
        return {"messages": []}

    def _error_response(self, code: int, message: str) -> dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message,
            },
        }


class MCPServerManager:
    """Manager for multiple MCP servers."""

    def __init__(self) -> None:
        self._handlers: dict[str, MCPServerHandler] = {}
        self._transports: dict[str, SSETransport] = {}

    async def get_handler(self, server: MCPServer) -> MCPServerHandler:
        """Get or create handler for a server."""
        server_id = str(server.id)

        if server_id not in self._handlers:
            handler = MCPServerHandler(server)
            # Load tools for this server
            await handler.tool_registry.load_server_tools(server_id)
            self._handlers[server_id] = handler

        return self._handlers[server_id]

    async def handle_sse_request(
        self,
        server: MCPServer,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle an SSE-based MCP request."""
        handler = await self.get_handler(server)
        return await handler.handle_request(method, params, session_id)

    async def broadcast_tool_list_changed(self, server_id: str) -> None:
        """Broadcast tool list changed notification."""
        if server_id in self._transports:
            transport = self._transports[server_id]
            await transport.broadcast(
                "notifications/tools/list_changed",
                {},
            )

    def register_transport(self, server_id: str, transport: SSETransport) -> None:
        """Register a transport for a server."""
        self._transports[server_id] = transport

    def unregister_transport(self, server_id: str) -> None:
        """Unregister a transport."""
        self._transports.pop(server_id, None)


# Global MCP server manager
mcp_server_manager = MCPServerManager()
