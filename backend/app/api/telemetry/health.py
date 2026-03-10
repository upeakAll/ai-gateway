"""Health and metrics endpoints."""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.config import settings
from app.schemas import HealthResponse
from app.storage import get_redis

router = APIRouter(tags=["Telemetry"])
logger = structlog.get_logger()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: DBSession,
) -> HealthResponse:
    """Health check endpoint."""
    db_status = "ok"
    redis_status = "ok"

    # Check database
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        db_status = "error"

    # Check Redis
    try:
        redis = await get_redis()
        await redis.ping()
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        redis_status = "error"

    overall_status = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.now(UTC),
    )


@router.get("/health/ready")
async def readiness_check(
    db: DBSession,
) -> dict[str, str]:
    """Readiness check for Kubernetes."""
    try:
        await db.execute(text("SELECT 1"))
        redis = await get_redis()
        await redis.ping()
        return {"status": "ready"}
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready",
        )


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Liveness check for Kubernetes."""
    return {"status": "alive"}


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    if not settings.metrics_enabled:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics disabled",
        )

    metrics_data = generate_latest()
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST,
    )
