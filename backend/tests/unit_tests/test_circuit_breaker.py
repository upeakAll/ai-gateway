"""Tests for circuit breaker."""

import pytest
import asyncio
from unittest.mock import AsyncMock

from app.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    circuit_breaker,
)


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test initial circuit breaker state."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed() is True
        assert cb.is_open() is False

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Test successful call through circuit breaker."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())

        async def success_func():
            return "success"

        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_on_failures(self):
        """Test circuit opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
        cb = CircuitBreaker("test", config)

        async def failing_func():
            raise ValueError("error")

        # First failure
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        assert cb.state == CircuitState.CLOSED

        # Second failure - should open
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_rejects(self):
        """Test that open circuit rejects calls."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=60)
        cb = CircuitBreaker("test", config)
        cb.state = CircuitState.OPEN

        async def func():
            return "should not be called"

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(func)

    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        """Test recovery through half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout=0.1,
        )
        cb = CircuitBreaker("test", config)

        # Force to open state
        cb.state = CircuitState.OPEN
        cb.stats.last_failure_time = 0  # Old enough to transition

        async def success_func():
            return "success"

        # Wait for timeout
        await asyncio.sleep(0.15)

        # First successful call - transition to half-open
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN

        # Second success - should close
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test statistics retrieval."""
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        stats = cb.get_stats()

        assert stats["name"] == "test"
        assert stats["state"] == "closed"
        assert stats["total_requests"] == 0


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker decorator."""

    @pytest.mark.asyncio
    async def test_decorator(self):
        """Test circuit breaker decorator."""
        @circuit_breaker("test_decorator")
        async def func():
            return "decorated"

        result = await func()
        assert result == "decorated"
