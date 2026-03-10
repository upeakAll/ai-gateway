"""Billing and invoicing module."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


class BillingMode(StrEnum):
    """Billing mode."""

    PREPAID = "prepaid"
    POSTPAID = "postpaid"
    HYBRID = "hybrid"


class InvoiceStatus(StrEnum):
    """Invoice status."""

    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    """Payment status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class BillingLineItem:
    """A line item in a billing statement."""

    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Invoice:
    """Invoice for billing."""

    id: str
    tenant_id: str
    period_start: datetime
    period_end: datetime
    line_items: list[BillingLineItem]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: datetime | None = None
    paid_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def calculate_totals(self) -> None:
        """Calculate subtotal and total from line items."""
        self.subtotal = sum(item.total for item in self.line_items)
        self.total = self.subtotal + self.tax


class BillingCalculator:
    """Calculator for billing calculations."""

    def __init__(self, tax_rate: Decimal = Decimal("0.1")) -> None:
        self.tax_rate = tax_rate

    def calculate_token_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        input_price_per_1k: Decimal,
        output_price_per_1k: Decimal,
    ) -> Decimal:
        """Calculate cost for token usage."""
        input_cost = Decimal(prompt_tokens) * input_price_per_1k / 1000
        output_cost = Decimal(completion_tokens) * output_price_per_1k / 1000
        return input_cost + output_cost

    def calculate_tax(self, amount: Decimal) -> Decimal:
        """Calculate tax on amount."""
        return amount * self.tax_rate

    def generate_invoice(
        self,
        tenant_id: str,
        usage_records: list[dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
    ) -> Invoice:
        """Generate invoice from usage records."""
        import uuid

        line_items: dict[str, BillingLineItem] = {}

        for record in usage_records:
            model = record.get("model_name", "unknown")
            cost = Decimal(str(record.get("total_cost", 0)))

            if model not in line_items:
                line_items[model] = BillingLineItem(
                    description=f"API Usage - {model}",
                    quantity=Decimal("0"),
                    unit="requests",
                    unit_price=Decimal("0"),
                    total=Decimal("0"),
                    metadata={"model": model, "requests": 0},
                )

            line_items[model].quantity += 1
            line_items[model].total += cost
            line_items[model].metadata["requests"] += 1

        subtotal = sum(item.total for item in line_items.values())
        tax = self.calculate_tax(subtotal)

        invoice = Invoice(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            line_items=list(line_items.values()),
            subtotal=subtotal,
            tax=tax,
            total=subtotal + tax,
            status=InvoiceStatus.DRAFT,
            due_date=datetime.now(UTC) + timedelta(days=30),
        )

        return invoice


class QuotaManager:
    """Manager for tenant quotas."""

    def __init__(self) -> None:
        self._quotas: dict[str, dict[str, Any]] = {}

    def set_quota(
        self,
        tenant_id: str,
        total: Decimal,
        used: Decimal = Decimal("0"),
        billing_mode: BillingMode = BillingMode.PREPAID,
    ) -> None:
        """Set quota for a tenant."""
        self._quotas[tenant_id] = {
            "total": total,
            "used": used,
            "remaining": total - used,
            "billing_mode": billing_mode,
            "last_updated": datetime.now(UTC),
        }

    def get_quota(self, tenant_id: str) -> dict[str, Any] | None:
        """Get quota for a tenant."""
        return self._quotas.get(tenant_id)

    def consume(self, tenant_id: str, amount: Decimal) -> bool:
        """Consume from quota.

        Returns True if successful, False if insufficient quota.
        """
        quota = self._quotas.get(tenant_id)
        if not quota:
            return False

        if quota["billing_mode"] == BillingMode.POSTPAID:
            quota["used"] += amount
            quota["remaining"] = quota["total"] - quota["used"]
            return True

        if quota["remaining"] < amount:
            return False

        quota["used"] += amount
        quota["remaining"] -= amount
        quota["last_updated"] = datetime.now(UTC)

        return True

    def add_quota(self, tenant_id: str, amount: Decimal) -> None:
        """Add to quota (top-up)."""
        quota = self._quotas.get(tenant_id)
        if quota:
            quota["total"] += amount
            quota["remaining"] += amount
            quota["last_updated"] = datetime.now(UTC)

    def get_usage_percentage(self, tenant_id: str) -> float:
        """Get quota usage percentage."""
        quota = self._quotas.get(tenant_id)
        if not quota or quota["total"] == 0:
            return 0.0
        return float(quota["used"] / quota["total"] * 100)


class PaymentProcessor:
    """Processor for payments."""

    def __init__(self) -> None:
        self._payments: dict[str, dict[str, Any]] = {}

    async def process_payment(
        self,
        invoice_id: str,
        amount: Decimal,
        payment_method: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a payment.

        This is a placeholder - integrate with actual payment providers.
        """
        import uuid

        payment_id = str(uuid.uuid4())

        # Simulate payment processing
        payment = {
            "id": payment_id,
            "invoice_id": invoice_id,
            "amount": amount,
            "payment_method": payment_method,
            "status": PaymentStatus.COMPLETED.value,
            "processed_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        self._payments[payment_id] = payment

        logger.info(
            "payment_processed",
            payment_id=payment_id,
            invoice_id=invoice_id,
            amount=str(amount),
        )

        return payment

    async def refund_payment(
        self,
        payment_id: str,
        amount: Decimal | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Refund a payment."""
        payment = self._payments.get(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        refund_amount = amount or Decimal(str(payment["amount"]))

        payment["status"] = PaymentStatus.REFUNDED.value
        payment["refunded_at"] = datetime.now(UTC).isoformat()
        payment["refund_amount"] = str(refund_amount)
        payment["refund_reason"] = reason

        logger.info(
            "payment_refunded",
            payment_id=payment_id,
            refund_amount=str(refund_amount),
        )

        return payment


# Global instances
billing_calculator = BillingCalculator()
quota_manager = QuotaManager()
payment_processor = PaymentProcessor()
