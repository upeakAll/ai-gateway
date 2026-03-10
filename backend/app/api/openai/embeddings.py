"""OpenAI-compatible embeddings endpoint."""

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import AdapterRegistry, EmbeddingRequest as AdapterEmbeddingRequest
from app.api.deps import CurrentContext, DBSession
from app.core.exceptions import AdapterError
from app.models import Channel, ModelConfig
from app.routing import RoutingContext, channel_selector
from app.schemas import Embedding, EmbeddingRequest, EmbeddingResponse, Usage

router = APIRouter()
logger = structlog.get_logger()


@router.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    body: EmbeddingRequest,
    ctx: CurrentContext,
    db: DBSession,
) -> EmbeddingResponse:
    """Create embeddings for the given input."""
    start_time = time.time()

    # Check model access
    if not ctx.has_model_access(body.model):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not available for this API key",
        )

    # Get available channels for embedding model
    query = (
        select(Channel)
        .where(Channel.is_available == True)  # type: ignore
    )
    if ctx.tenant_id:
        query = query.where(
            (Channel.tenant_id == ctx.tenant_id) | (Channel.tenant_id.is_(None))
        )

    result = await db.execute(query)
    channels = list(result.scalars().all())

    # Filter to channels supporting embeddings
    embedding_channels = []
    for channel in channels:
        # Check model configs for embedding support
        mc_result = await db.execute(
            select(ModelConfig)
            .where(ModelConfig.channel_id == str(channel.id))
            .where(ModelConfig.model_name == body.model)
        )
        if mc_result.scalar_one_or_none():
            embedding_channels.append(channel)

    if not embedding_channels:
        # Try to find any channel that supports the model
        for channel in channels:
            if "embedding" in body.model.lower() or "embed" in body.model.lower():
                if channel.provider.value in ["openai", "azure_openai"]:
                    embedding_channels.append(channel)

    if not embedding_channels:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No available channels for embedding model '{body.model}'",
        )

    # Select channel
    routing_context = RoutingContext(
        tenant_id=ctx.tenant_id,
        api_key_id=ctx.api_key_id,
        model=body.model,
    )
    channel = await channel_selector.select_channel(
        embedding_channels, routing_context
    )

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No available channels for this request",
        )

    # Build adapter request
    input_texts = body.input if isinstance(body.input, list) else [body.input]
    adapter_request = AdapterEmbeddingRequest(
        model=body.model,
        input=input_texts,
        encoding_format=body.encoding_format,
        dimensions=body.dimensions,
        user=body.user,
    )

    # Create adapter and execute
    try:
        adapter = AdapterRegistry.create_adapter(channel)
        response = await adapter.embedding(adapter_request)
        await adapter.close()

        latency_ms = (time.time() - start_time) * 1000
        channel.record_success(latency_ms)
        db.add(channel)

        # Calculate and deduct quota (embeddings typically have lower cost)
        from decimal import Decimal
        total_tokens = response.usage.total_tokens
        cost = Decimal(total_tokens) * Decimal("0.0001") / 1000  # $0.0001 per 1K tokens
        ctx.tenant.use_quota(cost)
        ctx.api_key.use_quota(cost)

        await db.commit()

        return EmbeddingResponse(
            object="list",
            data=[
                Embedding(
                    object="embedding",
                    index=e.index,
                    embedding=e.embedding,
                )
                for e in response.data
            ],
            model=response.model,
            usage=Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
        )

    except AdapterError as e:
        logger.error("embedding_failed", error=str(e), model=body.model)
        channel.record_failure()
        db.add(channel)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding failed: {str(e)}",
        )
    except Exception as e:
        logger.error("embedding_error", error=str(e), model=body.model)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding error: {str(e)}",
        )
