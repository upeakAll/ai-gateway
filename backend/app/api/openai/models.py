"""OpenAI-compatible models endpoint."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.models import Channel, ModelConfig
from app.schemas import ModelInfo, ModelListResponse

router = APIRouter()


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    db: DBSession,
) -> ModelListResponse:
    """List all available models.

    Returns a list of models configured across all channels.
    """
    # Get all active model configs
    result = await db.execute(
        select(ModelConfig)
        .join(Channel)
        .where(ModelConfig.is_active == True)  # type: ignore
        .where(Channel.is_active == True)  # type: ignore
        .distinct(ModelConfig.model_name)
    )
    model_configs = result.scalars().all()

    # Build model list
    models = []
    seen_names = set()

    for config in model_configs:
        if config.model_name in seen_names:
            continue
        seen_names.add(config.model_name)

        models.append(ModelInfo(
            id=config.model_name,
            object="model",
            created=int(time.time()),
            owned_by="ai-gateway",
            root=config.model_name,
        ))

    # Add some common model aliases
    common_models = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
    ]

    for model_name in common_models:
        if model_name not in seen_names:
            models.append(ModelInfo(
                id=model_name,
                object="model",
                created=int(time.time()),
                owned_by="ai-gateway",
                root=model_name,
            ))

    return ModelListResponse(
        object="list",
        data=sorted(models, key=lambda m: m.id),
    )


@router.get("/models/{model_id}", response_model=ModelInfo)
async def get_model(
    model_id: str,
    db: DBSession,
) -> ModelInfo:
    """Get information about a specific model."""
    # Check if model exists
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.model_name == model_id)
        .where(ModelConfig.is_active == True)  # type: ignore
        .limit(1)
    )
    config = result.scalar_one_or_none()

    if not config:
        # Return generic model info
        return ModelInfo(
            id=model_id,
            object="model",
            created=int(time.time()),
            owned_by="ai-gateway",
            root=model_id,
        )

    return ModelInfo(
        id=config.model_name,
        object="model",
        created=int(config.created_at.timestamp()) if config.created_at else int(time.time()),
        owned_by="ai-gateway",
        root=config.real_model_name,
    )
