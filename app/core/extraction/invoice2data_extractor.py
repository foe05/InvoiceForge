"""Fallback extraction using invoice2data template-matching library.

invoice2data uses YAML-based templates to extract fields from PDF invoices
via regex patterns. This provides a lightweight, no-LLM fallback for common
invoice layouts.

See: https://github.com/invoice-x/invoice2data
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    PaymentTerms,
    TaxBreakdown,
)

logger = logging.getLogger(__name__)


def _safe_decimal(val: str | float | int | None, default: str = "0") -> Decimal:
    """Safely convert a value to Decimal."""
    if val is None:
        return Decimal(default)
    try:
        return Decimal(str(val).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _safe_date(val: str | datetime | date | None) -> date:
    """Safely convert a value to date."""
    if val is None:
        return date.today()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    # Try common date formats
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return date.today()


class Invoice2DataExtractor:
    """Extract invoice data from PDFs using invoice2data template matching.

    Requires the `invoice2data` package to be installed:
        pip install invoice2data

    Optionally accepts a custom templates directory. Falls back to
    the built-in invoice2data templates if none provided.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir

    def extract(self, pdf_path: Path) -> Invoice:
        """Extract invoice data from a PDF file using invoice2data.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            An Invoice model populated with extracted data.

        Raises:
            ImportError: If invoice2data is not installed.
            ValueError: If no data could be extracted.
        """
        try:
            from invoice2data import extract_data
            from invoice2data.extract.loader import read_templates
        except ImportError:
            raise ImportError(
                "invoice2data is not installed. Install with: pip install invoice2data"
            )

        # Load templates
        if self.templates_dir and self.templates_dir.is_dir():
            templates = read_templates(str(self.templates_dir))
        else:
            templates = read_templates()

        # Extract data
        result = extract_data(str(pdf_path), templates=templates)
        if not result:
            raise ValueError(
                f"invoice2data could not extract data from {pdf_path}. "
                "No matching template found."
            )

        logger.info("invoice2data extracted data using template: %s", result.get("issuer", "unknown"))
        return self._map_to_invoice(result)

    def _map_to_invoice(self, data: dict) -> Invoice:
        """Map invoice2data extraction result to our Invoice model."""
        # Invoice number
        invoice_number = str(data.get("invoice_number", "UNKNOWN"))

        # Date
        invoice_date = _safe_date(data.get("date"))

        # Currency
        currency_str = str(data.get("currency", "EUR")).upper()
        try:
            currency = CurrencyCode(currency_str)
        except ValueError:
            currency = CurrencyCode.EUR

        # Amounts
        net_amount = _safe_decimal(data.get("amount_untaxed") or data.get("net_amount"))
        tax_amount = _safe_decimal(data.get("amount_tax") or data.get("vat"))
        gross_amount = _safe_decimal(data.get("amount") or data.get("total"))

        # If only gross is available, estimate net and tax
        if gross_amount and not net_amount:
            tax_rate = _safe_decimal(data.get("tax_rate") or data.get("vat_rate"), "19")
            if tax_rate > 0:
                net_amount = (gross_amount / (1 + tax_rate / 100)).quantize(Decimal("0.01"))
                tax_amount = gross_amount - net_amount
        elif net_amount and not gross_amount:
            gross_amount = net_amount + tax_amount

        # Seller
        seller_name = str(data.get("issuer", data.get("company", "Unknown")))
        seller = InvoiceParty(
            name=seller_name,
            address=Address(
                street=str(data.get("issuer_address", "-")),
                city=str(data.get("issuer_city", "-")),
                postal_code=str(data.get("issuer_postal_code", "-")),
                country_code=str(data.get("issuer_country", "DE")),
            ),
            vat_id=data.get("vat_number") or data.get("issuer_vat") or None,
        )

        # Buyer (often not extracted by invoice2data)
        buyer_name = str(data.get("recipient", data.get("buyer", "Käufer")))
        buyer = InvoiceParty(
            name=buyer_name,
            address=Address(street="-", city="-", postal_code="-", country_code="DE"),
        )

        # Tax rate
        tax_rate = _safe_decimal(data.get("tax_rate") or data.get("vat_rate"), "19")

        # Line items – invoice2data sometimes provides a "lines" list
        lines: list[InvoiceLine] = []
        raw_lines = data.get("lines", [])
        if isinstance(raw_lines, list):
            for idx, line in enumerate(raw_lines, start=1):
                if isinstance(line, dict):
                    lines.append(InvoiceLine(
                        line_id=str(idx),
                        description=str(line.get("description", line.get("name", f"Position {idx}"))),
                        quantity=_safe_decimal(line.get("quantity", line.get("qty")), "1"),
                        unit_code=str(line.get("unit", "C62")),
                        unit_price=_safe_decimal(line.get("unit_price", line.get("price"))),
                        line_net_amount=_safe_decimal(line.get("amount", line.get("net"))),
                        tax_category="S",
                        tax_rate=_safe_decimal(line.get("tax_rate"), str(tax_rate)),
                    ))

        # Fallback: single line with total amounts
        if not lines:
            lines.append(InvoiceLine(
                line_id="1",
                description=f"Rechnung {invoice_number}",
                quantity=Decimal("1"),
                unit_code="C62",
                unit_price=net_amount,
                line_net_amount=net_amount,
                tax_category="S",
                tax_rate=tax_rate,
            ))

        # Payment info
        iban = data.get("iban") or data.get("IBAN") or None
        bic = data.get("bic") or data.get("BIC") or None
        due_date = _safe_date(data.get("due_date")) if data.get("due_date") else None

        return Invoice(
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            currency_code=currency,
            buyer_reference="-",
            seller=seller,
            buyer=buyer,
            lines=lines,
            totals=InvoiceTotals(
                net_amount=net_amount,
                tax_amount=tax_amount,
                gross_amount=gross_amount,
                due_amount=gross_amount,
            ),
            tax_breakdown=[
                TaxBreakdown(
                    tax_category="S",
                    tax_rate=tax_rate,
                    taxable_amount=net_amount,
                    tax_amount=tax_amount,
                ),
            ],
            payment=PaymentTerms(
                due_date=due_date,
                iban=iban,
                bic=bic,
                payment_reference=data.get("payment_reference") or None,
            ),
        )
