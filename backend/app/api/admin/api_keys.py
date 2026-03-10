"""Admin API key management endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.core.security import generate_api_key, generate_sub_key, hash_api_key
from app.models import APIKey, KeyStatus, SubKey, Tenant
from app.schemas import (
    APIKeyCreate,
    APIKeyResponse,
    PaginatedResponse,
    SubKeyCreate,
    SubKeyResponse,
)

router = APIRouter(prefix="/admin/keys", tags=["Admin - API Keys"])


@router.post("", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreate,
    db: DBSession,
) -> APIKeyResponse:
    """Create a new API key."""
    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{body.tenant_id}' not found",
        )

    # Generate API key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)

    # Create API key record
    api_key = APIKey(
        tenant_id=body.tenant_id,
        key=plain_key,
        key_hash=key_hash,
        name=body.name,
        quota_total=body.quota_total,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        allowed_models=body.allowed_models,
        expires_at=body.expires_at,
        description=body.description,
    )

    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return _api_key_to_response(api_key, include_key=True)


@router.get("", response_model=PaginatedResponse[APIKeyResponse])
async def list_api_keys(
    db: DBSession,
    tenant_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[APIKeyResponse]:
    """List API keys with optional filtering."""
    query = select(APIKey)

    if tenant_id:
        query = query.where(APIKey.tenant_id == tenant_id)

    if status_filter:
        query = query.where(APIKey.status == KeyStatus(status_filter))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(APIKey.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    keys = result.scalars().all()

    return PaginatedResponse.create(
        items=[_api_key_to_response(k) for k in keys],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    db: DBSession,
) -> APIKeyResponse:
    """Get a specific API key by ID."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    return _api_key_to_response(api_key)


@router.post("/{key_id}/regenerate", response_model=APIKeyResponse)
async def regenerate_api_key(
    key_id: str,
    db: DBSession,
) -> APIKeyResponse:
    """Regenerate an API key (generates a new key value)."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    # Generate new key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)

    api_key.key = plain_key
    api_key.key_hash = key_hash

    await db.commit()
    await db.refresh(api_key)

    return _api_key_to_response(api_key, include_key=True)


@router.post("/{key_id}/disable", response_model=APIKeyResponse)
async def disable_api_key(
    key_id: str,
    db: DBSession,
) -> APIKeyResponse:
    """Disable an API key."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    api_key.status = KeyStatus.DISABLED
    await db.commit()
    await db.refresh(api_key)

    return _api_key_to_response(api_key)


@router.post("/{key_id}/enable", response_model=APIKeyResponse)
async def enable_api_key(
    key_id: str,
    db: DBSession,
) -> APIKeyResponse:
    """Enable a disabled API key."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    api_key.status = KeyStatus.ACTIVE
    await db.commit()
    await db.refresh(api_key)

    return _api_key_to_response(api_key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    db: DBSession,
) -> None:
    """Delete an API key."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    await db.delete(api_key)
    await db.commit()


# ============ Sub-keys ============


@router.post("/{key_id}/sub-keys", response_model=SubKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_sub_key(
    key_id: str,
    body: SubKeyCreate,
    db: DBSession,
) -> SubKeyResponse:
    """Create a sub-key for an API key."""
    # Verify parent key exists
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    parent_key = result.scalar_one_or_none()

    if not parent_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    # Generate sub-key
    plain_key = generate_sub_key()
    key_hash = hash_api_key(plain_key)

    # Create sub-key record
    sub_key = SubKey(
        parent_key_id=key_id,
        key=plain_key,
        key_hash=key_hash,
        name=body.name,
        quota_total=body.quota_total,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        expires_at=body.expires_at,
        description=body.description,
    )

    db.add(sub_key)
    await db.commit()
    await db.refresh(sub_key)

    return _sub_key_to_response(sub_key, include_key=True)


@router.get("/{key_id}/sub-keys", response_model=list[SubKeyResponse])
async def list_sub_keys(
    key_id: str,
    db: DBSession,
) -> list[SubKeyResponse]:
    """List all sub-keys for an API key."""
    result = await db.execute(
        select(SubKey).where(SubKey.parent_key_id == key_id).order_by(SubKey.created_at.desc())
    )
    sub_keys = result.scalars().all()

    return [_sub_key_to_response(sk) for sk in sub_keys]


@router.delete("/{key_id}/sub-keys/{sub_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sub_key(
    key_id: str,
    sub_key_id: str,
    db: DBSession,
) -> None:
    """Delete a sub-key."""
    result = await db.execute(
        select(SubKey).where(
            SubKey.id == sub_key_id,
            SubKey.parent_key_id == key_id,
        )
    )
    sub_key = result.scalar_one_or_none()

    if not sub_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sub-key '{sub_key_id}' not found",
        )

    await db.delete(sub_key)
    await db.commit()


def _api_key_to_response(api_key: APIKey, include_key: bool = False) -> APIKeyResponse:
    """Convert API key model to response schema."""
    return APIKeyResponse(
        id=str(api_key.id),
        tenant_id=str(api_key.tenant_id),
        key=api_key.key if include_key else None,
        name=api_key.name,
        quota_total=api_key.quota_total,
        quota_used=api_key.quota_used,
        quota_remaining=api_key.quota_remaining,
        rpm_limit=api_key.rpm_limit,
        tpm_limit=api_key.tpm_limit,
        allowed_models=api_key.allowed_models,
        status=api_key.status.value,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


def _sub_key_to_response(sub_key: SubKey, include_key: bool = False) -> SubKeyResponse:
    """Convert sub-key model to response schema."""
    return SubKeyResponse(
        id=str(sub_key.id),
        parent_key_id=str(sub_key.parent_key_id),
        key=sub_key.key if include_key else None,
        name=sub_key.name,
        quota_total=sub_key.quota_total,
        quota_used=sub_key.quota_used,
        quota_remaining=sub_key.quota_remaining,
        rpm_limit=sub_key.rpm_limit,
        tpm_limit=sub_key.tpm_limit,
        status=sub_key.status.value,
        expires_at=sub_key.expires_at,
        created_at=sub_key.created_at,
    )
