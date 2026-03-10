"""Admin tenant management endpoints."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.models import BillingMode, Channel, RoutingStrategy, Tenant
from app.schemas import (
    PaginatedResponse,
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)
from app.schemas.common import PaginationParams

router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: DBSession,
) -> TenantResponse:
    """Create a new tenant."""
    # Check if slug already exists
    result = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with slug '{body.slug}' already exists",
        )

    # Create tenant
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        billing_mode=BillingMode(body.billing_mode),
        routing_strategy=RoutingStrategy(body.routing_strategy),
        quota_total=body.quota_total,
        description=body.description,
        billing_email=body.billing_email,
        contact_email=body.contact_email,
    )

    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    return _tenant_to_response(tenant)


@router.get("", response_model=PaginatedResponse[TenantResponse])
async def list_tenants(
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
) -> PaginatedResponse[TenantResponse]:
    """List all tenants with pagination."""
    query = select(Tenant)

    if is_active is not None:
        query = query.where(Tenant.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Tenant.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    tenants = result.scalars().all()

    return PaginatedResponse.create(
        items=[_tenant_to_response(t) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: DBSession,
) -> TenantResponse:
    """Get a specific tenant by ID."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    return _tenant_to_response(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: DBSession,
) -> TenantResponse:
    """Update a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    # Update fields
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "billing_mode" and value:
            value = BillingMode(value)
        elif field == "routing_strategy" and value:
            value = RoutingStrategy(value)
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)

    return _tenant_to_response(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    db: DBSession,
) -> None:
    """Delete a tenant (soft delete by setting is_active=False)."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    tenant.is_active = False
    await db.commit()


@router.post("/{tenant_id}/add-quota")
async def add_tenant_quota(
    tenant_id: str,
    amount: Decimal = Query(..., description="Amount to add in USD"),
    db: DBSession = Depends(),
) -> dict[str, Any]:
    """Add quota to a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )

    tenant.add_quota(amount)
    await db.commit()

    return {
        "tenant_id": tenant_id,
        "added_amount": str(amount),
        "new_quota_total": str(tenant.quota_total),
        "quota_remaining": str(tenant.quota_remaining),
    }


def _tenant_to_response(tenant: Tenant) -> TenantResponse:
    """Convert tenant model to response schema."""
    return TenantResponse(
        id=str(tenant.id),
        name=tenant.name,
        slug=tenant.slug,
        quota_total=tenant.quota_total,
        quota_used=tenant.quota_used,
        quota_remaining=tenant.quota_remaining,
        billing_mode=tenant.billing_mode.value,
        routing_strategy=tenant.routing_strategy.value,
        fixed_channel_id=tenant.fixed_channel_id,
        is_active=tenant.is_active,
        description=tenant.description,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )
