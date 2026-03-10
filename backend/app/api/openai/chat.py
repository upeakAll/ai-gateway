"""OpenAI-compatible chat completions endpoint."""

import json
import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters import (
    AdapterRegistry,
    ChatCompletionRequest as AdapterRequest,
    ChatMessage,
    MessageRole,
    ToolDefinition,
)
from app.api.deps import CurrentContext, DBSession
from app.config import settings
from app.core.exceptions import (
    ModelNotSupportedError,
    NoAvailableChannelError,
    RateLimitExceededError,
    TenantQuotaExceededError,
)
from app.models import Channel, ModelConfig, RequestStatus, UsageLog
from app.routing import RoutingContext, channel_selector
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionStreamResponse,
    ChatCompletionStreamChoice,
    ChatCompletionStreamDelta,
    Usage,
)
from app.storage import RateLimiter, get_redis

router = APIRouter()
logger = structlog.get_logger()


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: Request,
    body: ChatCompletionRequest,
    ctx: CurrentContext,
    db: DBSession,
) -> ChatCompletionResponse | StreamingResponse:
    """Create a chat completion.

    Supports both streaming and non-streaming responses.
    """
    start_time = time.time()

    # Check model access
    if not ctx.has_model_access(body.model):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not available for this API key",
        )

    # Get available channels for this model
    channels = await _get_channels_for_model(db, body.model, ctx.tenant_id)
    if not channels:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No available channels for model '{body.model}'",
        )

    # Check rate limits
    redis = await get_redis()
    rate_limiter = RateLimiter(redis)

    # Check RPM limit
    rpm_limit = ctx.api_key.rpm_limit or settings.rate_limit_default_rpm
    rpm_key = f"key:{ctx.api_key_id}:rpm"
    allowed, current, retry_after = await rate_limiter.check_rate_limit(
        rpm_key, rpm_limit, settings.rate_limit_window_seconds
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds",
            headers={"Retry-After": str(retry_after)},
        )

    # Select channel using routing strategy
    routing_context = RoutingContext(
        tenant_id=ctx.tenant_id,
        api_key_id=ctx.api_key_id,
        model=body.model,
    )

    # Handle fixed channel routing
    if ctx.tenant.routing_strategy.value == "fixed_channel" and ctx.tenant.fixed_channel_id:
        channel = await channel_selector.select_channel_for_fixed_route(
            channels, routing_context, ctx.tenant.fixed_channel_id
        )
    else:
        channel = await channel_selector.select_channel(
            channels, routing_context, ctx.tenant.routing_strategy.value
        )

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No available channels for this request",
        )

    # Get model config for pricing
    model_config = await _get_model_config(db, str(channel.id), body.model)

    # Build adapter request
    adapter_request = _build_adapter_request(body)

    # Create adapter
    try:
        adapter = AdapterRegistry.create_adapter(channel)
    except Exception as e:
        logger.error("adapter_creation_failed", channel_id=str(channel.id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create adapter: {str(e)}",
        )

    # Handle streaming vs non-streaming
    if body.stream:
        return EventSourceResponse(
            _stream_completion(
                adapter, adapter_request, channel, model_config, ctx, db, start_time
            ),
            media_type="text/event-stream",
        )

    # Non-streaming completion
    try:
        response = await adapter.chat_completion(adapter_request)

        # Calculate cost
        cost = _calculate_cost(model_config, response.usage.prompt_tokens, response.usage.completion_tokens)

        # Check and deduct quota
        if not ctx.tenant.has_quota(cost):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient quota",
            )

        # Deduct quota
        ctx.tenant.use_quota(cost)
        ctx.api_key.use_quota(cost)

        # Record success
        channel.record_success(response.latency_ms)
        db.add(channel)

        # Create usage log
        await _create_usage_log(
            db, ctx, channel, model_config, response, cost, start_time, RequestStatus.SUCCESS
        )

        await db.commit()

        # Convert to response format
        return ChatCompletionResponse(
            id=response.id,
            object="chat.completion",
            created=response.created,
            model=response.model,
            choices=[
                ChatCompletionChoice(
                    index=c.index,
                    message=_convert_message(c.message),
                    finish_reason=c.finish_reason,
                )
                for c in response.choices
            ],
            usage=Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            system_fingerprint=response.system_fingerprint,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_completion_failed", error=str(e), model=body.model)
        channel.record_failure()
        db.add(channel)
        await _create_usage_log(
            db, ctx, channel, model_config, None, None, start_time, RequestStatus.FAILED, str(e)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat completion failed: {str(e)}",
        )
    finally:
        await adapter.close()


async def _stream_completion(
    adapter: Any,
    request: AdapterRequest,
    channel: Channel,
    model_config: ModelConfig | None,
    ctx: CurrentContext,
    db: AsyncSession,
    start_time: float,
) -> Any:
    """Stream chat completion response."""
    completion_id = f"chatcmpl-{int(time.time())}"
    created = int(time.time())
    total_prompt_tokens = 0
    total_completion_tokens = 0
    finish_reason = None

    try:
        async for chunk in adapter.chat_completion_stream(request):
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason

            if chunk.usage:
                total_prompt_tokens = chunk.usage.prompt_tokens
                total_completion_tokens = chunk.usage.completion_tokens

            # Convert to OpenAI streaming format
            delta = ChatCompletionStreamDelta(
                role=chunk.delta.get("role"),
                content=chunk.delta.get("content"),
                tool_calls=chunk.delta.get("tool_calls"),
            )

            stream_chunk = ChatCompletionStreamResponse(
                id=chunk.id or completion_id,
                created=chunk.id and int(time.time()) or created,
                model=chunk.model or request.model,
                choices=[
                    ChatCompletionStreamChoice(
                        index=0,
                        delta=delta,
                        finish_reason=chunk.finish_reason,
                    )
                ],
                usage=Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                ) if chunk.usage else None,
            )

            yield {
                "event": "message",
                "data": stream_chunk.model_dump_json(exclude_none=True),
            }

        # Final chunk
        final_chunk = ChatCompletionStreamResponse(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[
                ChatCompletionStreamChoice(
                    index=0,
                    delta=ChatCompletionStreamDelta(),
                    finish_reason=finish_reason or "stop",
                )
            ],
        )
        yield {"event": "message", "data": final_chunk.model_dump_json(exclude_none=True)}
        yield {"event": "message", "data": "[DONE]"}

        # Calculate cost and update quota
        cost = _calculate_cost(model_config, total_prompt_tokens, total_completion_tokens)
        latency_ms = (time.time() - start_time) * 1000

        channel.record_success(latency_ms)
        ctx.tenant.use_quota(cost)
        ctx.api_key.use_quota(cost)

        # Create usage log
        await _create_usage_log(
            db,
            ctx,
            channel,
            model_config,
            None,
            cost,
            start_time,
            RequestStatus.SUCCESS,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            is_streaming=True,
        )
        await db.commit()

    except Exception as e:
        logger.error("streaming_failed", error=str(e))
        channel.record_failure()
        db.add(channel)
        await db.commit()
        yield {"event": "error", "data": json.dumps({"error": str(e)})}

    finally:
        await adapter.close()


