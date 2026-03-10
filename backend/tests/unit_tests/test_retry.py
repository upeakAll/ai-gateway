"""Tests for retry strategy."""

import pytest
import asyncio
from unittest.mock import AsyncMock

from app.resilience.retry import (
    RetryConfig,
    RetryExecutor,
    RetryStrategy,
    with_retry,
)


class TestRetryConfig:
    """Tests for retry configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.strategy == RetryStrategy.EXPONENTIAL_JITTER
        assert config.base_delay == 0.5

    def test_calculate_delay_fixed(self):
        """Test fixed delay calculation."""
        config = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=1.0)
        assert config.calculate_delay(1) == 1.0
        assert config.calculate_delay(2) == 1.0
        assert config.calculate_delay(3) == 1.0

    def test_calculate_delay_linear(self):
        """Test linear delay calculation."""
        config = RetryConfig(strategy=RetryStrategy.LINEAR, base_delay=1.0)
        assert config.calculate_delay(1) == 1.0
        assert config.calculate_delay(2) == 2.0
        assert config.calculate_delay(3) == 3.0

    def test_calculate_delay_exponential(self):
        """Test exponential delay calculation."""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            exponential_base=2.0,
        )
        assert config.calculate_delay(1) == 1.0
        assert config.calculate_delay(2) == 2.0
        assert config.calculate_delay(3) == 4.0

    def test_calculate_delay_max(self):
        """Test max delay limit."""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=10.0,
            max_delay=100.0,
        )
        # Would be 1000 without max
        assert config.calculate_delay(3) == 100.0

    def test_should_retry_retryable_exception(self):
        """Test retry decision for retryable exceptions."""
        config = RetryConfig()
        assert config.should_retry(exception=TimeoutError()) is True
        assert config.should_retry(exception=ConnectionError()) is True

    def test_should_retry_non_retryable(self):
        """Test retry decision for non-retryable exceptions."""
        config = RetryConfig()
        assert config.should_retry(exception=ValueError()) is False


class TestRetryExecutor:
    """Tests for retry executor."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful execution without retry."""
        call_count = 0

        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        executor = RetryExecutor(RetryConfig(max_attempts=3))
        result = await executor.execute(success_func)

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry on failure."""
        call_count = 0

        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "success"

        config = RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.FIXED,
            base_delay=0.01,  # Fast for testing
        )
        executor = RetryExecutor(config)
        result = await executor.execute(failing_func)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded(self):
        """Test that max attempts is respected."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("always fails")

        config = RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.FIXED,
            base_delay=0.01,
        )
        executor = RetryExecutor(config)

        with pytest.raises(TimeoutError):
            await executor.execute(always_fail)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_decorator(self):
        """Test retry decorator."""
        call_count = 0

        @with_retry(max_attempts=2, strategy=RetryStrategy.FIXED, base_delay=0.01)
        async def decorated_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError()
            return "ok"

        result = await decorated_func()
        assert result == "ok"
        assert call_count == 2
