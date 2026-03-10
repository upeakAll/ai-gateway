"""Redis client management."""

from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.config import settings


class RedisManager:
    """Redis connection manager."""

    _pool: ConnectionPool | None = None
    _client: Redis | None = None

    @classmethod
    async def get_client(cls) -> Redis:
        """Get Redis client instance."""
        if cls._client is None:
            cls._pool = ConnectionPool.from_url(
                settings.redis_connection_url,
                max_connections=settings.redis_pool_size,
                decode_responses=True,
            )
            cls._client = Redis(connection_pool=cls._pool)
        return cls._client

    @classmethod
    async def close(cls) -> None:
        """Close Redis connection."""
        if cls._client:
            await cls._client.close()
            cls._client = None
        if cls._pool:
            await cls._pool.disconnect()
            cls._pool = None


async def get_redis() -> Redis:
    """Get Redis client for dependency injection."""
    return await RedisManager.get_client()


class RateLimiter:
    """Distributed rate limiter using Redis."""

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client
        self.prefix = "ai-gateway:ratelimit"

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """Check if request is within rate limit.

        Uses sliding window algorithm with Lua script for atomicity.

        Args:
            key: Rate limit key (e.g., "tenant:123:rpm")
            max_requests: Maximum requests allowed in window
            window_seconds: Window duration in seconds

        Returns:
            Tuple of (allowed, current_count, retry_after_seconds)
        """
        redis_key = f"{self.prefix}:{key}"

        # Lua script for atomic sliding window check
        lua_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)

        -- Get current count
        local count = redis.call('ZCARD', key)

        if count < limit then
            -- Add current request
            redis.call('ZADD', key, now, now .. '-' .. math.random())
            redis.call('PEXPIRE', key, window * 1000)
            return {1, count + 1, 0}
        else
            -- Calculate retry after
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local retry_after = 0
            if #oldest > 0 then
                retry_after = math.ceil((tonumber(oldest[2]) + window * 1000 - now) / 1000)
            end
            return {0, count, retry_after}
        end
        """

        import time
        now_ms = int(time.time() * 1000)

        result = await self.redis.eval(
            lua_script,
            1,
            redis_key,
            str(max_requests),
            str(window_seconds),
            str(now_ms),
        )

        allowed = bool(result[0])
        current_count = int(result[1])
        retry_after = int(result[2])

        return allowed, current_count, retry_after

    async def check_token_limit(
        self,
        key: str,
        tokens: int,
        max_tokens: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """Check if token usage is within limit.

        Uses token bucket algorithm.

        Args:
            key: Rate limit key
            tokens: Tokens to consume
            max_tokens: Maximum tokens allowed
            window_seconds: Window for refill

        Returns:
            Tuple of (allowed, remaining_tokens)
        """
        redis_key = f"{self.prefix}:tokens:{key}"

        # Get current token count
        current = await self.redis.get(redis_key)
        current_tokens = int(current) if current else max_tokens

        if current_tokens < tokens:
            return False, current_tokens

        # Consume tokens
        new_count = current_tokens - tokens
        await self.redis.set(redis_key, new_count, ex=window_seconds)

        return True, new_count

    async def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        await self.redis.delete(f"{self.prefix}:{key}")
        await self.redis.delete(f"{self.prefix}:tokens:{key}")


class CacheManager:
    """Redis cache manager."""

    def __init__(self, redis_client: Redis, prefix: str = "ai-gateway:cache") -> None:
        self.redis = redis_client
        self.prefix = prefix

    async def get(self, key: str) -> Any | None:
        """Get cached value."""
        value = await self.redis.get(f"{self.prefix}:{key}")
        if value:
            import json
            return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        """Set cached value."""
        import json
        await self.redis.set(
            f"{self.prefix}:{key}",
            json.dumps(value),
            ex=ttl_seconds,
        )

    async def delete(self, key: str) -> None:
        """Delete cached value."""
        await self.redis.delete(f"{self.prefix}:{key}")

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        keys = []
        async for key in self.redis.scan_iter(match=f"{self.prefix}:{pattern}"):
            keys.append(key)
        if keys:
            return await self.redis.delete(*keys)
        return 0
