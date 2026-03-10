"""Usage statistics endpoints."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentContext, DBSession
from app.models import RequestStatus, UsageLog

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class UsageSummary(BaseModel):
    """Usage summary for a time period."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost: Decimal
    avg_latency_ms: float | None


class ModelUsage(BaseModel):
    """Usage breakdown by model."""

    model_name: str
    requests: int
    tokens: int
    cost: Decimal


class DailyUsage(BaseModel):
    """Usage for a single day."""

    date: str
    requests: int
    tokens: int
    cost: Decimal


class UsageResponse(BaseModel):
    """Full usage response."""

    summary: UsageSummary
    by_model: list[ModelUsage]
    by_day: list[DailyUsage]


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    ctx: CurrentContext,
    db: DBSession,
    start_date: Annotated[str | None, Query(description="Start date (YYYY-MM-DD)")] = None,
    end_date: Annotated[str | None, Query(description="End date (YYYY-MM-DD)")] = None,
    group_by: Annotated[str, Query(description="Group by: day, model")] = "day",
) -> UsageResponse:
    """Get usage statistics for the current tenant."""
    # Default to last 7 days
    if not start_date:
        start_dt = datetime.now(UTC) - timedelta(days=7)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)

    if not end_date:
        end_dt = datetime.now(UTC)
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)

    # Build base query
    base_query = select(UsageLog).where(
        UsageLog.tenant_id == ctx.tenant_id,
        UsageLog.created_at >= start_dt,
        UsageLog.created_at < end_dt,
    )

    # Get summary
    summary_result = await db.execute(
        select(
            func.count().label("total_requests"),
            func.sum(
                func.case((UsageLog.status == RequestStatus.SUCCESS, 1), else_=0)
            ).label("successful_requests"),
            func.sum(
                func.case((UsageLog.status != RequestStatus.SUCCESS, 1), else_=0)
            ).label("failed_requests"),
            func.sum(UsageLog.total_tokens).label("total_tokens"),
            func.sum(UsageLog.prompt_tokens).label("total_prompt_tokens"),
            func.sum(UsageLog.completion_tokens).label("total_completion_tokens"),
            func.sum(UsageLog.total_cost).label("total_cost"),
            func.avg(UsageLog.latency_ms).label("avg_latency_ms"),
        ).where(
            UsageLog.tenant_id == ctx.tenant_id,
            UsageLog.created_at >= start_dt,
            UsageLog.created_at < end_dt,
        )
    )
    summary_row = summary_result.one()

    summary = UsageSummary(
        total_requests=summary_row.total_requests or 0,
        successful_requests=summary_row.successful_requests or 0,
        failed_requests=summary_row.failed_requests or 0,
        total_tokens=summary_row.total_tokens or 0,
        total_prompt_tokens=summary_row.total_prompt_tokens or 0,
        total_completion_tokens=summary_row.total_completion_tokens or 0,
        total_cost=summary_row.total_cost or Decimal("0"),
        avg_latency_ms=summary_row.avg_latency_ms,
    )

    # Get usage by model
    model_result = await db.execute(
        select(
            UsageLog.model_name,
            func.count().label("requests"),
            func.sum(UsageLog.total_tokens).label("tokens"),
            func.sum(UsageLog.total_cost).label("cost"),
        ).where(
            UsageLog.tenant_id == ctx.tenant_id,
            UsageLog.created_at >= start_dt,
            UsageLog.created_at < end_dt,
        ).group_by(UsageLog.model_name).order_by(func.sum(UsageLog.total_cost).desc())
    )
    model_rows = model_result.all()

    by_model = [
        ModelUsage(
            model_name=row.model_name,
            requests=row.requests or 0,
            tokens=row.tokens or 0,
            cost=row.cost or Decimal("0"),
        )
        for row in model_rows
    ]

    # Get daily usage
    # Note: This is simplified - in production, use date_trunc for PostgreSQL
    daily_result = await db.execute(
        select(
            func.date_trunc("day", UsageLog.created_at).label("day"),
            func.count().label("requests"),
            func.sum(UsageLog.total_tokens).label("tokens"),
            func.sum(UsageLog.total_cost).label("cost"),
        ).where(
            UsageLog.tenant_id == ctx.tenant_id,
            UsageLog.created_at >= start_dt,
            UsageLog.created_at < end_dt,
        ).group_by(func.date_trunc("day", UsageLog.created_at)).order_by(func.date_trunc("day", UsageLog.created_at))
    )
    daily_rows = daily_result.all()

    by_day = [
        DailyUsage(
            date=str(row.day.date()) if row.day else "",
            requests=row.requests or 0,
            tokens=row.tokens or 0,
            cost=row.cost or Decimal("0"),
        )
        for row in daily_rows
    ]

    return UsageResponse(
        summary=summary,
        by_model=by_model,
        by_day=by_day,
    )


@router.get("/logs")
async def get_logs(
    ctx: CurrentContext,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    model: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    """Get usage logs for the current tenant."""
    # Build query
    query = select(UsageLog).where(
        UsageLog.tenant_id == ctx.tenant_id,
    )

    if model:
        query = query.where(UsageLog.model_name == model)

    if status_filter:
        query = query.where(UsageLog.status == status_filter)

    # Order by created_at desc
    query = query.order_by(UsageLog.created_at.desc())

    # Get total count
    from sqlalchemy import func as sql_func
    count_query = select(sql_func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(log.id),
                "request_id": log.request_id,
                "model_name": log.model_name,
                "provider": log.provider,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "total_tokens": log.total_tokens,
                "total_cost": str(log.total_cost),
                "latency_ms": log.latency_ms,
                "status": log.status.value,
                "error_message": log.error_message,
                "created_at": str(log.created_at),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }
