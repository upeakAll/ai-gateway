"""Admin API endpoints."""

from fastapi import APIRouter

from app.api.admin.tenants import router as tenants_router
from app.api.admin.api_keys import router as keys_router
from app.api.admin.channels import router as channels_router
from app.api.admin.mcp import router as mcp_router

router = APIRouter()

router.include_router(tenants_router)
router.include_router(keys_router)
router.include_router(channels_router)
router.include_router(mcp_router)

__all__ = ["router"]
