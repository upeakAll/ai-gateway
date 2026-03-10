"""Tenant model for multi-tenancy support."""

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.channel import Channel


class BillingMode(StrEnum):
    """Billing mode for tenants."""

    PREPAID = "prepaid"  # Pay in advance
    POSTPAID = "postpaid"  # Pay after usage


class RoutingStrategy(StrEnum):
    """Routing strategy for channel selection."""

    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"  # Weighted round-robin
    COST_OPTIMIZED = "cost_optimized"  # Lowest cost first
    FIXED_CHANNEL = "fixed_channel"  # Fixed channel per tenant
    LATENCY_OPTIMIZED = "latency_optimized"  # Lowest latency first


class Tenant(BaseModel):
    """Tenant entity representing an organization or account."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )

    # Quota management
    quota_total: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Total quota in USD",
    )
    quota_used: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Used quota in USD",
    )

    # Billing configuration
    billing_mode: Mapped[BillingMode] = mapped_column(
        Enum(BillingMode),
        nullable=False,
        default=BillingMode.PREPAID,
    )
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Routing configuration
    routing_strategy: Mapped[RoutingStrategy] = mapped_column(
        Enum(RoutingStrategy),
        nullable=False,
        default=RoutingStrategy.WEIGHTED_ROUND_ROBIN,
    )
    fixed_channel_id: Mapped[str | None] = mapped_column(
        String(36),  # UUID as string
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="tenant", cascade="all, delete-orphan"
    )
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", back_populates="tenant", cascade="all, delete-orphan"
    )

    @property
    def quota_remaining(self) -> Decimal:
        """Calculate remaining quota."""
        return max(Decimal("0"), self.quota_total - self.quota_used)

    @property
    def quota_percentage(self) -> float:
        """Calculate quota usage percentage."""
        if self.quota_total == 0:
            return 0.0
        return float(self.quota_used / self.quota_total * 100)

    def has_quota(self, amount: Decimal) -> bool:
        """Check if tenant has enough quota for the given amount."""
        if self.billing_mode == BillingMode.POSTPAID:
            return True  # Postpaid tenants can use unlimited
        return self.quota_remaining >= amount

    def use_quota(self, amount: Decimal) -> bool:
        """Deduct quota from tenant. Returns True if successful."""
        if not self.has_quota(amount):
            return False
        self.quota_used += amount
        return True

    def add_quota(self, amount: Decimal) -> None:
        """Add quota to tenant."""
        self.quota_total += amount
