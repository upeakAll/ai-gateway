"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgreSQLDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Gateway"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # API Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # Database
    database_url: PostgreSQLDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_gateway"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_pool_size: int = 10

    # Security
    secret_key: str = Field(default="change-me-in-production-with-secure-random-key")
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    api_key_prefix: str = "sk-"

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default_rpm: int = 60  # requests per minute
    rate_limit_default_tpm: int = 100000  # tokens per minute
    rate_limit_window_seconds: int = 60

    # Resilience
    retry_max_attempts: int = 3
    retry_backoff_factor: float = 0.5
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    request_timeout_seconds: int = 120
    stream_timeout_seconds: int = 300

    # Billing
    billing_enabled: bool = True
    default_input_price_per_1k: float = 0.001  # $0.001 per 1K tokens
    default_output_price_per_1k: float = 0.002  # $0.002 per 1K tokens

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    # MCP
    mcp_enabled: bool = True
    mcp_sse_heartbeat_interval: int = 30

    # Metrics
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("secret_key must be at least 32 characters")
        return v

    @property
    def async_database_url(self) -> str:
        """Get async database URL."""
        return str(self.database_url)

    @property
    def redis_connection_url(self) -> str:
        """Get Redis connection URL."""
        return str(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