async def _get_channels_for_model(
    db: AsyncSession,
    model: str,
    tenant_id: str | None,
) -> list[Channel]:
    """Get all available channels for a model."""
    query = (
        select(Channel)
        .options(selectinload(Channel.model_configs))
        .where(Channel.is_available == True)  # type: ignore
    )

    # Filter by tenant (include global channels)
    if tenant_id:
        query = query.where(
            (Channel.tenant_id == tenant_id) | (Channel.tenant_id.is_(None))
        )
    else:
        query = query.where(Channel.tenant_id.is_(None))

    result = await db.execute(query)
    channels = list(result.scalars().all())

    # Filter channels that support the model
    supporting_channels = []
    for channel in channels:
        # Check if any model config matches
        for mc in channel.model_configs:
            if mc.model_name == model and mc.is_active:
                supporting_channels.append(channel)
                break

    return supporting_channels


async def _get_model_config(
    db: AsyncSession,
    channel_id: str,
    model_name: str,
) -> ModelConfig | None:
    """Get model configuration for pricing."""
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.channel_id == channel_id,
            ModelConfig.model_name == model_name,
            ModelConfig.is_active == True,  # type: ignore
        )
    )
    return result.scalar_one_or_none()


def _build_adapter_request(body: ChatCompletionRequest) -> AdapterRequest:
    """Convert API request to adapter request format."""
    messages = []
    for msg in body.messages:
        content = msg.content
        if isinstance(content, str):
            messages.append(ChatMessage(
                role=MessageRole(msg.role),
                content=content,
                name=msg.name,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
            ))
        else:
            messages.append(ChatMessage(
                role=MessageRole(msg.role),
                content=content,
                name=msg.name,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
            ))

    tools = None
    if body.tools:
        tools = [
            ToolDefinition(
                name=t.function.name,
                description=t.function.description,
                parameters=t.function.parameters,
            )
            for t in body.tools
        ]

    return AdapterRequest(
        model=body.model,
        messages=messages,
        temperature=body.temperature or 1.0,
        top_p=body.top_p or 1.0,
        max_tokens=body.max_tokens,
        stream=body.stream,
        tools=tools,
        tool_choice=body.tool_choice,
        stop=[body.stop] if isinstance(body.stop, str) else body.stop,
        frequency_penalty=body.frequency_penalty or 0.0,
        presence_penalty=body.presence_penalty or 0.0,
        user=body.user,
    )


