"""Tests for rate limiting."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.storage.redis import RateLimiter


class TestRateLimiter:
    """Tests for rate limiting."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = MagicMock()
        redis.eval = AsyncMock()
        redis.get = AsyncMock()
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, mock_redis):
        """Test rate limit check when allowed."""
        # Mock successful rate limit check
        mock_redis.eval.return_value = [1, 5, 0]  # allowed, count, retry_after

        limiter = RateLimiter(mock_redis)
        allowed, count, retry_after = await limiter.check_rate_limit(
            "test:key",
            max_requests=10,
            window_seconds=60,
        )

        assert allowed is True
        assert count == 5
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, mock_redis):
        """Test rate limit check when exceeded."""
        # Mock rate limit exceeded
        mock_redis.eval.return_value = [0, 10, 30]  # not allowed, count, retry_after

        limiter = RateLimiter(mock_redis)
        allowed, count, retry_after = await limiter.check_rate_limit(
            "test:key",
            max_requests=10,
            window_seconds=60,
        )

        assert allowed is False
        assert count == 10
        assert retry_after == 30

    @pytest.mark.asyncio
    async def test_check_token_limit_allowed(self, mock_redis):
        """Test token limit check when allowed."""
        mock_redis.get.return_value = "5000"  # 5000 tokens remaining

        limiter = RateLimiter(mock_redis)
        allowed, remaining = await limiter.check_token_limit(
            "test:key",
            tokens=100,
            max_tokens=10000,
        )

        assert allowed is True
        assert remaining == 4900

    @pytest.mark.asyncio
    async def test_check_token_limit_exceeded(self, mock_redis):
        """Test token limit check when exceeded."""
        mock_redis.get.return_value = "50"  # Only 50 tokens remaining

        limiter = RateLimiter(mock_redis)
        allowed, remaining = await limiter.check_token_limit(
            "test:key",
            tokens=100,
            max_tokens=10000,
        )

        assert allowed is False

    @pytest.mark.asyncio
    async def test_reset(self, mock_redis):
        """Test rate limit reset."""
        mock_redis.delete.return_value = 2

        limiter = RateLimiter(mock_redis)
        await limiter.reset("test:key")

        # Should delete both keys
        assert mock_redis.delete.call_count == 2


class TestRateLimitIntegration:
    """Integration tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, client, mock_redis):
        """Test rate limit headers in response."""
        # This would test the actual API response headers
        # when rate limiting is triggered
        pass
