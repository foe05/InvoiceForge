"""Generate CII-XML (Cross Industry Invoice) using drafthorse.

This module maps our Invoice Pydantic model to drafthorse's data model
and produces EN 16931 / XRechnung-compliant CII-XML.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote

from app.models.invoice import Invoice, ZUGFeRDProfile


# Map our profiles to drafthorse guideline IDs
_PROFILE_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.MINIMUM: "minimum",
    ZUGFeRDProfile.BASIC_WL: "basicwl",
    ZUGFeRDProfile.BASIC: "basic",
    ZUGFeRDProfile.EN16931: "en16931",
    ZUGFeRDProfile.EXTENDED: "extended",
    ZUGFeRDProfile.XRECHNUNG: "xrechnung",
}


class CIIGenerator:
    """Generate CII-XML from an Invoice model."""

    def __init__(self, invoice: Invoice) -> None:
        self.invoice = invoice

    def generate(self) -> bytes:
        """Generate CII-XML bytes from the invoice data."""
        inv = self.invoice
        doc = Document()

        # --- Profile / Guideline ---
        profile_key = _PROFILE_MAP.get(inv.profile, "en16931")
        doc.context.guideline_parameter.id = (
            f"urn:cen.eu:en16931:2017#compliant#"
            f"urn:zugferd.de:2p1:{profile_key}"
        )

        # --- Document header ---
        doc.header.id = inv.invoice_number
        doc.header.type_code = inv.invoice_type_code.value
        doc.header.issue_date_time = inv.invoice_date
        doc.header.name = "RECHNUNG"

        if inv.note:
            note = IncludedNote()
            note.content.add(inv.note)
            doc.header.notes.add(note)

        # --- Seller (BG-4) ---
        doc.trade.agreement.seller.name = inv.seller.name
        doc.trade.agreement.seller.address.line_one = inv.seller.address.street
        doc.trade.agreement.seller.address.city_name = inv.seller.address.city
        doc.trade.agreement.seller.address.postcode = inv.seller.address.postal_code
        doc.trade.agreement.seller.address.country_id = inv.seller.address.country_code

        if inv.seller.vat_id:
            doc.trade.agreement.seller.tax_registrations.add(
                ("VA", inv.seller.vat_id)
            )
        if inv.seller.tax_number:
            doc.trade.agreement.seller.tax_registrations.add(
                ("FC", inv.seller.tax_number)
            )

        # --- Buyer (BG-7) ---
        doc.trade.agreement.buyer.name = inv.buyer.name
        doc.trade.agreement.buyer.address.line_one = inv.buyer.address.street
        doc.trade.agreement.buyer.address.city_name = inv.buyer.address.city
        doc.trade.agreement.buyer.address.postcode = inv.buyer.address.postal_code
        doc.trade.agreement.buyer.address.country_id = inv.buyer.address.country_code

        # --- Buyer reference (BT-10) ---
        doc.trade.agreement.buyer_reference = inv.buyer_reference

        # --- Order reference (BT-13) ---
        if inv.order_reference:
            doc.trade.agreement.buyer_order.issuer_assigned_id = inv.order_reference

        # --- Payment (BG-16) ---
        doc.trade.settlement.payment_means.type_code = inv.payment.payment_means_code
        if inv.payment.iban:
            doc.trade.settlement.payment_means.payee_account.iban = inv.payment.iban
        if inv.payment.payment_reference:
            doc.trade.settlement.payment_reference = inv.payment.payment_reference

        doc.trade.settlement.currency_code = inv.currency_code.value

        if inv.payment.due_date:
            doc.trade.settlement.payment_terms.due_date = inv.payment.due_date
        if inv.payment.description:
            doc.trade.settlement.payment_terms.description = inv.payment.description

        # --- Tax breakdown (BG-23) ---
        for tb in inv.tax_breakdown:
            tax = doc.trade.settlement.trade_tax.add()
            tax.type_code = "VAT"
            tax.category_code = tb.tax_category
            tax.rate_applicable_percent = tb.tax_rate
            tax.basis_amount = tb.taxable_amount
            tax.calculated_amount = tb.tax_amount

        # --- Totals (BG-22) ---
        doc.trade.settlement.monetary_summation.line_total = inv.totals.net_amount
        doc.trade.settlement.monetary_summation.charge_total = inv.totals.charge_total
        doc.trade.settlement.monetary_summation.allowance_total = inv.totals.allowance_total
        doc.trade.settlement.monetary_summation.tax_basis_total = inv.totals.net_amount
        doc.trade.settlement.monetary_summation.tax_total = inv.totals.tax_amount
        doc.trade.settlement.monetary_summation.grand_total = inv.totals.gross_amount
        doc.trade.settlement.monetary_summation.prepaid_total = inv.totals.prepaid_amount
        doc.trade.settlement.monetary_summation.due_amount = inv.totals.due_amount

        # --- Invoice lines (BG-25) ---
        for line in inv.lines:
            li = doc.trade.items.new()
            li.document.line_id = line.line_id
            li.product.name = line.description
            if line.item_number:
                li.product.seller_assigned_id = line.item_number
            li.agreement.net.amount = line.unit_price
            li.delivery.billed_quantity = (line.quantity, line.unit_code)
            li.settlement.trade_tax.type_code = "VAT"
            li.settlement.trade_tax.category_code = line.tax_category
            li.settlement.trade_tax.rate_applicable_percent = line.tax_rate
            li.settlement.monetary_summation.total_amount = line.line_net_amount

        # Serialize to XML bytes
        xml_bytes = BytesIO()
        doc.serialize(xml_bytes)
        return xml_bytes.getvalue()
