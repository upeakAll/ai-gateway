"""MCP tool registry for managing and discovering tools."""

import json
from typing import Any, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MCPToolNotFoundError, MCPToolExecutionError
from app.models import MCPTool, ToolStatus

logger = structlog.get_logger()


class ToolRegistry:
    """Registry for MCP tools.

    Manages tool registration, discovery, and execution.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self._tools: dict[str, dict[str, MCPTool]] = {}  # server_id -> tool_name -> tool
        self._executors: dict[str, Callable[..., Any]] = {}  # tool_id -> executor
        self._db = db

    async def load_server_tools(self, server_id: str) -> list[MCPTool]:
        """Load tools for a server from database."""
        if not self._db:
            return []

        result = await self._db.execute(
            select(MCPTool).where(
                MCPTool.server_id == server_id,
                MCPTool.is_active == True,  # type: ignore
            )
        )
        tools = list(result.scalars().all())

        if server_id not in self._tools:
            self._tools[server_id] = {}

        for tool in tools:
            self._tools[server_id][tool.name] = tool

        return tools

    def register_tool(
        self,
        server_id: str,
        tool: MCPTool,
        executor: Callable[..., Any] | None = None,
    ) -> None:
        """Register a tool with optional executor."""
        if server_id not in self._tools:
            self._tools[server_id] = {}

        self._tools[server_id][tool.name] = tool

        if executor:
            self._executors[str(tool.id)] = executor

    def unregister_tool(self, server_id: str, tool_name: str) -> None:
        """Unregister a tool."""
        if server_id in self._tools:
            self._tools[server_id].pop(tool_name, None)

    async def list_tools(self, server_id: str) -> list[MCPTool]:
        """List all tools for a server."""
        if server_id not in self._tools:
            await self.load_server_tools(server_id)

        return list(self._tools.get(server_id, {}).values())

    def get_tool(self, server_id: str, tool_name: str) -> MCPTool | None:
        """Get a specific tool."""
        return self._tools.get(server_id, {}).get(tool_name)

    async def execute_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a tool.

        Args:
            server_id: Server ID
            tool_name: Tool name
            arguments: Tool arguments
            session_id: Optional session ID

        Returns:
            Tool execution result

        Raises:
            MCPToolNotFoundError: If tool not found
            MCPToolExecutionError: If execution fails
        """
        # Load tools if not cached
        if server_id not in self._tools:
            await self.load_server_tools(server_id)

        tool = self.get_tool(server_id, tool_name)
        if not tool:
            raise MCPToolNotFoundError(tool_name)

        if not tool.is_available:
            raise MCPToolExecutionError(tool_name, "Tool is not available")

        # Validate arguments against schema
        validation_error = self._validate_arguments(tool, arguments)
        if validation_error:
            raise MCPToolExecutionError(tool_name, validation_error)

        try:
            # Get executor
            tool_id = str(tool.id)
            executor = self._executors.get(tool_id)

            if executor:
                result = await executor(arguments, session_id=session_id)
            else:
                # Default execution for OpenAPI-based tools
                result = await self._execute_openapi_tool(tool, arguments)

            # Record successful invocation
            tool.record_invocation(success=True)
            if self._db:
                self._db.add(tool)

            return result

        except (MCPToolNotFoundError, MCPToolExecutionError):
            raise

        except Exception as e:
            # Record failed invocation
            tool.record_invocation(success=False)
            if self._db:
                self._db.add(tool)

            logger.error(
                "mcp_tool_execution_error",
                server_id=server_id,
                tool_name=tool_name,
                error=str(e),
            )

            raise MCPToolExecutionError(tool_name, str(e))

    def _validate_arguments(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
    ) -> str | None:
        """Validate arguments against tool schema.

        Returns:
            Error message if validation fails, None otherwise
        """
        schema = tool.input_schema
        if not schema:
            return None

        # Check required properties
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for prop in required:
            if prop not in arguments:
                return f"Missing required argument: {prop}"

        # Check for unknown properties
        if properties:
            for key in arguments:
                if key not in properties:
                    extra = schema.get("additionalProperties", True)
                    if extra is False:
                        return f"Unknown argument: {key}"

        # Basic type checking
        for key, value in arguments.items():
            prop_schema = properties.get(key, {})
            prop_type = prop_schema.get("type")

            if prop_type:
                type_valid = self._check_type(value, prop_type)
                if not type_valid:
                    return f"Invalid type for {key}: expected {prop_type}"

        return None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON Schema type."""
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        expected_python_type = type_mapping.get(expected_type)
        if expected_python_type is None:
            return True  # Unknown type, skip validation

        return isinstance(value, expected_python_type)

    async def _execute_openapi_tool(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an OpenAPI-based tool."""
        import httpx

        if not tool.openapi_path or not tool.openapi_method:
            raise MCPToolExecutionError(
                tool.name,
                "Tool is not configured for execution",
            )

        # Get execution config
        config = tool.execution_config or {}
        base_url = config.get("base_url", "")
        headers = config.get("headers", {})
        timeout = config.get("timeout", 30)

        # Build URL with path parameters
        url = tool.openapi_path
        for key, value in arguments.items():
            url = url.replace(f"{{{key}}}", str(value))

        # Build request
        method = tool.openapi_method.upper()

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(
                    f"{base_url}{url}",
                    params=arguments,
                    headers=headers,
                )
            elif method == "POST":
                response = await client.post(
                    f"{base_url}{url}",
                    json=arguments,
                    headers=headers,
                )
            elif method == "PUT":
                response = await client.put(
                    f"{base_url}{url}",
                    json=arguments,
                    headers=headers,
                )
            elif method == "DELETE":
                response = await client.delete(
                    f"{base_url}{url}",
                    headers=headers,
                )
            else:
                raise MCPToolExecutionError(
                    tool.name,
                    f"Unsupported HTTP method: {method}",
                )

        # Format response
        try:
            content = response.json()
        except Exception:
            content = response.text

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(content) if isinstance(content, (dict, list)) else str(content),
                }
            ],
            "isError": response.status_code >= 400,
        }
