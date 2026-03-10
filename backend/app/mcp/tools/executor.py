"""MCP tool executor for running tool functions."""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Callable

import httpx
import structlog

from app.config import settings
from app.core.exceptions import MCPToolExecutionError
from app.models import MCPTool

logger = structlog.get_logger()


class ToolExecutor(ABC):
    """Abstract base class for tool executors."""

    @abstractmethod
    async def execute(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the tool with given arguments."""
        pass


class OpenAPIToolExecutor(ToolExecutor):
    """Executor for OpenAPI-based tools.

    Executes HTTP requests based on OpenAPI operation definitions.
    """

    def __init__(
        self,
        base_url: str,
        default_headers: dict[str, str] | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.auth_token = auth_token

    async def execute(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an OpenAPI-based tool."""
        if not tool.openapi_path or not tool.openapi_method:
            raise MCPToolExecutionError(tool.name, "Tool has no OpenAPI configuration")

        method = tool.openapi_method.upper()
        path = tool.openapi_path
        config = tool.execution_config or {}

        # Apply path parameters
        for key, value in list(arguments.items()):
            if f"{{{key}}}" in path:
                path = path.replace(f"{{{key}}}", str(value))
                # Remove from arguments to avoid sending in body/query
                if key in arguments:
                    del arguments[key]

        # Build headers
        headers = {**self.default_headers}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if config.get("headers"):
            headers.update(config["headers"])

        # Build URL
        url = f"{self.base_url}{path}"

        timeout = config.get("timeout", settings.request_timeout_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(url, params=arguments, headers=headers)
                elif method == "POST":
                    response = await client.post(url, json=arguments, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, json=arguments, headers=headers)
                elif method == "PATCH":
                    response = await client.patch(url, json=arguments, headers=headers)
                elif method == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    raise MCPToolExecutionError(
                        tool.name, f"Unsupported method: {method}"
                    )

            return self._format_response(response)

        except httpx.TimeoutException:
            raise MCPToolExecutionError(tool.name, "Request timed out")
        except httpx.HTTPError as e:
            raise MCPToolExecutionError(tool.name, f"HTTP error: {str(e)}")

    def _format_response(self, response: httpx.Response) -> dict[str, Any]:
        """Format HTTP response as MCP tool result."""
        is_error = response.status_code >= 400

        try:
            content = response.json()
            text = json.dumps(content, indent=2)
        except Exception:
            text = response.text
            content = response.text

        return {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
            "_metadata": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
            },
        }


class PythonFunctionExecutor(ToolExecutor):
    """Executor for Python function-based tools.

    Executes registered Python functions as tools.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Any]] = {}

    def register_function(
        self,
        name: str,
        func: Callable[..., Any],
    ) -> None:
        """Register a Python function as a tool."""
        self._functions[name] = func

    def unregister_function(self, name: str) -> None:
        """Unregister a function."""
        self._functions.pop(name, None)

    async def execute(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a Python function tool."""
        func = self._functions.get(tool.name)
        if not func:
            raise MCPToolExecutionError(
                tool.name, "Function not registered"
            )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)

            return self._format_result(result)

        except Exception as e:
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }

    def _format_result(self, result: Any) -> dict[str, Any]:
        """Format function result as MCP tool result."""
        if isinstance(result, dict):
            if "content" in result:
                return result
            text = json.dumps(result, indent=2, default=str)
        elif isinstance(result, str):
            text = result
        else:
            text = str(result)

        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }


class CompositeExecutor(ToolExecutor):
    """Composite executor that selects based on tool type."""

    def __init__(self) -> None:
        self.openapi_executor = OpenAPIToolExecutor("")
        self.function_executor = PythonFunctionExecutor()
        self._server_base_urls: dict[str, str] = {}

    def set_server_base_url(self, server_id: str, base_url: str) -> None:
        """Set base URL for a server's OpenAPI tools."""
        self._server_base_urls[server_id] = base_url

    def register_function(self, name: str, func: Callable[..., Any]) -> None:
        """Register a Python function."""
        self.function_executor.register_function(name, func)

    async def execute(
        self,
        tool: MCPTool,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute using appropriate executor based on tool type."""
        # Check if it's a registered function
        if tool.name in self.function_executor._functions:
            return await self.function_executor.execute(tool, arguments, **kwargs)

        # Use OpenAPI executor
        if tool.openapi_path:
            server_id = str(tool.server_id)
            base_url = self._server_base_urls.get(server_id, "")

            if not base_url:
                config = tool.execution_config or {}
                base_url = config.get("base_url", "")

            self.openapi_executor.base_url = base_url
            return await self.openapi_executor.execute(tool, arguments, **kwargs)

        raise MCPToolExecutionError(tool.name, "No executor available for this tool")


# Global executor instance
tool_executor = CompositeExecutor()


def register_tool_function(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a Python function as an MCP tool.

    Usage:
        @register_tool_function("get_weather")
        async def get_weather(city: str) -> dict:
            return {"temperature": 20, "condition": "sunny"}
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        tool_executor.register_function(name, func)
        return func
    return decorator
