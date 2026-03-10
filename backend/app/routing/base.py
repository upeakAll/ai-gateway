"""Base routing strategy interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.channel import Channel


@dataclass
class RoutingContext:
    """Context information for routing decisions."""

    tenant_id: str | None = None
    api_key_id: str | None = None
    model: str = ""
    channel_ids: list[str] | None = None  # Allowed channels
    metadata: dict[str, Any] | None = None


class RoutingStrategy(ABC):
    """Abstract base class for channel routing strategies."""

    @abstractmethod
    async def select_channel(
        self,
        channels: list[Channel],
        context: RoutingContext,
    ) -> Channel | None:
        """Select the best channel from available options.

        Args:
            channels: List of available channels
            context: Routing context with request details

        Returns:
            Selected channel or None if no suitable channel found
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get the name of this routing strategy."""
        pass

    def filter_available_channels(
        self,
        channels: list[Channel],
        context: RoutingContext,
    ) -> list[Channel]:
        """Filter channels to only available ones.

        Args:
            channels: All channels
            context: Routing context

        Returns:
            List of available channels
        """
        available = [c for c in channels if c.is_available]

        # Filter by tenant if specified in channel
        if context.tenant_id:
            # Include global channels (no tenant) and tenant-specific channels
            available = [
                c
                for c in available
                if c.tenant_id is None or c.tenant_id == context.tenant_id
            ]

        # Filter by allowed channel IDs
        if context.channel_ids:
            available = [c for c in available if str(c.id) in context.channel_ids]

        return available