def _convert_message(msg: ChatMessage) -> dict[str, Any]:
    """Convert adapter message to response format."""
    return {
        "role": msg.role.value,
        "content": msg.content,
        "tool_calls": msg.tool_calls,
    }


def _calculate_cost(
    model_config: ModelConfig | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> Any:
    """Calculate request cost."""
    from decimal import Decimal

    if model_config:
        return model_config.calculate_cost(prompt_tokens, completion_tokens)

    # Use default pricing
    input_cost = Decimal(prompt_tokens) * Decimal(settings.default_input_price_per_1k) / 1000
    output_cost = Decimal(completion_tokens) * Decimal(settings.default_output_price_per_1k) / 1000
    return input_cost + output_cost


async def _create_usage_log(
    db: AsyncSession,
    ctx: CurrentContext,
    channel: Channel,
    model_config: ModelConfig | None,
    response: Any,
    cost: Any,
    start_time: float,
    status: RequestStatus,
    error_message: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    is_streaming: bool = False,
) -> None:
    """Create usage log entry."""
    from decimal import Decimal

    latency_ms = (time.time() - start_time) * 1000

    if response and not is_streaming:
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    usage_log = UsageLog(
        tenant_id=ctx.tenant_id,
        api_key_id=ctx.api_key_id,
        channel_id=str(channel.id),
        request_id=ctx.request_id,
        model_name=model_config.model_name if model_config else "unknown",
        real_model_name=model_config.real_model_name if model_config else None,
        provider=channel.provider.value,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        input_cost=Decimal(str(cost)) * prompt_tokens / (prompt_tokens + completion_tokens) if cost and (prompt_tokens + completion_tokens) > 0 else Decimal("0"),
        output_cost=Decimal(str(cost)) * completion_tokens / (prompt_tokens + completion_tokens) if cost and (prompt_tokens + completion_tokens) > 0 else Decimal("0"),
        total_cost=cost or Decimal("0"),
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        client_ip=ctx.client_ip,
        is_streaming=is_streaming,
    )

    db.add(usage_log)
