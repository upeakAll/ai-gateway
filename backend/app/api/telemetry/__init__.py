"""Telemetry API endpoints."""

from fastapi import APIRouter

from app.api.telemetry.health import router as health_router
from app.api.telemetry.usage import router as usage_router

router = APIRouter()

router.include_router(health_router)
router.include_router(usage_router)

__all__ = ["router"]
