"""Tests for billing calculations."""

import pytest
from decimal import Decimal
from datetime import datetime, UTC, timedelta

from app.billing.invoice import (
    BillingCalculator,
    BillingLineItem,
    Invoice,
    InvoiceStatus,
    QuotaManager,
    BillingMode,
)


class TestBillingCalculator:
    """Tests for billing calculator."""

    def test_calculate_token_cost(self):
        """Test token cost calculation."""
        calculator = BillingCalculator()

        cost = calculator.calculate_token_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            input_price_per_1k=Decimal("0.01"),
            output_price_per_1k=Decimal("0.03"),
        )

        # 1000 * 0.01 / 1000 + 500 * 0.03 / 1000
        # = 0.01 + 0.015 = 0.025
        assert cost == Decimal("0.025")

    def test_calculate_tax(self):
        """Test tax calculation."""
        calculator = BillingCalculator(tax_rate=Decimal("0.1"))

        tax = calculator.calculate_tax(Decimal("100.00"))
        assert tax == Decimal("10.00")

    def test_generate_invoice(self):
        """Test invoice generation."""
        calculator = BillingCalculator(tax_rate=Decimal("0.1"))

        usage_records = [
            {"model_name": "gpt-4o", "total_cost": "1.00"},
            {"model_name": "gpt-4o", "total_cost": "2.00"},
            {"model_name": "gpt-3.5-turbo", "total_cost": "0.50"},
        ]

        invoice = calculator.generate_invoice(
            tenant_id="test-tenant",
            usage_records=usage_records,
            period_start=datetime.now(UTC) - timedelta(days=30),
            period_end=datetime.now(UTC),
        )

        assert invoice.tenant_id == "test-tenant"
        assert invoice.subtotal == Decimal("3.50")
        assert invoice.tax == Decimal("0.35")
        assert invoice.total == Decimal("3.85")
        assert invoice.status == InvoiceStatus.DRAFT


class TestQuotaManager:
    """Tests for quota manager."""

    def test_set_quota(self):
        """Test setting quota."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            billing_mode=BillingMode.PREPAID,
        )

        quota = manager.get_quota("test")
        assert quota is not None
        assert quota["total"] == Decimal("100.00")
        assert quota["remaining"] == Decimal("100.00")

    def test_consume_quota(self):
        """Test consuming quota."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            billing_mode=BillingMode.PREPAID,
        )

        result = manager.consume("test", Decimal("30.00"))
        assert result is True

        quota = manager.get_quota("test")
        assert quota["used"] == Decimal("30.00")
        assert quota["remaining"] == Decimal("70.00")

    def test_consume_quota_insufficient(self):
        """Test consuming more than available quota."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            billing_mode=BillingMode.PREPAID,
        )

        result = manager.consume("test", Decimal("150.00"))
        assert result is False

    def test_consume_quota_postpaid(self):
        """Test consuming quota in postpaid mode."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            billing_mode=BillingMode.POSTPAID,
        )

        # In postpaid, should always succeed
        result = manager.consume("test", Decimal("150.00"))
        assert result is True

    def test_add_quota(self):
        """Test adding quota (top-up)."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            used=Decimal("50.00"),
        )

        manager.add_quota("test", Decimal("50.00"))

        quota = manager.get_quota("test")
        assert quota["total"] == Decimal("150.00")
        assert quota["remaining"] == Decimal("100.00")

    def test_get_usage_percentage(self):
        """Test usage percentage calculation."""
        manager = QuotaManager()
        manager.set_quota(
            tenant_id="test",
            total=Decimal("100.00"),
            used=Decimal("75.00"),
        )

        percentage = manager.get_usage_percentage("test")
        assert percentage == 75.0


class TestBillingLineItem:
    """Tests for billing line items."""

    def test_line_item_creation(self):
        """Test creating a billing line item."""
        item = BillingLineItem(
            description="API Usage - gpt-4o",
            quantity=Decimal("1000"),
            unit="tokens",
            unit_price=Decimal("0.01"),
            total=Decimal("10.00"),
        )

        assert item.description == "API Usage - gpt-4o"
        assert item.total == Decimal("10.00")
