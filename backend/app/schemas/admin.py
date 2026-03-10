"""Admin API schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============ Tenant ============


class TenantCreate(BaseModel):
    """Create tenant request."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    billing_mode: str = "prepaid"
    routing_strategy: str = "weighted_round_robin"
    quota_total: Decimal = Field(default=Decimal("0"), ge=0)
    description: str | None = None
    billing_email: str | None = None
    contact_email: str | None = None


class TenantUpdate(BaseModel):
    """Update tenant request."""

    name: str | None = None
    billing_mode: str | None = None
    routing_strategy: str | None = None
    fixed_channel_id: str | None = None
    quota_total: Decimal | None = None
    description: str | None = None
    billing_email: str | None = None
    contact_email: str | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    """Tenant response."""

    id: str
    name: str
    slug: str
    quota_total: Decimal
    quota_used: Decimal
    quota_remaining: Decimal
    billing_mode: str
    routing_strategy: str
    fixed_channel_id: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ API Key ============


class APIKeyCreate(BaseModel):
    """Create API key request."""

    tenant_id: str
    name: str | None = None
    quota_total: Decimal | None = None
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    allowed_models: list[str] | None = None
    expires_at: datetime | None = None
    description: str | None = None


class APIKeyResponse(BaseModel):
    """API key response (includes the key on creation)."""

    id: str
    tenant_id: str
    key: str | None = None  # Only included on creation
    name: str | None = None
    quota_total: Decimal | None = None
    quota_used: Decimal
    quota_remaining: Decimal | None = None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    allowed_models: list[str] | None = None
    status: str
    expires_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubKeyCreate(BaseModel):
    """Create sub-key request."""

    name: str | None = None
    quota_total: Decimal = Field(default=Decimal("0"), ge=0)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    description: str | None = None


class SubKeyResponse(BaseModel):
    """Sub-key response."""

    id: str
    parent_key_id: str
    key: str | None = None  # Only included on creation
    name: str | None = None
    quota_total: Decimal
    quota_used: Decimal
    quota_remaining: Decimal
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    status: str
    expires_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ Channel ============


class ChannelCreate(BaseModel):
    """Create channel request."""

    tenant_id: str | None = None  # None for shared channels
    name: str = Field(..., min_length=1, max_length=255)
    provider: str
    api_key: str
    api_base: str | None = None
    api_version: str | None = None
    weight: int = Field(default=1, ge=1)
    priority: int = Field(default=0, ge=0)
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


class ChannelUpdate(BaseModel):
    """Update channel request."""

    name: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    weight: int | None = None
    priority: int | None = None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    status: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


class ChannelResponse(BaseModel):
    """Channel response."""

    id: str
    tenant_id: str | None = None
    name: str
    provider: str
    api_base: str | None = None
    weight: int
    priority: int
    status: str
    health_status: str
    avg_response_time: float | None = None
    success_rate: float | None = None
    is_available: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChannelTestRequest(BaseModel):
    """Test channel request."""

    model: str
    prompt: str = "Hello, can you respond with 'OK'?"


class ChannelTestResponse(BaseModel):
    """Test channel response."""

    success: bool
    response_time_ms: float
    error: str | None = None
    model: str | None = None


# ============ Model Config ============


class ModelConfigCreate(BaseModel):
    """Create model config request."""

    channel_id: str
    model_name: str
    real_model_name: str
    input_price: Decimal = Field(default=Decimal("0.001"), ge=0)
    output_price: Decimal = Field(default=Decimal("0.002"), ge=0)
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    supports_streaming: bool = True
    supports_functions: bool = False
    supports_vision: bool = False
    max_context_tokens: int | None = None
    max_output_tokens: int | None = None


class ModelConfigResponse(BaseModel):
    """Model config response."""

    id: str
    channel_id: str
    model_name: str
    real_model_name: str
    input_price: Decimal
    output_price: Decimal
    is_active: bool
    supports_streaming: bool
    supports_functions: bool
    supports_vision: bool

    model_config = ConfigDict(from_attributes=True)
