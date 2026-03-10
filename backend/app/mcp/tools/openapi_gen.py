"""OpenAPI to MCP tool generator.

Converts OpenAPI specifications to MCP tool definitions.
"""

import json
from typing import Any

import httpx
import structlog

from app.core.exceptions import MCPError

logger = structlog.get_logger()


class OpenAPIToolGenerator:
    """Generator that creates MCP tools from OpenAPI specifications."""

    def __init__(self) -> None:
        self._supported_methods = {"get", "post", "put", "patch", "delete"}

    async def fetch_spec(self, url: str) -> dict[str, Any]:
        """Fetch OpenAPI specification from URL."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if "json" in content_type:
                    return response.json()
                elif "yaml" in content_type or "yml" in content_type:
                    import yaml
                    return yaml.safe_load(response.text)
                else:
                    # Try JSON first, then YAML
                    try:
                        return response.json()
                    except Exception:
                        import yaml
                        return yaml.safe_load(response.text)

        except Exception as e:
            logger.error("openapi_fetch_error", url=url, error=str(e))
            raise MCPError(f"Failed to fetch OpenAPI spec: {str(e)}")

    def generate_tools(
        self,
        spec: dict[str, Any],
        base_url: str | None = None,
        include_operations: list[str] | None = None,
        exclude_operations: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate MCP tool definitions from OpenAPI spec.

        Args:
            spec: OpenAPI specification dict
            base_url: Override base URL for API calls
            include_operations: Only include these operation IDs
            exclude_operations: Exclude these operation IDs

        Returns:
            List of tool definition dicts
        """
        tools = []
        paths = spec.get("paths", {})

        # Get base URL from spec if not provided
        if not base_url:
            servers = spec.get("servers", [])
            if servers:
                base_url = servers[0].get("url", "")

        for path, path_item in paths.items():
            for method in self._supported_methods:
                if method not in path_item:
                    continue

                operation = path_item[method]
                operation_id = operation.get("operationId")

                # Skip if no operation ID
                if not operation_id:
                    operation_id = f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", "")

                # Apply filters
                if include_operations and operation_id not in include_operations:
                    continue
                if exclude_operations and operation_id in exclude_operations:
                    continue

                tool = self._create_tool_from_operation(
                    operation_id=operation_id,
                    path=path,
                    method=method,
                    operation=operation,
                    base_url=base_url,
                )

                tools.append(tool)

        return tools

    def _create_tool_from_operation(
        self,
        operation_id: str,
        path: str,
        method: str,
        operation: dict[str, Any],
        base_url: str | None,
    ) -> dict[str, Any]:
        """Create an MCP tool definition from an OpenAPI operation."""
        # Get description
        description = operation.get("description") or operation.get("summary", "")

        # Build input schema
        input_schema = self._build_input_schema(operation, path)

        # Build execution config
        execution_config = {
            "base_url": base_url,
            "timeout": 30,
        }

        # Extract security requirements
        security = operation.get("security", [])
        if security:
            execution_config["security"] = security

        return {
            "name": self._sanitize_name(operation_id),
            "display_name": operation.get("summary", operation_id),
            "description": description,
            "input_schema": input_schema,
            "openapi_operation_id": operation_id,
            "openapi_path": path,
            "openapi_method": method.upper(),
            "execution_config": execution_config,
        }

    def _build_input_schema(
        self,
        operation: dict[str, Any],
        path: str,
    ) -> dict[str, Any]:
        """Build JSON Schema for tool input from OpenAPI parameters."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Path parameters
        path_params = operation.get("parameters", [])
        for param in path_params:
            if param.get("in") == "path":
                name = param.get("name")
                properties[name] = self._param_to_schema(param)
                if param.get("required"):
                    required.append(name)

        # Query parameters
        for param in path_params:
            if param.get("in") == "query":
                name = param.get("name")
                properties[name] = self._param_to_schema(param)
                if param.get("required"):
                    required.append(name)

        # Header parameters (selective)
        for param in path_params:
            if param.get("in") == "header":
                name = param.get("name")
                # Only include custom headers, not standard ones
                if name.lower() not in ("authorization", "content-type", "accept"):
                    properties[name] = self._param_to_schema(param)

        # Request body
        request_body = operation.get("requestBody")
        if request_body:
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})

            if schema.get("type") == "object":
                # Merge body properties
                body_props = schema.get("properties", {})
                for name, prop in body_props.items():
                    properties[name] = prop

                if request_body.get("required"):
                    required.extend(schema.get("required", []))
            else:
                # Single body parameter
                properties["body"] = {
                    "type": "object",
                    "description": request_body.get("description", "Request body"),
                }

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": True,
        }

    def _param_to_schema(self, param: dict[str, Any]) -> dict[str, Any]:
        """Convert OpenAPI parameter to JSON Schema."""
        schema = param.get("schema", {"type": "string"})

        result: dict[str, Any] = {
            "type": schema.get("type", "string"),
            "description": param.get("description", ""),
        }

        if schema.get("enum"):
            result["enum"] = schema["enum"]

        if schema.get("default"):
            result["default"] = schema["default"]

        if schema.get("format"):
            result["format"] = schema["format"]

        if schema.get("minimum") is not None:
            result["minimum"] = schema["minimum"]

        if schema.get("maximum") is not None:
            result["maximum"] = schema["maximum"]

        return result

    def _sanitize_name(self, name: str) -> str:
        """Sanitize operation ID to valid tool name."""
        # Replace spaces and special chars with underscores
        sanitized = name.lower()
        sanitized = sanitized.replace(" ", "_")
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in sanitized)
        # Remove leading numbers
        while sanitized and sanitized[0].isdigit():
            sanitized = sanitized[1:]
        return sanitized


# Global generator
openapi_generator = OpenAPIToolGenerator()
