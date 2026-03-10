"""Health check module for channels and services."""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import structlog

from app.adapters import AdapterRegistry
from app.config import settings
from app.models import Channel, HealthStatus

logger = structlog.get_logger()


class HealthCheckType(Enum):
    """Types of health checks."""

    PASSIVE = "passive"  # Based on actual request results
    ACTIVE = "active"  # Dedicated health check requests
    HYBRID = "hybrid"  # Combination of both


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    latency_ms: float
    status: HealthStatus
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class HealthCheckConfig:
    """Health check configuration."""

    # Active health check settings
    enabled: bool = True
    interval_seconds: int = 30
    timeout_seconds: int = 10
    failure_threshold: int = 3  # Failures before marking unhealthy
    success_threshold: int = 2  # Successes before marking healthy

    # Passive health check settings
    passive_window_seconds: int = 60  # Window for calculating success rate
    passive_failure_rate_threshold: float = 0.5  # 50% failure rate threshold

    # Health check endpoint
    health_check_prompt: str = "Respond with 'OK' if you receive this message."
    health_check_max_tokens: int = 5


class HealthChecker(ABC):
    """Abstract base class for health checkers."""

    @abstractmethod
    async def check(self, channel: Channel) -> HealthCheckResult:
        """Perform health check on a channel."""
        pass

    @abstractmethod
    def update_from_request(
        self,
        channel: Channel,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Update health status from actual request result."""
        pass


class ActiveHealthChecker(HealthChecker):
    """Active health checker that sends test requests."""

    def __init__(self, config: HealthCheckConfig | None = None) -> None:
        self.config = config or HealthCheckConfig()
        self._consecutive_failures: dict[str, int] = {}
        self._consecutive_successes: dict[str, int] = {}

    async def check(self, channel: Channel) -> HealthCheckResult:
        """Perform active health check by sending a test request."""
        channel_id = str(channel.id)

        try:
            start_time = time.time()

            # Create adapter for the channel
            adapter = AdapterRegistry.create_adapter(channel)

            # Import here to avoid circular dependency
            from app.adapters import (
                ChatCompletionRequest,
                ChatMessage,
                MessageRole,
            )

            # Send a simple test request
            request = ChatCompletionRequest(
                model=_get_test_model(channel),
                messages=[
                    ChatMessage(
                        role=MessageRole.USER,
                        content=self.config.health_check_prompt,
                    )
                ],
                max_tokens=self.config.health_check_max_tokens,
            )

            response = await asyncio.wait_for(
                adapter.chat_completion(request),
                timeout=self.config.timeout_seconds,
            )

            await adapter.close()

            latency_ms = (time.time() - start_time) * 1000

            # Update consecutive counters
            self._consecutive_failures[channel_id] = 0
            self._consecutive_successes[channel_id] = (
                self._consecutive_successes.get(channel_id, 0) + 1
            )

            # Determine health status
            if self._consecutive_successes[channel_id] >= self.config.success_threshold:
                status = HealthStatus.HEALTHY
            else:
                status = HealthStatus.DEGRADED

            return HealthCheckResult(
                healthy=True,
                latency_ms=latency_ms,
                status=status,
                details={
                    "response_id": response.id,
                    "model": response.model,
                },
            )

        except asyncio.TimeoutError:
            return self._handle_failure(channel, "Health check timed out")

        except Exception as e:
            return self._handle_failure(channel, str(e))

    def _handle_failure(self, channel: Channel, error: str) -> HealthCheckResult:
        """Handle health check failure."""
        channel_id = str(channel.id)

        self._consecutive_successes[channel_id] = 0
        self._consecutive_failures[channel_id] = (
            self._consecutive_failures.get(channel_id, 0) + 1
        )

        # Determine health status
        if self._consecutive_failures[channel_id] >= self.config.failure_threshold:
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED

        return HealthCheckResult(
            healthy=False,
            latency_ms=0,
            status=status,
            error=error,
        )

    def update_from_request(
        self,
        channel: Channel,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Update health status from passive monitoring (no-op for active checker)."""
        pass


class PassiveHealthChecker(HealthChecker):
    """Passive health checker based on actual request results."""

    def __init__(self, config: HealthCheckConfig | None = None) -> None:
        self.config = config or HealthCheckConfig()
        self._request_history: dict[str, list[tuple[float, bool, float]]] = {}

    async def check(self, channel: Channel) -> HealthCheckResult:
        """Check health based on historical request data."""
        channel_id = str(channel.id)
        history = self._request_history.get(channel_id, [])

        if not history:
            return HealthCheckResult(
                healthy=True,
                latency_ms=0,
                status=HealthStatus.UNKNOWN,
                details={"reason": "No request history"},
            )

        # Filter to recent window
        cutoff = time.time() - self.config.passive_window_seconds
        recent = [(t, s, l) for t, s, l in history if t > cutoff]

        if not recent:
            return HealthCheckResult(
                healthy=True,
                latency_ms=0,
                status=HealthStatus.UNKNOWN,
                details={"reason": "No recent requests"},
            )

        # Calculate metrics
        total = len(recent)
        successes = sum(1 for _, s, _ in recent if s)
        failures = total - successes
        failure_rate = failures / total if total > 0 else 0
        avg_latency = sum(l for _, _, l in recent) / total

        # Determine health
        if failure_rate >= self.config.passive_failure_rate_threshold:
            status = HealthStatus.UNHEALTHY
            healthy = False
        elif failure_rate > 0:
            status = HealthStatus.DEGRADED
            healthy = True
        else:
            status = HealthStatus.HEALTHY
            healthy = True

        return HealthCheckResult(
            healthy=healthy,
            latency_ms=avg_latency,
            status=status,
            details={
                "total_requests": total,
                "successes": successes,
                "failures": failures,
                "failure_rate": f"{failure_rate:.1%}",
            },
        )

    def update_from_request(
        self,
        channel: Channel,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Record request result for passive health tracking."""
        channel_id = str(channel.id)

        if channel_id not in self._request_history:
            self._request_history[channel_id] = []

        self._request_history[channel_id].append((time.time(), success, latency_ms))

        # Prune old entries
        cutoff = time.time() - self.config.passive_window_seconds * 2
        self._request_history[channel_id] = [
            (t, s, l) for t, s, l in self._request_history[channel_id] if t > cutoff
        ]


class HybridHealthChecker(HealthChecker):
    """Hybrid health checker combining active and passive checks."""

    def __init__(self, config: HealthCheckConfig | None = None) -> None:
        self.config = config or HealthCheckConfig()
        self.active_checker = ActiveHealthChecker(config)
        self.passive_checker = PassiveHealthChecker(config)

    async def check(self, channel: Channel) -> HealthCheckResult:
        """Perform hybrid health check."""
        # Get passive result first (fast, no external call)
        passive_result = await self.passive_checker.check(channel)

        # If passive shows healthy, trust it
        if passive_result.status == HealthStatus.HEALTHY:
            return passive_result

        # If passive shows issues, do active check
        if passive_result.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY):
            active_result = await self.active_checker.check(channel)

            # Active check overrides passive if it succeeds
            if active_result.healthy:
                return active_result

            # Otherwise return the worse of the two
            if (
                passive_result.status == HealthStatus.UNHEALTHY
                or active_result.status == HealthStatus.UNHEALTHY
            ):
                return HealthCheckResult(
                    healthy=False,
                    latency_ms=active_result.latency_ms or passive_result.latency_ms,
                    status=HealthStatus.UNHEALTHY,
                    error=active_result.error or passive_result.error,
                    details={
                        "active": active_result.details,
                        "passive": passive_result.details,
                    },
                )

        # Default to passive result
        return passive_result

    def update_from_request(
        self,
        channel: Channel,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Update both passive and active checkers."""
        self.passive_checker.update_from_request(channel, success, latency_ms)


def _get_test_model(channel: Channel) -> str:
    """Get an appropriate test model for the channel."""
    # Map providers to their simplest/cheapest models
    provider_models = {
        "openai": "gpt-3.5-turbo",
        "azure_openai": "gpt-35-turbo",
        "anthropic": "claude-3-haiku-20240307",
        "aws_bedrock": "anthropic.claude-3-haiku-20240307-v1:0",
        "aliyun": "qwen-turbo",
        "baidu": "ernie-speed-8k",
        "zhipu": "glm-4-flash",
        "deepseek": "deepseek-chat",
        "ollama": "llama3",
    }
    return provider_models.get(channel.provider.value, "gpt-3.5-turbo")


# Health check scheduler
class HealthCheckScheduler:
    """Scheduler for periodic health checks."""

    def __init__(
        self,
        checker: HealthChecker | None = None,
        config: HealthCheckConfig | None = None,
    ) -> None:
        self.checker = checker or HybridHealthChecker(config)
        self.config = config or HealthCheckConfig()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register a channel for health checks."""
        self._channels[str(channel.id)] = channel

    def unregister(self, channel_id: str) -> None:
        """Unregister a channel."""
        self._channels.pop(channel_id, None)

    async def start(self) -> None:
        """Start the health check scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("health_check_scheduler_started")

    async def stop(self) -> None:
        """Stop the health check scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("health_check_scheduler_stopped")

    async def _run_loop(self) -> None:
        """Main health check loop."""
        while self._running:
            try:
                await self._check_all_channels()
                await asyncio.sleep(self.config.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_loop_error", error=str(e))
                await asyncio.sleep(5)  # Brief pause on error

    async def _check_all_channels(self) -> None:
        """Check health of all registered channels."""
        if not self._channels:
            return

        logger.debug(
            "health_check_running",
            channel_count=len(self._channels),
        )

        # Run checks concurrently
        tasks = [
            self._check_channel(channel)
            for channel in self._channels.values()
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_channel(self, channel: Channel) -> None:
        """Check health of a single channel."""
        try:
            result = await self.checker.check(channel)

            # Update channel health status
            channel.health_status = result.status
            if result.healthy:
                channel.consecutive_failures = 0
            else:
                channel.consecutive_failures += 1

            logger.debug(
                "health_check_completed",
                channel_id=str(channel.id),
                channel_name=channel.name,
                healthy=result.healthy,
                status=result.status.value,
                latency_ms=result.latency_ms,
            )

        except Exception as e:
            logger.error(
                "health_check_channel_error",
                channel_id=str(channel.id),
                error=str(e),
            )


# Global health check scheduler
health_check_scheduler = HealthCheckScheduler()
