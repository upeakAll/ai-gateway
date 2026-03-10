"""Admin MCP server management endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.mcp.tools.openapi_gen import openapi_generator
from app.models import MCPServer, MCPServerStatus, MCPServerType, MCPTransport, MCPTool
from app.schemas import PaginatedResponse

router = APIRouter(prefix="/admin/mcp", tags=["Admin - MCP"])


class MCPServerCreate:
    """Schema for creating MCP server."""

    name: str
    display_name: str | None = None
    description: str | None = None
    server_type: str = "manual"
    transport: str = "sse"
    tenant_id: str | None = None
    openapi_url: str | None = None
    base_url: str | None = None
    sse_url: str | None = None
    http_url: str | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class MCPServerUpdate:
    """Schema for updating MCP server."""

    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None


class MCPServerResponse:
    """Schema for MCP server response."""

    id: str
    name: str
    display_name: str | None
    description: str | None
    server_type: str
    transport: str
    tenant_id: str | None
    status: str
    is_active: bool
    openapi_url: str | None
    base_url: str | None
    tool_count: int = 0


class OpenAPIGenerateRequest:
    """Schema for OpenAPI to MCP generation."""

    openapi_url: str
    base_url: str | None = None
    include_operations: list[str] | None = None
    exclude_operations: list[str] | None = None


@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    body: MCPServerCreate,
    db: DBSession,
) -> dict[str, Any]:
    """Create a new MCP server."""
    # Check if name already exists
    result = await db.execute(select(MCPServer).where(MCPServer.name == body.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MCP server '{body.name}' already exists",
        )

    server = MCPServer(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        server_type=MCPServerType(body.server_type),
        transport=MCPTransport(body.transport),
        tenant_id=body.tenant_id,
        openapi_url=body.openapi_url,
        base_url=body.base_url,
        sse_url=body.sse_url,
        http_url=body.http_url,
        auth_type=body.auth_type,
        auth_config=body.auth_config,
        config=body.config,
        status=MCPServerStatus.ACTIVE,
    )

    db.add(server)
    await db.commit()
    await db.refresh(server)

    return _server_to_response(server)


@router.get("/servers", response_model=PaginatedResponse[dict[str, Any]])
async def list_mcp_servers(
    db: DBSession,
    tenant_id: str | None = None,
    server_type: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[dict[str, Any]]:
    """List MCP servers."""
    query = select(MCPServer)

    if tenant_id:
        query = query.where(MCPServer.tenant_id == tenant_id)
    if server_type:
        query = query.where(MCPServer.server_type == MCPServerType(server_type))
    if is_active is not None:
        query = query.where(MCPServer.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(MCPServer.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    servers = result.scalars().all()

    return PaginatedResponse.create(
        items=[_server_to_response(s) for s in servers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/servers/{server_id}")
async def get_mcp_server(
    server_id: str,
    db: DBSession,
) -> dict[str, Any]:
    """Get MCP server by ID."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' not found",
        )

    return _server_to_response(server)


@router.patch("/servers/{server_id}")
async def update_mcp_server(
    server_id: str,
    body: MCPServerUpdate,
    db: DBSession,
) -> dict[str, Any]:
    """Update MCP server."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' not found",
        )

    update_data = body.__dict__
    for field, value in update_data.items():
        if value is not None and hasattr(server, field):
            setattr(server, field, value)

    await db.commit()
    await db.refresh(server)

    return _server_to_response(server)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: str,
    db: DBSession,
) -> None:
    """Delete MCP server."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' not found",
        )

    await db.delete(server)
    await db.commit()


@router.post("/servers/{server_id}/generate-from-openapi")
async def generate_tools_from_openapi(
    server_id: str,
    body: OpenAPIGenerateRequest,
    db: DBSession,
) -> dict[str, Any]:
    """Generate MCP tools from OpenAPI specification."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' not found",
        )

    try:
        # Fetch and parse OpenAPI spec
        spec = await openapi_generator.fetch_spec(body.openapi_url)

        # Generate tools
        tools = openapi_generator.generate_tools(
            spec,
            base_url=body.base_url,
            include_operations=body.include_operations,
            exclude_operations=body.exclude_operations,
        )

        # Create tool records
        created_tools = []
        for tool_data in tools:
            tool = MCPTool(
                server_id=server_id,
                name=tool_data["name"],
                display_name=tool_data.get("display_name"),
                description=tool_data.get("description", ""),
                input_schema=tool_data["input_schema"],
                openapi_operation_id=tool_data.get("openapi_operation_id"),
                openapi_path=tool_data.get("openapi_path"),
                openapi_method=tool_data.get("openapi_method"),
                execution_config=tool_data.get("execution_config"),
            )
            db.add(tool)
            created_tools.append(tool)

        # Update server with OpenAPI info
        server.openapi_url = body.openapi_url
        server.openapi_spec = spec
        if body.base_url:
            server.base_url = body.base_url

        await db.commit()

        return {
            "server_id": server_id,
            "tools_generated": len(created_tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                }
                for t in created_tools
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate tools: {str(e)}",
        )


@router.get("/servers/{server_id}/tools")
async def list_server_tools(
    server_id: str,
    db: DBSession,
) -> list[dict[str, Any]]:
    """List tools for an MCP server."""
    result = await db.execute(
        select(MCPTool).where(MCPTool.server_id == server_id)
    )
    tools = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "display_name": t.display_name,
            "description": t.description,
            "is_active": t.is_active,
            "total_invocations": t.total_invocations,
        }
        for t in tools
    ]


@router.post("/servers/{server_id}/tools", status_code=status.HTTP_201_CREATED)
async def create_mcp_tool(
    server_id: str,
    body: dict[str, Any],
    db: DBSession,
) -> dict[str, Any]:
    """Create a custom MCP tool."""
    # Verify server exists
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' not found",
        )

    tool = MCPTool(
        server_id=server_id,
        name=body.get("name"),
        display_name=body.get("display_name"),
        description=body.get("description", ""),
        input_schema=body.get("input_schema", {}),
        required_permission=body.get("required_permission"),
        allowed_roles=body.get("allowed_roles"),
        execution_config=body.get("execution_config"),
    )

    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    return {
        "id": str(tool.id),
        "name": tool.name,
        "description": tool.description,
    }


@router.delete("/servers/{server_id}/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_tool(
    server_id: str,
    tool_id: str,
    db: DBSession,
) -> None:
    """Delete an MCP tool."""
    result = await db.execute(
        select(MCPTool).where(
            MCPTool.id == tool_id,
            MCPTool.server_id == server_id,
        )
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )

    await db.delete(tool)
    await db.commit()


def _server_to_response(server: MCPServer) -> dict[str, Any]:
    """Convert server to response dict."""
    return {
        "id": str(server.id),
        "name": server.name,
        "display_name": server.display_name,
        "description": server.description,
        "server_type": server.server_type.value,
        "transport": server.transport.value,
        "tenant_id": str(server.tenant_id) if server.tenant_id else None,
        "status": server.status.value,
        "is_active": server.is_active,
        "openapi_url": server.openapi_url,
        "base_url": server.base_url,
        "created_at": str(server.created_at),
    }
