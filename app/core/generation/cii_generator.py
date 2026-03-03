"""Generate CII-XML (Cross Industry Invoice) using drafthorse.

This module maps our Invoice Pydantic model to drafthorse's data model
and produces EN 16931 / XRechnung-compliant CII-XML.
"""

from __future__ import annotations

from decimal import Decimal

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms as DHPaymentTerms
from drafthorse.models.tradelines import LineItem

from app.models.invoice import Invoice, ZUGFeRDProfile


# Guideline URNs per profile
_GUIDELINE_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.MINIMUM: (
        "urn:factur-x.eu:1p0:minimum"
    ),
    ZUGFeRDProfile.BASIC_WL: (
        "urn:factur-x.eu:1p0:basicwl"
    ),
    ZUGFeRDProfile.BASIC: (
        "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic"
    ),
    ZUGFeRDProfile.EN16931: (
        "urn:cen.eu:en16931:2017"
    ),
    ZUGFeRDProfile.EXTENDED: (
        "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended"
    ),
    ZUGFeRDProfile.XRECHNUNG: (
        "urn:cen.eu:en16931:2017#compliant#"
        "urn:xeinkauf.de:kosit:xrechnung_3.0"
    ),
}

# Schema names for drafthorse XSD validation
_SCHEMA_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.MINIMUM: "FACTUR-X_BASIC",
    ZUGFeRDProfile.BASIC_WL: "FACTUR-X_BASIC-WL",
    ZUGFeRDProfile.BASIC: "FACTUR-X_BASIC",
    ZUGFeRDProfile.EN16931: "FACTUR-X_EN16931",
    ZUGFeRDProfile.EXTENDED: "FACTUR-X_EXTENDED",
    ZUGFeRDProfile.XRECHNUNG: "FACTUR-X_EN16931",
}


class CIIGenerator:
    """Generate CII-XML from an Invoice model."""

    def __init__(self, invoice: Invoice) -> None:
        self.invoice = invoice

    def generate(self) -> bytes:
        """Generate CII-XML bytes from the invoice data."""
        inv = self.invoice
        doc = Document()
        currency = inv.currency_code.value

        # --- Profile / Guideline ---
        doc.context.guideline_parameter.id = _GUIDELINE_MAP.get(
            inv.profile, _GUIDELINE_MAP[ZUGFeRDProfile.EN16931]
        )

        # --- Document header ---
        doc.header.id = inv.invoice_number
        doc.header.type_code = inv.invoice_type_code.value
        doc.header.issue_date_time = inv.invoice_date

        if inv.note:
            note = IncludedNote()
            note.content.add(inv.note)
            doc.header.notes.add(note)

        # --- Seller (BG-4) ---
        seller = doc.trade.agreement.seller
        seller.name = inv.seller.name
        seller.address.line_one = inv.seller.address.street
        if inv.seller.address.additional_line:
            seller.address.line_two = inv.seller.address.additional_line
        seller.address.city_name = inv.seller.address.city
        seller.address.postcode = inv.seller.address.postal_code
        seller.address.country_id = inv.seller.address.country_code

        if inv.seller.vat_id:
            vat_reg = TaxRegistration()
            vat_reg.id = ("VA", inv.seller.vat_id)
            seller.tax_registrations.add(vat_reg)
        if inv.seller.tax_number:
            fc_reg = TaxRegistration()
            fc_reg.id = ("FC", inv.seller.tax_number)
            seller.tax_registrations.add(fc_reg)

        if inv.seller.electronic_address:
            seller.electronic_address.uri_ID = (
                inv.seller.electronic_address_scheme,
                inv.seller.electronic_address,
            )

        if inv.seller.contact_name:
            seller.contact.person_name = inv.seller.contact_name
        if inv.seller.contact_phone:
            seller.contact.telephone.number = inv.seller.contact_phone
        if inv.seller.contact_email:
            seller.contact.email.address = inv.seller.contact_email

        # --- Buyer (BG-7) ---
        buyer = doc.trade.agreement.buyer
        buyer.name = inv.buyer.name
        buyer.address.line_one = inv.buyer.address.street
        if inv.buyer.address.additional_line:
            buyer.address.line_two = inv.buyer.address.additional_line
        buyer.address.city_name = inv.buyer.address.city
        buyer.address.postcode = inv.buyer.address.postal_code
        buyer.address.country_id = inv.buyer.address.country_code

        if inv.buyer.electronic_address:
            buyer.electronic_address.uri_ID = (
                inv.buyer.electronic_address_scheme,
                inv.buyer.electronic_address,
            )

        # --- Buyer reference (BT-10) ---
        doc.trade.agreement.buyer_reference = inv.buyer_reference

        # --- Order reference (BT-13) ---
        if inv.order_reference:
            doc.trade.agreement.buyer_order.issuer_assigned_id = inv.order_reference

        # --- Settlement ---
        settlement = doc.trade.settlement
        settlement.currency_code = currency

        if inv.payment.payment_reference:
            settlement.payment_reference = inv.payment.payment_reference

        # --- Payment means (BG-16) ---
        pm = PaymentMeans()
        pm.type_code = inv.payment.payment_means_code
        if inv.payment.iban:
            pm.payee_account.iban = inv.payment.iban
        if inv.payment.bic:
            pm.payee_institution.bic = inv.payment.bic
        settlement.payment_means.add(pm)

        # --- Payment terms (BT-20) ---
        if inv.payment.description or inv.payment.due_date:
            pt = DHPaymentTerms()
            if inv.payment.description:
                pt.description = inv.payment.description
            if inv.payment.due_date:
                pt.due = inv.payment.due_date
            settlement.terms.add(pt)

        # --- Tax breakdown (BG-23) ---
        for tb in inv.tax_breakdown:
            tax = ApplicableTradeTax()
            tax.type_code = "VAT"
            tax.category_code = tb.tax_category
            tax.rate_applicable_percent = tb.tax_rate
            tax.basis_amount = tb.taxable_amount
            tax.calculated_amount = tb.tax_amount
            settlement.trade_tax.add(tax)

        # --- Totals (BG-22) – CurrencyFields take (amount, currency) tuples ---
        ms = settlement.monetary_summation
        ms.line_total = inv.totals.net_amount
        ms.charge_total = inv.totals.charge_total
        ms.allowance_total = inv.totals.allowance_total
        ms.tax_basis_total = (inv.totals.net_amount, currency)
        ms.tax_total = (inv.totals.tax_amount, currency)
        ms.grand_total = (inv.totals.gross_amount, currency)
        ms.prepaid_total = inv.totals.prepaid_amount
        ms.due_amount = inv.totals.due_amount

        # --- Invoice lines (BG-25) ---
        for line in inv.lines:
            li = LineItem()
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
            doc.trade.items.add(li)

        # Serialize to XML bytes (with XSD validation)
        schema = _SCHEMA_MAP.get(inv.profile, "FACTUR-X_EN16931")
        return doc.serialize(schema=schema)
