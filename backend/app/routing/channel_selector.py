"""Channel selector for orchestrating routing strategies."""

from typing import Any

import structlog

from app.models.channel import Channel
from app.models.tenant import RoutingStrategy as TenantRoutingStrategy
from app.routing.base import RoutingContext
from app.routing.weighted import (
    CostOptimizedStrategy,
    LatencyOptimizedStrategy,
    WeightedRoundRobinStrategy,
)

logger = structlog.get_logger()


class ChannelSelector:
    """Manages channel selection using various routing strategies."""

    def __init__(self) -> None:
        self._strategies: dict[str, Any] = {
            TenantRoutingStrategy.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinStrategy(),
            TenantRoutingStrategy.COST_OPTIMIZED: CostOptimizedStrategy(),
            TenantRoutingStrategy.LATENCY_OPTIMIZED: LatencyOptimizedStrategy(),
        }

    def register_strategy(self, name: str, strategy: Any) -> None:
        """Register a custom routing strategy.

        Args:
            name: Strategy name
            strategy: Strategy instance
        """
        self._strategies[name] = strategy
        logger.info("routing_strategy_registered", strategy=name)

    async def select_channel(
        self,
        channels: list[Channel],
        context: RoutingContext,
        strategy_name: str | None = None,
    ) -> Channel | None:
        """Select a channel using the specified strategy.

        Args:
            channels: List of available channels
            context: Routing context
            strategy_name: Strategy to use (defaults to weighted round-robin)

        Returns:
            Selected channel or None
        """
        if not channels:
            logger.warning("no_channels_provided")
            return None

        # Get strategy
        strategy_key = strategy_name or TenantRoutingStrategy.WEIGHTED_ROUND_ROBIN
        if isinstance(strategy_key, TenantRoutingStrategy):
            strategy_key = strategy_key.value

        strategy = self._strategies.get(strategy_key)
        if not strategy:
            logger.warning(
                "unknown_strategy",
                strategy=strategy_key,
                fallback="weighted_round_robin",
            )
            strategy = self._strategies[TenantRoutingStrategy.WEIGHTED_ROUND_ROBIN]

        # Execute strategy
        try:
            selected = await strategy.select_channel(channels, context)
            if selected:
                logger.info(
                    "channel_selected",
                    channel_id=str(selected.id),
                    channel_name=selected.name,
                    provider=selected.provider.value,
                    strategy=strategy_key,
                    model=context.model,
                )
            return selected
        except Exception as e:
            logger.error(
                "channel_selection_error",
                strategy=strategy_key,
                error=str(e),
            )
            # Fallback to first available
            available = strategy.filter_available_channels(channels, context)
            return available[0] if available else None

    async def select_channel_for_fixed_route(
        self,
        channels: list[Channel],
        context: RoutingContext,
        fixed_channel_id: str,
    ) -> Channel | None:
        """Select a specific fixed channel for tenant with fixed routing.

        Args:
            channels: List of available channels
            context: Routing context
            fixed_channel_id: ID of the fixed channel to use

        Returns:
            Selected channel or None if not available
        """
        # Find the fixed channel
        for channel in channels:
            if str(channel.id) == fixed_channel_id:
                if channel.is_available:
                    return channel
                else:
                    logger.warning(
                        "fixed_channel_unavailable",
                        channel_id=fixed_channel_id,
                        status=channel.status.value,
                        health=channel.health_status.value,
                    )
                    return None

        logger.warning(
            "fixed_channel_not_found",
            channel_id=fixed_channel_id,
        )
        return None


# Global channel selector instance
channel_selector = ChannelSelector()
