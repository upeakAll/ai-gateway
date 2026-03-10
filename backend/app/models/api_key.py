"""API Key and Sub-Key models."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.usage_log import UsageLog


class KeyStatus(StrEnum):
    """Status of an API key."""

    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class APIKey(BaseModel):
    """API Key entity for authentication and rate limiting."""

    __tablename__ = "api_keys"

    # Foreign keys
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Key identification
    key: Mapped[str] = mapped_column(
        String(64),  # sk-prefix + 32 hex chars
        nullable=False,
        unique=True,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the key for verification",
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Quota management (inherits from tenant if None)
    quota_total: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=True,
        comment="Key-specific quota in USD, None means use tenant quota",
    )
    quota_used: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Used quota in USD",
    )

    # Rate limits (inherits from defaults if None)
    rpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Requests per minute limit, None means no limit",
    )
    tpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Tokens per minute limit, None means no limit",
    )

    # Model access control
    allowed_models: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="List of allowed models, None means all models allowed",
    )
    denied_models: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="List of denied models, takes precedence over allowed_models",
    )

    # Status
    status: Mapped[KeyStatus] = mapped_column(
        Enum(KeyStatus),
        nullable=False,
        default=KeyStatus.ACTIVE,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Expiration date, None means never expires",
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional metadata as JSON",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")
    sub_keys: Mapped[list["SubKey"]] = relationship(
        "SubKey", back_populates="parent_key", cascade="all, delete-orphan"
    )
    usage_logs: Mapped[list["UsageLog"]] = relationship(
        "UsageLog", back_populates="api_key"
    )

    @property
    def is_active(self) -> bool:
        """Check if the key is active and not expired."""
        if self.status != KeyStatus.ACTIVE:
            return False
        if self.expires_at and self.expires_at < datetime.now(self.expires_at.tzinfo):
            return False
        return True

    @property
    def quota_remaining(self) -> Decimal | None:
        """Calculate remaining quota. None means unlimited."""
        if self.quota_total is None:
            return None  # Use tenant quota
        return max(Decimal("0"), self.quota_total - self.quota_used)

    def is_model_allowed(self, model: str) -> bool:
        """Check if the model is allowed for this key."""
        # Denied models take precedence
        if self.denied_models and model in self.denied_models:
            return False
        # If no allowed_models specified, all are allowed (except denied)
        if self.allowed_models is None:
            return True
        return model in self.allowed_models

    def use_quota(self, amount: Decimal) -> bool:
        """Deduct quota from key. Returns True if successful."""
        if self.quota_total is None:
            return True  # Use tenant quota instead
        if self.quota_remaining is not None and self.quota_remaining < amount:
            return False
        self.quota_used += amount
        return True


class SubKey(BaseModel):
    """Sub-key entity with independent quota tracking."""

    __tablename__ = "sub_keys"

    # Foreign keys
    parent_key_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Key identification
    key: Mapped[str] = mapped_column(
        String(68),  # sk-sub- prefix + 32 hex chars
        nullable=False,
        unique=True,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the key for verification",
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Independent quota tracking
    quota_total: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Sub-key quota in USD",
    )
    quota_used: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=4),
        nullable=False,
        default=Decimal("0.0000"),
        comment="Used quota in USD",
    )

    # Rate limits
    rpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Requests per minute limit, inherits from parent if None",
    )
    tpm_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Tokens per minute limit, inherits from parent if None",
    )

    # Status
    status: Mapped[KeyStatus] = mapped_column(
        Enum(KeyStatus),
        nullable=False,
        default=KeyStatus.ACTIVE,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    # Relationships
    parent_key: Mapped["APIKey"] = relationship("APIKey", back_populates="sub_keys")

    @property
    def is_active(self) -> bool:
        """Check if the sub-key is active and not expired."""
        if self.status != KeyStatus.ACTIVE:
            return False
        if not self.parent_key.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.now(self.expires_at.tzinfo):
            return False
        return True

    @property
    def quota_remaining(self) -> Decimal:
        """Calculate remaining quota."""
        return max(Decimal("0"), self.quota_total - self.quota_used)

    def use_quota(self, amount: Decimal) -> bool:
        """Deduct quota from sub-key. Returns True if successful."""
        if self.quota_remaining < amount:
            return False
        self.quota_used += amount
        return True
