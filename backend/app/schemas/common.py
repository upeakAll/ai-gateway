"""Common Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseResponse(BaseModel):
    """Base response schema with common fields."""

    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    """Error detail for API responses."""

    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail
    request_id: str | None = None


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseResponse, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """Create a paginated response."""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    environment: str
    database: str = "unknown"
    redis: str = "unknown"
    timestamp: datetime


class MetricsResponse(BaseModel):
    """Metrics response for Prometheus."""

    metrics: str
    content_type: str = "text/plain; version=0.0.4"
