"""Tests for routing strategies."""

import pytest
from decimal import Decimal

from app.models import Channel, ChannelStatus, HealthStatus, Provider, RoutingStrategy as TenantRoutingStrategy
from app.routing import (
    RoutingContext,
    WeightedRoundRobinStrategy,
    CostOptimizedStrategy,
    LatencyOptimizedStrategy,
    channel_selector,
)


def create_channel(
    name: str,
    provider: Provider = Provider.OPENAI,
    weight: int = 1,
    priority: int = 0,
    health_status: HealthStatus = HealthStatus.HEALTHY,
    avg_response_time: float | None = None,
    success_rate: float | None = None,
    default_input_price: Decimal | None = None,
) -> Channel:
    """Create a test channel."""
    channel = Channel(
        name=name,
        provider=provider,
        api_key="test-key",
        weight=weight,
        priority=priority,
        status=ChannelStatus.ACTIVE,
        health_status=health_status,
        avg_response_time=avg_response_time,
        success_rate=success_rate,
        default_input_price=default_input_price,
    )
    # Set id manually for testing
    import uuid
    channel.id = uuid.uuid4()
    return channel


class TestWeightedRoundRobinStrategy:
    """Tests for weighted round-robin strategy."""

    @pytest.mark.asyncio
    async def test_single_channel(self):
        """Test selection with single channel."""
        channels = [create_channel("channel1")]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = WeightedRoundRobinStrategy()

        selected = await strategy.select_channel(channels, context)
        assert selected == channels[0]

    @pytest.mark.asyncio
    async def test_weighted_distribution(self):
        """Test weighted distribution."""
        # Channel with weight 3 should be selected 3x more often
        channel1 = create_channel("low", weight=1)
        channel2 = create_channel("high", weight=3)

        channels = [channel1, channel2]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = WeightedRoundRobinStrategy()

        # Run multiple selections
        selections = []
        for _ in range(4):
            selected = await strategy.select_channel(channels, context)
            selections.append(selected.name)

        # With weights 1:3, in 4 rounds we expect 1 of low and 3 of high
        assert selections.count("high") == 3
        assert selections.count("low") == 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test priority ordering."""
        low_priority = create_channel("low", priority=0)
        high_priority = create_channel("high", priority=10)

        channels = [low_priority, high_priority]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = WeightedRoundRobinStrategy()

        # Higher priority should be selected first
        selected = await strategy.select_channel(channels, context)
        assert selected == high_priority

    @pytest.mark.asyncio
    async def test_filter_unhealthy(self):
        """Test filtering of unhealthy channels."""
        healthy = create_channel("healthy", health_status=HealthStatus.HEALTHY)
        unhealthy = create_channel("unhealthy", health_status=HealthStatus.UNHEALTHY)

        channels = [healthy, unhealthy]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = WeightedRoundRobinStrategy()

        selected = await strategy.select_channel(channels, context)
        assert selected == healthy


class TestCostOptimizedStrategy:
    """Tests for cost-optimized strategy."""

    @pytest.mark.asyncio
    async def test_cheapest_selection(self):
        """Test selection of cheapest channel."""
        cheap = create_channel("cheap", default_input_price=Decimal("0.001"))
        expensive = create_channel("expensive", default_input_price=Decimal("0.01"))

        channels = [expensive, cheap]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = CostOptimizedStrategy()

        selected = await strategy.select_channel(channels, context)
        assert selected == cheap

    @pytest.mark.asyncio
    async def test_quality_threshold(self):
        """Test quality threshold filtering."""
        good = create_channel("good", success_rate=95.0, default_input_price=Decimal("0.01"))
        bad = create_channel("bad", success_rate=50.0, default_input_price=Decimal("0.001"))

        channels = [good, bad]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = CostOptimizedStrategy(quality_threshold=0.9)

        selected = await strategy.select_channel(channels, context)
        # Bad channel should be filtered by quality threshold
        assert selected == good


class TestLatencyOptimizedStrategy:
    """Tests for latency-optimized strategy."""

    @pytest.mark.asyncio
    async def test_fastest_selection(self):
        """Test selection of fastest channel."""
        fast = create_channel("fast", avg_response_time=100.0)
        slow = create_channel("slow", avg_response_time=500.0)

        channels = [slow, fast]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = LatencyOptimizedStrategy()

        selected = await strategy.select_channel(channels, context)
        assert selected == fast

    @pytest.mark.asyncio
    async def test_latency_threshold(self):
        """Test latency threshold."""
        good = create_channel("good", avg_response_time=100.0)
        bad = create_channel("bad", avg_response_time=10000.0)

        channels = [bad, good]
        context = RoutingContext(tenant_id="test", model="gpt-4")
        strategy = LatencyOptimizedStrategy(max_latency_ms=5000.0)

        selected = await strategy.select_channel(channels, context)
        # Bad channel exceeds threshold
        assert selected == good


class TestChannelSelector:
    """Tests for channel selector."""

    @pytest.mark.asyncio
    async def test_strategy_selection(self):
        """Test strategy-based selection."""
        channels = [create_channel("test")]
        context = RoutingContext(tenant_id="test", model="gpt-4")

        selected = await channel_selector.select_channel(
            channels,
            context,
            TenantRoutingStrategy.WEIGHTED_ROUND_ROBIN.value,
        )
        assert selected is not None
