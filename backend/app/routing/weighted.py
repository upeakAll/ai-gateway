"""Weighted round-robin routing strategy."""

import random
from typing import Any

import structlog

from app.models.channel import Channel
from app.routing.base import RoutingContext, RoutingStrategy

logger = structlog.get_logger()


class WeightedRoundRobinStrategy(RoutingStrategy):
    """Weighted round-robin channel selection.

    Channels are selected based on their weight, with higher weight
    channels receiving more traffic proportionally.

    Example: If channel A has weight 3 and channel B has weight 1,
    channel A will receive 75% of traffic.
    """

    def __init__(self) -> None:
        # Track selection state per tenant for consistency
        self._counters: dict[str, int] = {}

    async def select_channel(
        self,
        channels: list[Channel],
        context: RoutingContext,
    ) -> Channel | None:
        """Select channel using weighted round-robin."""
        available = self.filter_available_channels(channels, context)

        if not available:
            logger.warning(
                "no_available_channels",
                tenant_id=context.tenant_id,
                model=context.model,
            )
            return None

        if len(available) == 1:
            return available[0]

        # Calculate total weight
        total_weight = sum(c.weight for c in available)
        if total_weight <= 0:
            # If all weights are 0, fall back to simple round-robin
            return random.choice(available)

        # Get counter for this context
        counter_key = self._get_counter_key(context, available)
        counter = self._counters.get(counter_key, 0)

        # Weighted selection
        selected_index = counter % total_weight
        cumulative = 0

        for channel in sorted(available, key=lambda c: c.priority, reverse=True):
            cumulative += channel.weight
            if selected_index < cumulative:
                self._counters[counter_key] = counter + 1
                logger.debug(
                    "channel_selected",
                    channel_id=str(channel.id),
                    channel_name=channel.name,
                    weight=channel.weight,
                    strategy="weighted_round_robin",
                )
                return channel

        # Fallback to first available
        return available[0]

    def get_strategy_name(self) -> str:
        return "weighted_round_robin"

    def _get_counter_key(
        self, context: RoutingContext, channels: list[Channel]
    ) -> str:
        """Generate a key for tracking round-robin state."""
        # Include channel IDs to reset counter if channels change
        channel_ids = ",".join(sorted(str(c.id) for c in channels))
        return f"{context.tenant_id or 'global'}:{channel_ids}"


class CostOptimizedStrategy(RoutingStrategy):
    """Cost-optimized channel selection.

    Selects channels with the lowest cost for the given model,
    while considering availability and quality.
    """

    def __init__(self, quality_threshold: float = 0.9) -> None:
        """
        Args:
            quality_threshold: Minimum success rate to consider channel
        """
        self.quality_threshold = quality_threshold

    async def select_channel(
        self,
        channels: list[Channel],
        context: RoutingContext,
    ) -> Channel | None:
        """Select channel with lowest cost."""
        available = self.filter_available_channels(channels, context)

        if not available:
            return None

        if len(available) == 1:
            return available[0]

        # Filter by quality threshold
        quality_channels = [
            c
            for c in available
            if c.success_rate is None or c.success_rate >= self.quality_threshold * 100
        ]

        # If no channels meet quality threshold, use all available
        if not quality_channels:
            quality_channels = available

        # Sort by cost (use default pricing as proxy)
        # In production, this would query actual model pricing
        def get_cost_estimate(channel: Channel) -> float:
            input_cost = float(channel.default_input_price or 0)
            output_cost = float(channel.default_output_price or 0)
            # Estimate based on typical 3:1 input:output ratio
            return (input_cost * 3 + output_cost) / 4

        sorted_channels = sorted(quality_channels, key=get_cost_estimate)

        selected = sorted_channels[0]
        logger.debug(
            "channel_selected",
            channel_id=str(selected.id),
            channel_name=selected.name,
            estimated_cost=get_cost_estimate(selected),
            strategy="cost_optimized",
        )

        return selected

    def get_strategy_name(self) -> str:
        return "cost_optimized"


class LatencyOptimizedStrategy(RoutingStrategy):
    """Latency-optimized channel selection.

    Selects channels with the lowest average response time,
    while considering availability.
    """

    def __init__(self, max_latency_ms: float = 5000.0) -> None:
        """
        Args:
            max_latency_ms: Maximum acceptable latency in milliseconds
        """
        self.max_latency_ms = max_latency_ms

    async def select_channel(
        self,
        channels: list[Channel],
        context: RoutingContext,
    ) -> Channel | None:
        """Select channel with lowest latency."""
        available = self.filter_available_channels(channels, context)

        if not available:
            return None

        if len(available) == 1:
            return available[0]

        # Filter by latency threshold
        fast_channels = [
            c
            for c in available
            if c.avg_response_time is None
            or c.avg_response_time <= self.max_latency_ms
        ]

        if not fast_channels:
            fast_channels = available

        # Sort by average response time (prefer channels with data)
        def get_latency(channel: Channel) -> float:
            return channel.avg_response_time or float("inf")

        sorted_channels = sorted(fast_channels, key=get_latency)

        selected = sorted_channels[0]
        logger.debug(
            "channel_selected",
            channel_id=str(selected.id),
            channel_name=selected.name,
            avg_latency_ms=selected.avg_response_time,
            strategy="latency_optimized",
        )

        return selected

    def get_strategy_name(self) -> str:
        return "latency_optimized"
