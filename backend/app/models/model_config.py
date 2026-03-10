"""Model configuration for pricing and model mapping."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.channel import Channel


class ModelConfig(BaseModel):
    """Model configuration for a specific channel.

    Maps virtual model names to actual provider model names and pricing.
    """

    __tablename__ = "model_configs"

    # Foreign keys
    channel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Model names
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Virtual model name exposed to clients (e.g., 'gpt-4')",
    )
    real_model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Actual model name for the provider (e.g., 'gpt-4-0613')",
    )

    # Pricing (per 1K tokens in USD)
    input_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=Decimal("0.001000"),
        comment="Input price per 1K tokens in USD",
    )
    output_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
        default=Decimal("0.002000"),
        comment="Output price per 1K tokens in USD",
    )

    # Rate limits for this specific model
    rpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Requests per minute limit for this model",
    )
    tpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Tokens per minute limit for this model",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # Model capabilities
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    supports_functions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    max_context_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum context window size",
    )
    max_output_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum output tokens",
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="model_configs")

    def calculate_cost(
        self, prompt_tokens: int, completion_tokens: int
    ) -> Decimal:
        """Calculate cost for the given token usage.

        Args:
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            Total cost in USD
        """
        input_cost = Decimal(prompt_tokens) * self.input_price / 1000
        output_cost = Decimal(completion_tokens) * self.output_price / 1000
        return input_cost + output_cost

    def __repr__(self) -> str:
        return f"<ModelConfig({self.model_name} -> {self.real_model_name})>"
