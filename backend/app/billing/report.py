"""Billing report generation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger()


class BillingReport:
    """Generator for billing reports."""

    def __init__(self) -> None:
        pass

    def generate_usage_report(
        self,
        tenant_id: str,
        usage_data: list[dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Generate usage report for a period."""
        # Aggregate by model
        by_model: dict[str, dict[str, Any]] = {}
        total_cost = Decimal("0")
        total_tokens = 0
        total_requests = 0

        for record in usage_data:
            model = record.get("model_name", "unknown")
            cost = Decimal(str(record.get("total_cost", 0)))
            tokens = record.get("total_tokens", 0)

            if model not in by_model:
                by_model[model] = {
                    "model": model,
                    "requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": Decimal("0"),
                }

            by_model[model]["requests"] += 1
            by_model[model]["prompt_tokens"] += record.get("prompt_tokens", 0)
            by_model[model]["completion_tokens"] += record.get("completion_tokens", 0)
            by_model[model]["total_tokens"] += tokens
            by_model[model]["cost"] += cost

            total_cost += cost
            total_tokens += tokens
            total_requests += 1

        # Aggregate by day
        by_day: dict[str, dict[str, Any]] = {}
        for record in usage_data:
            created_at = record.get("created_at")
            if isinstance(created_at, str):
                day = created_at[:10]  # YYYY-MM-DD
            else:
                day = created_at.strftime("%Y-%m-%d")

            cost = Decimal(str(record.get("total_cost", 0)))

            if day not in by_day:
                by_day[day] = {
                    "date": day,
                    "requests": 0,
                    "tokens": 0,
                    "cost": Decimal("0"),
                }

            by_day[day]["requests"] += 1
            by_day[day]["tokens"] += record.get("total_tokens", 0)
            by_day[day]["cost"] += cost

        return {
            "tenant_id": tenant_id,
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "summary": {
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost": str(total_cost),
            },
            "by_model": [
                {
                    "model": data["model"],
                    "requests": data["requests"],
                    "tokens": data["total_tokens"],
                    "cost": str(data["cost"]),
                }
                for data in by_model.values()
            ],
            "by_day": [
                {
                    "date": data["date"],
                    "requests": data["requests"],
                    "tokens": data["tokens"],
                    "cost": str(data["cost"]),
                }
                for data in sorted(by_day.values(), key=lambda x: x["date"])
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def generate_cost_analysis(
        self,
        usage_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate cost analysis report."""
        by_provider: dict[str, dict[str, Any]] = {}
        by_channel: dict[str, dict[str, Any]] = {}

        for record in usage_data:
            provider = record.get("provider", "unknown")
            channel_id = record.get("channel_id", "unknown")
            cost = Decimal(str(record.get("total_cost", 0)))

            # By provider
            if provider not in by_provider:
                by_provider[provider] = {
                    "provider": provider,
                    "requests": 0,
                    "cost": Decimal("0"),
                }
            by_provider[provider]["requests"] += 1
            by_provider[provider]["cost"] += cost

            # By channel
            if channel_id not in by_channel:
                by_channel[channel_id] = {
                    "channel_id": channel_id,
                    "requests": 0,
                    "cost": Decimal("0"),
                }
            by_channel[channel_id]["requests"] += 1
            by_channel[channel_id]["cost"] += cost

        return {
            "by_provider": [
                {
                    "provider": data["provider"],
                    "requests": data["requests"],
                    "cost": str(data["cost"]),
                }
                for data in sorted(by_provider.values(), key=lambda x: x["cost"], reverse=True)
            ],
            "by_channel": [
                {
                    "channel_id": data["channel_id"],
                    "requests": data["requests"],
                    "cost": str(data["cost"]),
                }
                for data in sorted(by_channel.values(), key=lambda x: x["cost"], reverse=True)
            ],
        }

    def export_csv(
        self,
        usage_data: list[dict[str, Any]],
        include_fields: list[str] | None = None,
    ) -> str:
        """Export usage data to CSV format."""
        import csv
        import io

        if not include_fields:
            include_fields = [
                "request_id",
                "created_at",
                "model_name",
                "provider",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "total_cost",
                "status",
            ]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=include_fields)
        writer.writeheader()

        for record in usage_data:
            row = {}
            for field in include_fields:
                value = record.get(field, "")
                if isinstance(value, Decimal):
                    value = str(value)
                elif isinstance(value, datetime):
                    value = value.isoformat()
                row[field] = value
            writer.writerow(row)

        return output.getvalue()


# Global report generator
billing_report = BillingReport()
