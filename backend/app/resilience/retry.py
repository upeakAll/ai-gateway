"""Retry strategy with exponential backoff."""

import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

import structlog

from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError

logger = structlog.get_logger()

T = TypeVar("T")


class RetryStrategy(Enum):
    """Retry strategy types."""

    FIXED = "fixed"  # Fixed interval
    LINEAR = "linear"  # Linearly increasing
    EXPONENTIAL = "exponential"  # Exponential backoff
    EXPONENTIAL_JITTER = "exponential_jitter"  # Exponential with jitter


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    base_delay: float = 0.5  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter_factor: float = 0.1  # 10% jitter

    # Exceptions that should trigger retry
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            AdapterTimeoutError,
            ConnectionError,
            TimeoutError,
        )
    )

    # HTTP status codes that should trigger retry
    retryable_status_codes: tuple[int, ...] = field(
        default_factory=lambda: (429, 500, 502, 503, 504)
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number."""
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay

        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt

        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (self.exponential_base ** (attempt - 1))

        elif self.strategy == RetryStrategy.EXPONENTIAL_JITTER:
            base_delay = self.base_delay * (self.exponential_base ** (attempt - 1))
            jitter = base_delay * self.jitter_factor * random.random()
            delay = base_delay + jitter

        else:
            delay = self.base_delay

        return min(delay, self.max_delay)

    def should_retry(
        self,
        exception: Exception | None = None,
        status_code: int | None = None,
    ) -> bool:
        """Determine if a retry should be attempted."""
        if exception:
            # Check for rate limit with retry-after
            if isinstance(exception, AdapterRateLimitError):
                return exception.retry_after is not None

            # Check against retryable exceptions
            if isinstance(exception, self.retryable_exceptions):
                return True

        if status_code and status_code in self.retryable_status_codes:
            return True

        return False


class RetryExecutor:
    """Executor that wraps functions with retry logic."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig(
            max_attempts=settings.retry_max_attempts,
            base_delay=settings.retry_backoff_factor,
        )

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            Exception: Last exception after all retries exhausted
        """
        last_exception: Exception | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return await func(*args, **kwargs)

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if attempt == self.config.max_attempts:
                    logger.error(
                        "retry_exhausted",
                        attempt=attempt,
                        max_attempts=self.config.max_attempts,
                        error=str(e),
                    )
                    raise

                if not self.config.should_retry(exception=e):
                    logger.debug(
                        "retry_not_allowed",
                        error_type=type(e).__name__,
                    )
                    raise

                # Calculate and apply delay
                delay = self.config.calculate_delay(attempt)

                # Handle rate limit retry-after
                if isinstance(e, AdapterRateLimitError) and e.retry_after:
                    delay = max(delay, e.retry_after)

                logger.warning(
                    "retry_attempt",
                    attempt=attempt,
                    max_attempts=self.config.max_attempts,
                    delay_seconds=delay,
                    error=str(e),
                )

                await asyncio.sleep(delay)

        # Should never reach here, but for type safety
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry executor failed unexpectedly")

    def wrap(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap function with retry logic."""

        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await self.execute(func, *args, **kwargs)

        return wrapper


# Default retry executor
default_retry_executor = RetryExecutor()


def with_retry(
    max_attempts: int = 3,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER,
    base_delay: float = 0.5,
    **kwargs: Any,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory for retry logic.

    Usage:
        @with_retry(max_attempts=3)
        async def my_function():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        strategy=strategy,
        base_delay=base_delay,
        **kwargs,
    )
    executor = RetryExecutor(config)
    return executor.wrap
