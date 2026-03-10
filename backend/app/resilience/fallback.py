"""Fallback and degradation strategies."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

import structlog

from app.core.exceptions import AdapterError

logger = structlog.get_logger()

T = TypeVar("T")


class FallbackStrategy(Enum):
    """Fallback strategy types."""

    RETURN_DEFAULT = "return_default"  # Return a default value
    RETURN_CACHED = "return_cached"  # Return cached value
    CALL_FALLBACK = "call_fallback"  # Call fallback function
    RAISE_ERROR = "raise_error"  # Raise the error
    RETRY_WITH_BACKUP = "retry_with_backup"  # Try backup provider


@dataclass
class FallbackConfig:
    """Fallback configuration."""

    strategy: FallbackStrategy = FallbackStrategy.CALL_FALLBACK
    default_value: Any = None
    cache_ttl: int = 300  # Cache TTL in seconds
    fallback_func: Callable[..., Any] | None = None

    # For retry with backup
    backup_providers: list[str] = field(default_factory=list)


class FallbackHandler(ABC, Generic[T]):
    """Abstract base class for fallback handlers."""

    @abstractmethod
    async def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Handle the fallback.

        Args:
            error: The exception that triggered fallback
            context: Additional context about the failed operation

        Returns:
            Fallback value or raises exception
        """
        pass


@dataclass
class CachedResponse(Generic[T]):
    """Cached response container."""

    value: T
    timestamp: float
    ttl: int = 300

    def is_expired(self) -> bool:
        """Check if cached response is expired."""
        import time
        return time.time() - self.timestamp > self.ttl


class CacheBasedFallback(FallbackHandler[T]):
    """Fallback that returns cached responses."""

    def __init__(self, default_ttl: int = 300) -> None:
        self._cache: dict[str, CachedResponse[T]] = {}
        self._default_ttl = default_ttl

    def cache(self, key: str, value: T, ttl: int | None = None) -> None:
        """Cache a response."""
        import time
        self._cache[key] = CachedResponse(
            value=value,
            timestamp=time.time(),
            ttl=ttl or self._default_ttl,
        )

    def get_cached(self, key: str) -> T | None:
        """Get cached response if available and not expired."""
        cached = self._cache.get(key)
        if cached and not cached.is_expired():
            return cached.value
        return None

    async def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Return cached response if available."""
        context = context or {}
        cache_key = context.get("cache_key")

        if cache_key:
            cached = self.get_cached(cache_key)
            if cached is not None:
                logger.info(
                    "fallback_cache_hit",
                    cache_key=cache_key,
                )
                return cached

        # No cached value available
        logger.warning(
            "fallback_cache_miss",
            error=str(error),
        )
        raise error


class DefaultValueFallback(FallbackHandler[T]):
    """Fallback that returns a default value."""

    def __init__(self, default_value: T) -> None:
        self.default_value = default_value

    async def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Return default value."""
        logger.info(
            "fallback_default_value",
            error=str(error),
        )
        return self.default_value


class FunctionFallback(FallbackHandler[T]):
    """Fallback that calls a fallback function."""

    def __init__(self, fallback_func: Callable[..., T]) -> None:
        self.fallback_func = fallback_func

    async def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Call fallback function."""
        logger.info(
            "fallback_function_called",
            error=str(error),
        )

        if asyncio.iscoroutinefunction(self.fallback_func):
            return await self.fallback_func(error, context)
        else:
            return self.fallback_func(error, context)


class CompositeFallback(FallbackHandler[T]):
    """Composite fallback that tries multiple strategies in order."""

    def __init__(self, handlers: list[FallbackHandler[T]]) -> None:
        self.handlers = handlers

    async def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Try handlers in order until one succeeds."""
        last_error = error

        for handler in self.handlers:
            try:
                return await handler.handle(last_error, context)
            except Exception as e:
                last_error = e
                logger.debug(
                    "fallback_handler_failed",
                    handler=handler.__class__.__name__,
                    error=str(e),
                )
                continue

        # All handlers failed
        logger.error(
            "fallback_all_handlers_failed",
            error=str(last_error),
        )
        raise last_error


