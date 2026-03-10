"""Alerting and notification service."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable

import structlog

logger = structlog.get_logger()


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(StrEnum):
    """Types of alerts."""

    QUOTA_WARNING = "quota_warning"
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    CHANNEL_UNHEALTHY = "channel_unhealthy"
    CHANNEL_FAILED = "channel_failed"
    HIGH_LATENCY = "high_latency"
    ERROR_RATE_HIGH = "error_rate_high"
    BILLING_ISSUE = "billing_issue"
    SECURITY_ALERT = "security_alert"


@dataclass
class Alert:
    """Alert data."""

    id: str
    type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    resolved: bool = False
    resolved_at: datetime | None = None


@dataclass
class AlertRule:
    """Rule for triggering alerts."""

    name: str
    alert_type: AlertType
    severity: AlertSeverity
    condition: str  # Python expression
    cooldown_minutes: int = 5
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class AlertManager:
    """Manager for alerts and notifications."""

    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._rules: dict[str, AlertRule] = {}
        self._handlers: list[Callable[[Alert], Any]] = []
        self._cooldowns: dict[str, datetime] = {}

    def add_handler(self, handler: Callable[[Alert], Any]) -> None:
        """Add an alert handler."""
        self._handlers.append(handler)

    def remove_handler(self, handler: Callable[[Alert], Any]) -> None:
        """Remove an alert handler."""
        self._handlers.remove(handler)

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove an alert rule."""
        self._rules.pop(name, None)

    async def trigger(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        tenant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Trigger a new alert."""
        import uuid

        alert_id = str(uuid.uuid4())

        # Check cooldown
        cooldown_key = f"{alert_type.value}:{tenant_id or 'global'}"
        if cooldown_key in self._cooldowns:
            last_alert = self._cooldowns[cooldown_key]
            # Find rule to get cooldown time
            rule = self._get_rule_for_type(alert_type)
            cooldown_minutes = rule.cooldown_minutes if rule else 5

            if datetime.now(UTC) - last_alert < timedelta(minutes=cooldown_minutes):
                logger.debug(
                    "alert_cooldown",
                    alert_type=alert_type.value,
                    tenant_id=tenant_id,
                )
                # Return existing alert
                return self._alerts.get(alert_id) or Alert(
                    id=alert_id,
                    type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    tenant_id=tenant_id,
                    metadata=metadata or {},
                )

        alert = Alert(
            id=alert_id,
            type=alert_type,
            severity=severity,
            title=title,
            message=message,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        self._alerts[alert_id] = alert
        self._cooldowns[cooldown_key] = datetime.now(UTC)

        logger.info(
            "alert_triggered",
            alert_id=alert_id,
            alert_type=alert_type.value,
            severity=severity.value,
            title=title,
            tenant_id=tenant_id,
        )

        # Notify handlers
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(
                    "alert_handler_error",
                    alert_id=alert_id,
                    error=str(e),
                )

        return alert

    async def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.acknowledged = True
        alert.acknowledged_at = datetime.now(UTC)

        logger.info("alert_acknowledged", alert_id=alert_id)
        return True

    async def resolve(self, alert_id: str) -> bool:
        """Resolve an alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False

        alert.resolved = True
        alert.resolved_at = datetime.now(UTC)

        logger.info("alert_resolved", alert_id=alert_id)
        return True

    def get_alerts(
        self,
        tenant_id: str | None = None,
        severity: AlertSeverity | None = None,
        unresolved_only: bool = False,
    ) -> list[Alert]:
        """Get alerts with optional filtering."""
        alerts = list(self._alerts.values())

        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if unresolved_only:
            alerts = [a for a in alerts if not a.resolved]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def _get_rule_for_type(self, alert_type: AlertType) -> AlertRule | None:
        """Get rule for an alert type."""
        for rule in self._rules.values():
            if rule.alert_type == alert_type:
                return rule
        return None


class AnomalyDetector:
    """Detector for anomalies in usage patterns."""

    def __init__(
        self,
        latency_threshold_ms: float = 5000.0,
        error_rate_threshold: float = 0.1,
        quota_warning_threshold: float = 0.8,
    ) -> None:
        self.latency_threshold_ms = latency_threshold_ms
        self.error_rate_threshold = error_rate_threshold
        self.quota_warning_threshold = quota_warning_threshold

        self._latency_history: dict[str, list[float]] = {}
        self._error_history: dict[str, list[tuple[float, bool]]] = {}

    def record_latency(self, channel_id: str, latency_ms: float) -> None:
        """Record latency for a channel."""
        if channel_id not in self._latency_history:
            self._latency_history[channel_id] = []

        self._latency_history[channel_id].append(latency_ms)

        # Keep last 100 measurements
        if len(self._latency_history[channel_id]) > 100:
            self._latency_history[channel_id] = self._latency_history[channel_id][-100:]

    def record_request(self, channel_id: str, success: bool) -> None:
        """Record request result for a channel."""
        import time

        if channel_id not in self._error_history:
            self._error_history[channel_id] = []

        self._error_history[channel_id].append((time.time(), success))

        # Keep last hour of data
        cutoff = time.time() - 3600
        self._error_history[channel_id] = [
            (t, s) for t, s in self._error_history[channel_id] if t > cutoff
        ]

    def check_latency_anomaly(self, channel_id: str) -> dict[str, Any] | None:
        """Check for latency anomaly."""
        history = self._latency_history.get(channel_id, [])
        if len(history) < 10:
            return None

        recent_avg = sum(history[-10:]) / 10

        if recent_avg > self.latency_threshold_ms:
            return {
                "type": "high_latency",
                "channel_id": channel_id,
                "avg_latency_ms": recent_avg,
                "threshold_ms": self.latency_threshold_ms,
            }

        return None

    def check_error_rate_anomaly(self, channel_id: str) -> dict[str, Any] | None:
        """Check for high error rate."""
        history = self._error_history.get(channel_id, [])
        if len(history) < 10:
            return None

        errors = sum(1 for _, success in history if not success)
        error_rate = errors / len(history)

        if error_rate > self.error_rate_threshold:
            return {
                "type": "high_error_rate",
                "channel_id": channel_id,
                "error_rate": error_rate,
                "threshold": self.error_rate_threshold,
                "sample_size": len(history),
            }

        return None

    def check_quota_anomaly(
        self,
        tenant_id: str,
        quota_used: float,
        quota_total: float,
    ) -> dict[str, Any] | None:
        """Check for quota warning."""
        if quota_total == 0:
            return None

        usage_rate = quota_used / quota_total

        if usage_rate >= self.quota_warning_threshold:
            return {
                "type": "quota_warning",
                "tenant_id": tenant_id,
                "usage_rate": usage_rate,
                "quota_used": quota_used,
                "quota_total": quota_total,
                "threshold": self.quota_warning_threshold,
            }

        return None


# Global instances
alert_manager = AlertManager()
anomaly_detector = AnomalyDetector()


# Register default alert handlers
async def log_alert_handler(alert: Alert) -> None:
    """Log alerts."""
    log_method = {
        AlertSeverity.INFO: logger.info,
        AlertSeverity.WARNING: logger.warning,
        AlertSeverity.ERROR: logger.error,
        AlertSeverity.CRITICAL: logger.critical,
    }
    log_method.get(alert.severity, logger.info)(
        "alert",
        alert_id=alert.id,
        alert_type=alert.type.value,
        title=alert.title,
        message=alert.message,
        tenant_id=alert.tenant_id,
        metadata=alert.metadata,
    )


alert_manager.add_handler(log_alert_handler)
