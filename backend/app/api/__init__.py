"""API endpoints package."""

from fastapi import APIRouter

from app.api.openai import router as openai_router
from app.api.telemetry import router as telemetry_router
from app.api.admin import router as admin_router
from app.api.mcp import router as mcp_router

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(openai_router)
api_router.include_router(telemetry_router)
api_router.include_router(admin_router)
api_router.include_router(mcp_router)

__all__ = ["api_router"]
