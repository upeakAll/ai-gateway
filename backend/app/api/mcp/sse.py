"""MCP SSE endpoint for Server-Sent Events transport."""

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.core.exceptions import MCPServerNotFoundError
from app.mcp import mcp_server_manager
from app.mcp.transport import SSETransport
from app.models import MCPServer, MCPServerStatus

router = APIRouter(prefix="/mcp", tags=["MCP"])
logger = structlog.get_logger()

# SSE transports per server
_sse_transports: dict[str, SSETransport] = {}


@router.get("/{server_name}/sse")
async def mcp_sse_endpoint(
    server_name: str,
    request: Request,
    session_id: str | None = Query(None, description="Optional session ID"),
    db: DBSession = None,
):
    """MCP SSE endpoint for streaming communication.

    This endpoint establishes a Server-Sent Events connection for
    bidirectional MCP communication.
    """
    # Find the MCP server
    result = await db.execute(
        select(MCPServer).where(
            MCPServer.name == server_name,
            MCPServer.is_active == True,  # type: ignore
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_name}' not found",
        )

    if server.status != MCPServerStatus.ACTIVE:
        raise HTTPException(
            status_code=503,
            detail=f"MCP server '{server_name}' is not active",
        )

    # Get or create transport
    server_id = str(server.id)

    if server_id not in _sse_transports:
        transport = SSETransport()
        _sse_transports[server_id] = transport
        mcp_server_manager.register_transport(server_id, transport)
    else:
        transport = _sse_transports[server_id]

    # Generate session ID if not provided
    import uuid
    actual_session_id = session_id or str(uuid.uuid4())

    # Return SSE response
    return transport.create_response(actual_session_id)


@router.post("/{server_name}/request")
async def mcp_request_endpoint(
    server_name: str,
    request: Request,
    db: DBSession = None,
) -> JSONResponse:
    """Handle MCP request via HTTP POST.

    This is a companion endpoint for SSE that handles
    client-to-server requests.
    """
    # Find the MCP server
    result = await db.execute(
        select(MCPServer).where(
            MCPServer.name == server_name,
            MCPServer.is_active == True,  # type: ignore
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_name}' not found",
        )

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    method = body.get("method")
    params = body.get("params", {})
    session_id = request.headers.get("X-Session-ID")

    if not method:
        raise HTTPException(status_code=400, detail="Missing method")

    # Handle request through server manager
    response = await mcp_server_manager.handle_sse_request(
        server=server,
        method=method,
        params=params,
        session_id=session_id,
    )

    return JSONResponse(content=response)


@router.post("/{server_name}/initialize")
async def mcp_initialize(
    server_name: str,
    request: Request,
    db: DBSession = None,
) -> JSONResponse:
    """Initialize MCP connection."""
    # Find the MCP server
    result = await db.execute(
        select(MCPServer).where(MCPServer.name == server_name)
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_name}' not found",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    response = await mcp_server_manager.handle_sse_request(
        server=server,
        method="initialize",
        params=body,
        session_id=request.headers.get("X-Session-ID"),
    )

    return JSONResponse(content=response)


@router.get("/{server_name}/tools")
async def list_mcp_tools(
    server_name: str,
    db: DBSession = None,
) -> dict[str, Any]:
    """List available tools for an MCP server."""
    # Find the MCP server
    result = await db.execute(
        select(MCPServer).where(
            MCPServer.name == server_name,
            MCPServer.is_active == True,  # type: ignore
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_name}' not found",
        )

    response = await mcp_server_manager.handle_sse_request(
        server=server,
        method="tools/list",
        params={},
    )

    if "result" in response:
        return response["result"]

    raise HTTPException(
        status_code=500,
        detail=response.get("error", {}).get("message", "Failed to list tools"),
    )


@router.post("/{server_name}/tools/call")
async def call_mcp_tool(
    server_name: str,
    request: Request,
    db: DBSession = None,
) -> dict[str, Any]:
    """Call an MCP tool."""
    # Find the MCP server
    result = await db.execute(
        select(MCPServer).where(
            MCPServer.name == server_name,
            MCPServer.is_active == True,  # type: ignore
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_name}' not found",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    tool_name = body.get("name")
    arguments = body.get("arguments", {})

    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing tool name")

    response = await mcp_server_manager.handle_sse_request(
        server=server,
        method="tools/call",
        params={
            "name": tool_name,
            "arguments": arguments,
        },
        session_id=request.headers.get("X-Session-ID"),
    )

    if "result" in response:
        return response["result"]

    raise HTTPException(
        status_code=500,
        detail=response.get("error", {}).get("message", "Tool execution failed"),
    )
