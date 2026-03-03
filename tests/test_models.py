"""Tests for Pydantic invoice models."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    InvoiceTypeCode,
    PaymentTerms,
    TaxBreakdown,
    ZUGFeRDProfile,
)


class TestInvoiceModel:
    """Tests for the Invoice model."""

    def test_valid_invoice(self, sample_invoice: Invoice) -> None:
        """A well-formed invoice should pass validation."""
        assert sample_invoice.invoice_number == "RE-2026-001"
        assert sample_invoice.seller.name == "Muster GmbH"
        assert len(sample_invoice.lines) == 2
        assert sample_invoice.totals.gross_amount == Decimal("2082.50")

    def test_invoice_requires_lines(self) -> None:
        """Invoice must have at least one line item."""
        with pytest.raises(ValidationError, match="too_short"):
            Invoice(
                invoice_number="FAIL-001",
                invoice_date=date(2026, 1, 1),
                seller=InvoiceParty(
                    name="Seller",
                    address=Address(
                        street="A", city="B", postal_code="12345", country_code="DE"
                    ),
                ),
                buyer=InvoiceParty(
                    name="Buyer",
                    address=Address(
                        street="C", city="D", postal_code="67890", country_code="DE"
                    ),
                ),
                lines=[],  # empty – must fail
                totals=InvoiceTotals(
                    net_amount=Decimal("0"),
                    tax_amount=Decimal("0"),
                    gross_amount=Decimal("0"),
                    due_amount=Decimal("0"),
                ),
                tax_breakdown=[
                    TaxBreakdown(
                        tax_rate=Decimal("19"),
                        taxable_amount=Decimal("0"),
                        tax_amount=Decimal("0"),
                    )
                ],
            )

    def test_invoice_requires_tax_breakdown(self) -> None:
        """Invoice must have at least one tax breakdown entry."""
        with pytest.raises(ValidationError, match="too_short"):
            Invoice(
                invoice_number="FAIL-002",
                invoice_date=date(2026, 1, 1),
                seller=InvoiceParty(
                    name="Seller",
                    address=Address(
                        street="A", city="B", postal_code="12345", country_code="DE"
                    ),
                ),
                buyer=InvoiceParty(
                    name="Buyer",
                    address=Address(
                        street="C", city="D", postal_code="67890", country_code="DE"
                    ),
                ),
                lines=[
                    InvoiceLine(
                        line_id="1",
                        description="Item",
                        quantity=Decimal("1"),
                        unit_price=Decimal("100"),
                        line_net_amount=Decimal("100"),
                        tax_rate=Decimal("19"),
                    )
                ],
                totals=InvoiceTotals(
                    net_amount=Decimal("100"),
                    tax_amount=Decimal("19"),
                    gross_amount=Decimal("119"),
                    due_amount=Decimal("119"),
                ),
                tax_breakdown=[],  # empty – must fail
            )

    def test_invoice_serialization_roundtrip(self, sample_invoice: Invoice) -> None:
        """Invoice should survive JSON serialization and deserialization."""
        json_str = sample_invoice.model_dump_json()
        restored = Invoice.model_validate_json(json_str)
        assert restored.invoice_number == sample_invoice.invoice_number
        assert restored.totals.gross_amount == sample_invoice.totals.gross_amount
        assert len(restored.lines) == len(sample_invoice.lines)

    def test_default_values(self) -> None:
        """Check that sensible defaults are applied."""
        line = InvoiceLine(
            line_id="1",
            description="Test",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_net_amount=Decimal("100"),
            tax_rate=Decimal("19"),
        )
        assert line.unit_code == "C62"
        assert line.tax_category == "S"

    def test_zugferd_profiles(self) -> None:
        """All profiles should be valid enum values."""
        profiles = [p.value for p in ZUGFeRDProfile]
        assert "EN 16931" in profiles
        assert "XRECHNUNG" in profiles
        assert "MINIMUM" in profiles


class TestAddress:
    """Tests for the Address model."""

    def test_default_country(self) -> None:
        addr = Address(street="Test 1", city="Berlin", postal_code="10115")
        assert addr.country_code == "DE"

    def test_custom_country(self) -> None:
        addr = Address(
            street="Test 1", city="Wien", postal_code="1010", country_code="AT"
        )
        assert addr.country_code == "AT"
