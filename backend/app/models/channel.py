"""Channel model for LLM provider configuration."""

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.model_config import ModelConfig
    from app.models.usage_log import UsageLog


class Provider(StrEnum):
    """Supported LLM providers."""

    # OpenAI compatible
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"

    # Anthropic
    ANTHROPIC = "anthropic"

    # Cloud providers
    AWS_BEDROCK = "aws_bedrock"
    GOOGLE_VERTEX = "google_vertex"

    # Domestic (China)
    ALIYUN = "aliyun"
    BAIDU = "baidu"
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    MINIMAX = "minimax"
    MOONSHOT = "moonshot"
    BAICHUAN = "baichuan"

    # Open source / local
    OLLAMA = "ollama"
    VLLM = "vllm"
    LOCALAI = "localai"

    # Custom
    CUSTOM = "custom"


class ChannelStatus(StrEnum):
    """Status of a channel."""

    ACTIVE = "active"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"


class HealthStatus(StrEnum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class Channel(BaseModel):
    """Channel entity representing an LLM provider configuration."""

    __tablename__ = "channels"

    # Foreign keys
    tenant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL means shared channel available to all tenants",
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[Provider] = mapped_column(
        Enum(Provider), nullable=False, index=True
    )

    # API configuration
    api_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Encrypted API key for the provider",
    )
    api_base: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Custom API base URL, uses provider default if None",
    )
    api_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="API version (e.g., for Azure)",
    )

    # AWS specific
    aws_region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    aws_access_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aws_secret_access_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Routing configuration
    weight: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Weight for weighted round-robin routing",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Higher priority channels are preferred",
    )

    # Health status
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus),
        nullable=False,
        default=ChannelStatus.ACTIVE,
        index=True,
    )
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus),
        nullable=False,
        default=HealthStatus.UNKNOWN,
    )
    health_check_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Custom health check URL",
    )
    last_health_check: Mapped[str | None] = mapped_column(  # Will be datetime
        String(50),
        nullable=True,
        comment="ISO timestamp of last health check",
    )

    # Performance metrics
    avg_response_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Average response time in milliseconds",
    )
    success_rate: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Success rate as percentage (0-100)",
    )
    total_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    failed_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Circuit breaker
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Consecutive failures for circuit breaker",
    )
    circuit_breaker_open: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    circuit_breaker_opened_at: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="ISO timestamp when circuit breaker opened",
    )

    # Rate limits (provider-side)
    rpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Provider requests per minute limit",
    )
    tpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Provider tokens per minute limit",
    )

    # Pricing override
    default_input_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=True,
        comment="Default input price per 1K tokens in USD",
    )
    default_output_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=True,
        comment="Default output price per 1K tokens in USD",
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional provider-specific configuration",
    )

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="channels")
    model_configs: Mapped[list["ModelConfig"]] = relationship(
        "ModelConfig", back_populates="channel", cascade="all, delete-orphan"
    )
    usage_logs: Mapped[list["UsageLog"]] = relationship(
        "UsageLog", back_populates="channel"
    )

    @property
    def is_available(self) -> bool:
        """Check if channel is available for routing."""
        return (
            self.status == ChannelStatus.ACTIVE
            and self.health_status != HealthStatus.UNHEALTHY
            and not self.circuit_breaker_open
        )

    def record_success(self, response_time_ms: float) -> None:
        """Record a successful request."""
        self.total_requests += 1
        self.consecutive_failures = 0

        # Update average response time (exponential moving average)
        if self.avg_response_time is None:
            self.avg_response_time = response_time_ms
        else:
            alpha = 0.1  # Smoothing factor
            self.avg_response_time = (
                alpha * response_time_ms + (1 - alpha) * self.avg_response_time
            )

        # Update success rate
        if self.total_requests > 0:
            self.success_rate = (
                (self.total_requests - self.failed_requests) / self.total_requests * 100
            )

    def record_failure(self) -> None:
        """Record a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1

        # Update success rate
        if self.total_requests > 0:
            self.success_rate = (
                (self.total_requests - self.failed_requests) / self.total_requests * 100
            )

    def reset_health_metrics(self) -> None:
        """Reset health metrics (useful for testing)."""
        self.total_requests = 0
        self.failed_requests = 0
        self.consecutive_failures = 0
        self.success_rate = None
        self.avg_response_time = None
        self.health_status = HealthStatus.UNKNOWN
