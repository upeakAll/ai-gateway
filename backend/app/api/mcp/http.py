"""MCP HTTP endpoint for Streamable HTTP transport."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.mcp import mcp_server_manager
from app.mcp.transport import StreamableHTTPTransport
from app.models import MCPServer, MCPServerStatus

router = APIRouter(prefix="/mcp", tags=["MCP HTTP"])
logger = structlog.get_logger()

# HTTP transports
_http_transports: dict[str, StreamableHTTPTransport] = {}


@router.post("/{server_name}")
async def mcp_http_endpoint(
    server_name: str,
    request: Request,
    db: DBSession = None,
) -> JSONResponse:
    """MCP HTTP endpoint for request/response communication.

    Supports the Streamable HTTP transport mode.
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

    # Parse JSON-RPC request
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Validate JSON-RPC format
    if body.get("jsonrpc") != "2.0":
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC version")

    method = body.get("method")
    params = body.get("params", {})
    request_id = body.get("id")

    if not method:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32600, "message": "Missing method"},
        })

    # Handle request
    response = await mcp_server_manager.handle_sse_request(
        server=server,
        method=method,
        params=params,
        session_id=request.headers.get("X-Session-ID"),
    )

    # Add request ID to response
    if request_id:
        response["id"] = request_id

    return JSONResponse(content=response)


@router.post("/{server_name}/batch")
async def mcp_batch_endpoint(
    server_name: str,
    request: Request,
    db: DBSession = None,
) -> JSONResponse:
    """Handle batch MCP requests.

    Accepts an array of requests and returns an array of responses.
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

    # Parse batch request
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, list):
        raise HTTPException(status_code=400, detail="Batch request must be an array")

    # Process each request
    responses = []
    session_id = request.headers.get("X-Session-ID")

    for item in body:
        method = item.get("method")
        params = item.get("params", {})
        request_id = item.get("id")

        if not method:
            responses.append({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32600, "message": "Missing method"},
            })
            continue

        response = await mcp_server_manager.handle_sse_request(
            server=server,
            method=method,
            params=params,
            session_id=session_id,
        )

        if request_id:
            response["id"] = request_id

        responses.append(response)

    return JSONResponse(content=responses)
