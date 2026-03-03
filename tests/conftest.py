"""Shared test fixtures for InvoiceForge."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    InvoiceTypeCode,
    OutputFormat,
    PaymentTerms,
    TaxBreakdown,
    ZUGFeRDProfile,
)


@pytest.fixture
def sample_invoice() -> Invoice:
    """A minimal valid EN 16931 invoice for testing."""
    return Invoice(
        invoice_number="RE-2026-001",
        invoice_date=date(2026, 3, 1),
        invoice_type_code=InvoiceTypeCode.INVOICE,
        currency_code=CurrencyCode.EUR,
        buyer_reference="-",
        seller=InvoiceParty(
            name="Muster GmbH",
            address=Address(
                street="Musterstraße 1",
                city="Berlin",
                postal_code="10115",
                country_code="DE",
            ),
            vat_id="DE123456789",
            tax_number="30/123/45678",
            electronic_address="rechnung@muster.de",
        ),
        buyer=InvoiceParty(
            name="Käufer AG",
            address=Address(
                street="Käuferweg 42",
                city="München",
                postal_code="80331",
                country_code="DE",
            ),
            electronic_address="einkauf@kaeufer.de",
        ),
        lines=[
            InvoiceLine(
                line_id="1",
                description="Beratungsleistung",
                quantity=Decimal("10.00"),
                unit_code="HUR",
                unit_price=Decimal("150.00"),
                line_net_amount=Decimal("1500.00"),
                tax_category="S",
                tax_rate=Decimal("19.00"),
            ),
            InvoiceLine(
                line_id="2",
                description="Reisekosten",
                quantity=Decimal("1.00"),
                unit_code="C62",
                unit_price=Decimal("250.00"),
                line_net_amount=Decimal("250.00"),
                tax_category="S",
                tax_rate=Decimal("19.00"),
            ),
        ],
        totals=InvoiceTotals(
            net_amount=Decimal("1750.00"),
            tax_amount=Decimal("332.50"),
            gross_amount=Decimal("2082.50"),
            due_amount=Decimal("2082.50"),
        ),
        tax_breakdown=[
            TaxBreakdown(
                tax_category="S",
                tax_rate=Decimal("19.00"),
                taxable_amount=Decimal("1750.00"),
                tax_amount=Decimal("332.50"),
            ),
        ],
        payment=PaymentTerms(
            description="Zahlbar innerhalb 30 Tagen",
            due_date=date(2026, 3, 31),
            payment_means_code="58",
            iban="DE89370400440532013000",
            payment_reference="RE-2026-001",
        ),
        profile=ZUGFeRDProfile.EN16931,
        output_format=OutputFormat.ZUGFERD_PDF,
    )