class FallbackExecutor(Generic[T]):
    """Executor that wraps functions with fallback logic."""

    def __init__(self, handler: FallbackHandler[T]) -> None:
        self.handler = handler

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute function with fallback.

        Args:
            func: Async function to execute
            *args: Positional arguments
            context: Context for fallback handler
            **kwargs: Keyword arguments

        Returns:
            Function result or fallback value
        """
        try:
            result = await func(*args, **kwargs)

            # Cache successful result if handler supports caching
            if isinstance(self.handler, CacheBasedFallback) and context:
                cache_key = context.get("cache_key")
                if cache_key:
                    self.handler.cache(cache_key, result)

            return result

        except Exception as e:
            logger.warning(
                "fallback_triggered",
                error=str(e),
                context=context,
            )
            return await self.handler.handle(e, context)


def with_fallback(
    handler: FallbackHandler[T] | None = None,
    default_value: T | None = None,
    fallback_func: Callable[..., T] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to add fallback to a function.

    Usage:
        @with_fallback(default_value="default response")
        async def risky_function():
            ...
    """
    if handler is None:
        if default_value is not None:
            handler = DefaultValueFallback(default_value)
        elif fallback_func is not None:
            handler = FunctionFallback(fallback_func)
        else:
            raise ValueError("Must provide handler, default_value, or fallback_func")

    executor = FallbackExecutor(handler)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await executor.execute(func, *args, **kwargs)

        return wrapper

    return decorator


# Model degradation fallback
class ModelDegradationFallback:
    """Fallback for model degradation.

    When a primary model fails, this can:
    1. Try a backup model
    2. Return a cached response
    3. Return a degraded response
    """

    def __init__(
        self,
        model_priority: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Args:
            model_priority: Map of primary model to list of fallback models
        """
        self.model_priority = model_priority or {
            "gpt-4o": ["gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
            "gpt-4-turbo": ["gpt-4", "gpt-3.5-turbo"],
            "gpt-4": ["gpt-3.5-turbo"],
            "claude-3-opus-20240229": ["claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
            "claude-3-sonnet-20240229": ["claude-3-haiku-20240307"],
        }
        self._cache_fallback = CacheBasedFallback[Any]()

    def get_fallback_model(self, primary_model: str) -> str | None:
        """Get the first available fallback model."""
        fallbacks = self.model_priority.get(primary_model, [])
        return fallbacks[0] if fallbacks else None

    def get_all_fallbacks(self, primary_model: str) -> list[str]:
        """Get all fallback models in priority order."""
        return self.model_priority.get(primary_model, [])

    async def handle_degradation(
        self,
        primary_model: str,
        error: Exception,
        adapter_call_func: Callable[..., Any],
        original_request: dict[str, Any],
    ) -> Any:
        """Handle model degradation by trying fallback models.

        Args:
            primary_model: The failed primary model
            error: The exception that caused the failure
            adapter_call_func: Function to call adapter
            original_request: Original request payload

        Returns:
            Response from fallback model or raises exception
        """
        fallbacks = self.get_all_fallbacks(primary_model)

        for fallback_model in fallbacks:
            try:
                logger.info(
                    "model_degradation_attempt",
                    primary_model=primary_model,
                    fallback_model=fallback_model,
                )

                # Modify request for fallback model
                fallback_request = {**original_request, "model": fallback_model}

                result = await adapter_call_func(fallback_request)

                logger.info(
                    "model_degradation_success",
                    primary_model=primary_model,
                    fallback_model=fallback_model,
                )

                return result

            except Exception as fallback_error:
                logger.warning(
                    "model_degradation_failed",
                    fallback_model=fallback_model,
                    error=str(fallback_error),
                )
                continue

        # All fallbacks failed
        logger.error(
            "model_degradation_exhausted",
            primary_model=primary_model,
            fallbacks_attempted=fallbacks,
            original_error=str(error),
        )
        raise error


# Global model degradation handler
model_degradation = ModelDegradationFallback()
