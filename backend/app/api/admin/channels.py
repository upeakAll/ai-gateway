"""Admin channel management endpoints."""

import time
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import AdapterRegistry
from app.api.deps import DBSession
from app.models import Channel, ChannelStatus, HealthStatus, ModelConfig, Provider
from app.schemas import (
    ChannelCreate,
    ChannelResponse,
    ChannelTestRequest,
    ChannelTestResponse,
    ChannelUpdate,
    ModelConfigCreate,
    ModelConfigResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/admin/channels", tags=["Admin - Channels"])
logger = structlog.get_logger()


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    db: DBSession,
) -> ChannelResponse:
    """Create a new channel."""
    # Validate provider
    try:
        provider = Provider(body.provider)
    except ValueError:
        valid_providers = [p.value for p in Provider]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Valid options: {valid_providers}",
        )

    # Create channel
    channel = Channel(
        tenant_id=body.tenant_id,
        name=body.name,
        provider=provider,
        api_key=body.api_key,  # Should be encrypted in production
        api_base=body.api_base,
        api_version=body.api_version,
        weight=body.weight,
        priority=body.priority,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        description=body.description,
        config=body.config,
        health_status=HealthStatus.UNKNOWN,
    )

    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    return _channel_to_response(channel)


@router.get("", response_model=PaginatedResponse[ChannelResponse])
async def list_channels(
    db: DBSession,
    tenant_id: str | None = None,
    provider: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ChannelResponse]:
    """List channels with optional filtering."""
    query = select(Channel)

    if tenant_id:
        query = query.where(Channel.tenant_id == tenant_id)

    if provider:
        query = query.where(Channel.provider == Provider(provider))

    if status_filter:
        query = query.where(Channel.status == ChannelStatus(status_filter))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Channel.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    channels = result.scalars().all()

    return PaginatedResponse.create(
        items=[_channel_to_response(c) for c in channels],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str,
    db: DBSession,
) -> ChannelResponse:
    """Get a specific channel by ID."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    return _channel_to_response(channel)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: str,
    body: ChannelUpdate,
    db: DBSession,
) -> ChannelResponse:
    """Update a channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    # Update fields
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            value = ChannelStatus(value)
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)

    return _channel_to_response(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    db: DBSession,
) -> None:
    """Delete a channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    await db.delete(channel)
    await db.commit()


@router.post("/{channel_id}/test", response_model=ChannelTestResponse)
async def test_channel(
    channel_id: str,
    body: ChannelTestRequest,
    db: DBSession,
) -> ChannelTestResponse:
    """Test a channel by making a test request."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    try:
        start_time = time.time()

        # Create adapter and test
        adapter = AdapterRegistry.create_adapter(channel)

        # Simple test request
        from app.adapters import ChatCompletionRequest as AdapterRequest
        from app.adapters import ChatMessage, MessageRole

        test_request = AdapterRequest(
            model=body.model,
            messages=[
                ChatMessage(role=MessageRole.USER, content=body.prompt),
            ],
            max_tokens=10,
        )

        response = await adapter.chat_completion(test_request)
        await adapter.close()

        latency_ms = (time.time() - start_time) * 1000

        # Update channel metrics
        channel.record_success(latency_ms)
        channel.health_status = HealthStatus.HEALTHY
        db.add(channel)
        await db.commit()

        return ChannelTestResponse(
            success=True,
            response_time_ms=latency_ms,
            model=response.model,
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000

        # Update channel metrics
        channel.record_failure()
        channel.health_status = HealthStatus.UNHEALTHY
        db.add(channel)
        await db.commit()

        return ChannelTestResponse(
            success=False,
            response_time_ms=latency_ms,
            error=str(e),
            model=body.model,
        )


@router.post("/{channel_id}/enable", response_model=ChannelResponse)
async def enable_channel(
    channel_id: str,
    db: DBSession,
) -> ChannelResponse:
    """Enable a disabled channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    channel.status = ChannelStatus.ACTIVE
    channel.circuit_breaker_open = False
    channel.consecutive_failures = 0
    await db.commit()
    await db.refresh(channel)

    return _channel_to_response(channel)


@router.post("/{channel_id}/disable", response_model=ChannelResponse)
async def disable_channel(
    channel_id: str,
    db: DBSession,
) -> ChannelResponse:
    """Disable a channel."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    channel.status = ChannelStatus.DISABLED
    await db.commit()
    await db.refresh(channel)

    return _channel_to_response(channel)


# ============ Model Configs ============


@router.post("/{channel_id}/models", response_model=ModelConfigResponse, status_code=status.HTTP_201_CREATED)
async def add_model_config(
    channel_id: str,
    body: ModelConfigCreate,
    db: DBSession,
) -> ModelConfigResponse:
    """Add a model configuration to a channel."""
    # Verify channel exists
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found",
        )

    # Check if model config already exists
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.channel_id == channel_id,
            ModelConfig.model_name == body.model_name,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{body.model_name}' already configured for this channel",
        )

    # Create model config
    model_config = ModelConfig(
        channel_id=channel_id,
        model_name=body.model_name,
        real_model_name=body.real_model_name,
        input_price=body.input_price,
        output_price=body.output_price,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        supports_streaming=body.supports_streaming,
        supports_functions=body.supports_functions,
        supports_vision=body.supports_vision,
        max_context_tokens=body.max_context_tokens,
        max_output_tokens=body.max_output_tokens,
    )

    db.add(model_config)
    await db.commit()
    await db.refresh(model_config)

    return ModelConfigResponse.model_validate(model_config)


@router.get("/{channel_id}/models", response_model=list[ModelConfigResponse])
async def list_model_configs(
    channel_id: str,
    db: DBSession,
) -> list[ModelConfigResponse]:
    """List all model configurations for a channel."""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.channel_id == channel_id)
    )
    configs = result.scalars().all()

    return [ModelConfigResponse.model_validate(c) for c in configs]


@router.delete("/{channel_id}/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_config(
    channel_id: str,
    model_id: str,
    db: DBSession,
) -> None:
    """Delete a model configuration."""
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.channel_id == channel_id,
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model configuration not found",
        )

    await db.delete(config)
    await db.commit()


def _channel_to_response(channel: Channel) -> ChannelResponse:
    """Convert channel model to response schema."""
    return ChannelResponse(
        id=str(channel.id),
        tenant_id=str(channel.tenant_id) if channel.tenant_id else None,
        name=channel.name,
        provider=channel.provider.value,
        api_base=channel.api_base,
        weight=channel.weight,
        priority=channel.priority,
        status=channel.status.value,
        health_status=channel.health_status.value,
        avg_response_time=channel.avg_response_time,
        success_rate=channel.success_rate,
        is_available=channel.is_available,
        description=channel.description,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )
