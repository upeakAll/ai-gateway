"""Resilience module for fault tolerance."""

from app.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    CircuitState,
    circuit_breaker,
    circuit_breaker_registry,
)
from app.resilience.fallback import (
    CacheBasedFallback,
    CachedResponse,
    CompositeFallback,
    DefaultValueFallback,
    FallbackConfig,
    FallbackExecutor,
    FallbackHandler,
    FallbackStrategy,
    FunctionFallback,
    ModelDegradationFallback,
    model_degradation,
    with_fallback,
)
from app.resilience.health_check import (
    ActiveHealthChecker,
    HealthCheckConfig,
    HealthChecker,
    HealthCheckResult,
    HealthCheckScheduler,
    HealthCheckType,
    HybridHealthChecker,
    PassiveHealthChecker,
    health_check_scheduler,
)
from app.resilience.retry import (
    RetryConfig,
    RetryExecutor,
    RetryStrategy,
    default_retry_executor,
    with_retry,
)

__all__ = [
    # Retry
    "RetryStrategy",
    "RetryConfig",
    "RetryExecutor",
    "with_retry",
    "default_retry_executor",
    # Circuit Breaker
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerRegistry",
    "circuit_breaker",
    "circuit_breaker_registry",
    # Fallback
    "FallbackStrategy",
    "FallbackConfig",
    "FallbackHandler",
    "CacheBasedFallback",
    "CachedResponse",
    "DefaultValueFallback",
    "FunctionFallback",
    "CompositeFallback",
    "FallbackExecutor",
    "with_fallback",
    "ModelDegradationFallback",
    "model_degradation",
    # Health Check
    "HealthCheckType",
    "HealthCheckResult",
    "HealthCheckConfig",
    "HealthChecker",
    "ActiveHealthChecker",
    "PassiveHealthChecker",
    "HybridHealthChecker",
    "HealthCheckScheduler",
    "health_check_scheduler",
]
