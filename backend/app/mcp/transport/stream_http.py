"""HTTP transport for MCP protocol."""

import json
from typing import Any

import httpx
import structlog

from app.config import settings
from app.core.exceptions import MCPError

logger = structlog.get_logger()


class HTTPMCPClient:
    """HTTP client for connecting to MCP servers.

    Used for connecting to remote MCP servers that expose
    HTTP endpoints.
    """

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=timeout,
                write=30.0,
                pool=10.0,
            ),
            headers={
                "Content-Type": "application/json",
                **self.headers,
            },
        )

    async def initialize(
        self,
        client_info: dict[str, Any],
        capabilities: dict[str, Any],
    ) -> dict[str, Any]:
        """Initialize connection to MCP server."""
        response = await self._send_request("initialize", {
            "clientInfo": client_info,
            "capabilities": capabilities,
            "protocolVersion": "2024-11-05",
        })

        return response.get("result", {})

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from server."""
        response = await self._send_request("tools/list", {})
        return response.get("result", {}).get("tools", [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the server."""
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        return response.get("result", {})

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources from server."""
        response = await self._send_request("resources/list", {})
        return response.get("result", {}).get("resources", [])

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource from the server."""
        response = await self._send_request("resources/read", {"uri": uri})
        return response.get("result", {})

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List available prompts from server."""
        response = await self._send_request("prompts/list", {})
        return response.get("result", {}).get("prompts", [])

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get a prompt from the server."""
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments

        response = await self._send_request("prompts/get", params)
        return response.get("result", {})

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a JSON-RPC request to the server."""
        import uuid

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            response = await self._client.post(
                f"{self.base_url}/mcp",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "mcp_http_error",
                method=method,
                status=e.response.status_code,
            )
            raise MCPError(f"HTTP error: {e.response.status_code}")

        except httpx.TimeoutException:
            logger.error("mcp_http_timeout", method=method)
            raise MCPError("Request timed out")

        except Exception as e:
            logger.error("mcp_http_error", method=method, error=str(e))
            raise MCPError(f"Request failed: {str(e)}")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
