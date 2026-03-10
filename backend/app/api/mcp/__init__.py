"""MCP API endpoints."""

from fastapi import APIRouter

from app.api.mcp.sse import router as sse_router
from app.api.mcp.http import router as http_router

router = APIRouter()

router.include_router(sse_router)
router.include_router(http_router)

__all__ = ["router"]
