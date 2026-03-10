"""Usage log model for tracking requests and token consumption."""

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.channel import Channel
    from app.models.tenant import Tenant


class RequestStatus(StrEnum):
    """Status of a request."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CANCELLED = "cancelled"


class UsageLog(Base):
    """Usage log for tracking requests and billing.

    This table is designed for high-volume writes and time-series queries.
    Consider using table partitioning by month for large-scale deployments.
    """

    __tablename__ = "usage_logs"

    # Use auto-increment integer ID for better write performance
    # UUID is included as request_id for external reference
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Timestamp with index for time-based queries
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Foreign keys
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_key_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Request identification
    request_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique request identifier for tracing",
    )

    # Model information
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Virtual model name used in request",
    )
    real_model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Actual model name at provider",
    )
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Provider name",
    )

    # Token usage
    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Cost calculation
    input_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=Decimal("0"),
        comment="Cost for input tokens in USD",
    )
    output_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=Decimal("0"),
        comment="Cost for output tokens in USD",
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=Decimal("0"),
        comment="Total cost in USD",
    )

    # Performance metrics
    latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Total request latency in milliseconds",
    )
    time_to_first_token_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Time to first token for streaming requests",
    )

    # Status
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus),
        nullable=False,
        default=RequestStatus.SUCCESS,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Request/Response metadata (for debugging, not full content)
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Request metadata (model, temperature, etc.)",
    )
    response_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Response metadata (finish_reason, etc.)",
    )

    # Client information
    client_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    # Streaming info
    is_streaming: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship("Tenant")
    api_key: Mapped["APIKey | None"] = relationship("APIKey", back_populates="usage_logs")
    channel: Mapped["Channel | None"] = relationship("Channel", back_populates="usage_logs")

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_usage_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_usage_logs_api_key_created", "api_key_id", "created_at"),
        Index("ix_usage_logs_channel_created", "channel_id", "created_at"),
        Index("ix_usage_logs_model_created", "model_name", "created_at"),
        Index("ix_usage_logs_status_created", "status", "created_at"),
    )

    def calculate_totals(self) -> None:
        """Calculate total tokens and cost."""
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.total_cost = self.input_cost + self.output_cost
