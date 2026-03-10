"""Circuit breaker pattern implementation."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

import structlog

from app.config import settings

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failing, requests are rejected
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitStats:
    """Circuit breaker statistics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    last_state_change: float | None = None


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes in half-open to close
    timeout: float = 60.0  # Seconds before attempting recovery
    half_open_max_calls: int = 3  # Max calls in half-open state

    # Exceptions that count as failures
    failure_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )

    # Exceptions that should not affect circuit state
    ignored_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: ()
    )


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, circuit_name: str, retry_after: float) -> None:
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{circuit_name}' is open. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker(Generic[T]):
    """Circuit breaker implementation.

    State transitions:
    - CLOSED -> OPEN: When failures exceed threshold
    - OPEN -> HALF_OPEN: After timeout expires
    - HALF_OPEN -> CLOSED: When enough successes occur
    - HALF_OPEN -> OPEN: When any failure occurs
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout=settings.circuit_breaker_recovery_timeout,
        )
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: When circuit is open
            Exception: Original exception from function
        """
        async with self._lock:
            await self._check_state_transition()

            if self.state == CircuitState.OPEN:
                retry_after = self._get_retry_after()
                logger.warning(
                    "circuit_breaker_open",
                    circuit=self.name,
                    retry_after=retry_after,
                )
                raise CircuitBreakerOpenError(self.name, retry_after)

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    logger.warning(
                        "circuit_breaker_half_open_limit",
                        circuit=self.name,
                    )
                    raise CircuitBreakerOpenError(self.name, self._get_retry_after())
                self._half_open_calls += 1

        # Execute the function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except self.config.ignored_exceptions:
            # Don't count as success or failure
            raise

        except self.config.failure_exceptions as e:
            await self._on_failure(e)
            raise

    async def _check_state_transition(self) -> None:
        """Check and perform state transitions."""
        current_time = time.time()

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if (
                self.stats.last_failure_time
                and current_time - self.stats.last_failure_time >= self.config.timeout
            ):
                await self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    "circuit_breaker_half_open",
                    circuit=self.name,
                )

    async def _on_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self.stats.total_requests += 1
            self.stats.successful_requests += 1
            self.stats.consecutive_failures = 0
            self.stats.consecutive_successes += 1
            self.stats.last_success_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1

                if self.stats.consecutive_successes >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        "circuit_breaker_closed",
                        circuit=self.name,
                        consecutive_successes=self.stats.consecutive_successes,
                    )

    async def _on_failure(self, error: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            self.stats.total_requests += 1
            self.stats.failed_requests += 1
            self.stats.consecutive_failures += 1
            self.stats.consecutive_successes = 0
            self.stats.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls = 0
                await self._transition_to(CircuitState.OPEN)
                logger.warning(
                    "circuit_breaker_reopened",
                    circuit=self.name,
                    error=str(error),
                )

            elif self.state == CircuitState.CLOSED:
                if self.stats.consecutive_failures >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        "circuit_breaker_opened",
                        circuit=self.name,
                        consecutive_failures=self.stats.consecutive_failures,
                        error=str(error),
                    )

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        self.stats.last_state_change = time.time()

        logger.info(
            "circuit_breaker_state_change",
            circuit=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

        # Reset counters on state change
        if new_state == CircuitState.CLOSED:
            self.stats.consecutive_failures = 0
            self.stats.consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

    def _get_retry_after(self) -> float:
        """Calculate seconds until next retry attempt."""
        if not self.stats.last_failure_time:
            return self.config.timeout

        elapsed = time.time() - self.stats.last_failure_time
        return max(0, self.config.timeout - elapsed)

    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    def is_open(self) -> bool:
        """Check if circuit is open (failing)."""
        return self.state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "consecutive_failures": self.stats.consecutive_failures,
            "consecutive_successes": self.stats.consecutive_successes,
            "failure_rate": (
                self.stats.failed_requests / self.stats.total_requests * 100
                if self.stats.total_requests > 0
                else 0
            ),
            "retry_after": self._get_retry_after() if self.state == CircuitState.OPEN else 0,
        }

    async def reset(self) -> None:
        """Force reset the circuit breaker."""
        async with self._lock:
            await self._transition_to(CircuitState.CLOSED)
            self.stats = CircuitStats()
            self._half_open_calls = 0


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    _instance: "CircuitBreakerRegistry | None" = None
    _circuit_breakers: dict[str, CircuitBreaker[Any]]

    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._circuit_breakers = {}
        return cls._instance

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker[Any]:
        """Get existing circuit breaker or create new one."""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(name, config)
        return self._circuit_breakers[name]

    def get(self, name: str) -> CircuitBreaker[Any] | None:
        """Get circuit breaker by name."""
        return self._circuit_breakers.get(name)

    def get_all_stats(self) -> list[dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return [cb.get_stats() for cb in self._circuit_breakers.values()]

    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            await cb.reset()


# Global registry
circuit_breaker_registry = CircuitBreakerRegistry()


def circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to wrap function with circuit breaker.

    Usage:
        @circuit_breaker("external_api")
        async def call_external_api():
            ...
    """
    cb = circuit_breaker_registry.get_or_create(name, config)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await cb.call(func, *args, **kwargs)

        return wrapper

    return decorator
