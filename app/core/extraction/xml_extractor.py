"""Extract structured invoice data from ZUGFeRD/XRechnung XML (CII format).

Parses CII-XML (embedded in ZUGFeRD PDFs or standalone XRechnung files)
and maps it to our Invoice Pydantic model.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from facturx import get_xml_from_pdf
from lxml import etree

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

# CII namespaces
_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}


def _text(el: etree._Element | None, xpath: str) -> str:
    """Get text content from an XPath relative to element, or empty string."""
    if el is None:
        return ""
    node = el.find(xpath, namespaces=_NS)
    return (node.text or "").strip() if node is not None else ""


def _decimal(el: etree._Element | None, xpath: str) -> Decimal:
    """Get Decimal from XPath, default 0."""
    txt = _text(el, xpath)
    if not txt:
        return Decimal("0")
    try:
        return Decimal(txt)
    except InvalidOperation:
        return Decimal("0")


def _date(el: etree._Element | None, xpath: str) -> date | None:
    """Parse a CII DateTimeString (format 102 = YYYYMMDD)."""
    txt = _text(el, xpath)
    if not txt:
        return None
    try:
        return datetime.strptime(txt, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_party(party_el: etree._Element | None) -> InvoiceParty:
    """Parse a trade party element (seller or buyer)."""
    name = _text(party_el, "ram:Name")
    addr_el = party_el.find("ram:PostalTradeAddress", _NS) if party_el is not None else None

    address = Address(
        street=_text(addr_el, "ram:LineOne") or "-",
        additional_line=_text(addr_el, "ram:LineTwo") or None,
        city=_text(addr_el, "ram:CityName") or "-",
        postal_code=_text(addr_el, "ram:PostcodeCode") or "-",
        country_code=_text(addr_el, "ram:CountryID") or "DE",
    )

    # Tax registrations
    vat_id = None
    tax_number = None
    if party_el is not None:
        for reg in party_el.findall("ram:SpecifiedTaxRegistration", _NS):
            id_el = reg.find("ram:ID", _NS)
            if id_el is not None:
                scheme = id_el.get("schemeID", "")
                value = (id_el.text or "").strip()
                if scheme == "VA":
                    vat_id = value
                elif scheme == "FC":
                    tax_number = value

    # Electronic address
    e_addr = None
    e_scheme = "EM"
    if party_el is not None:
        uri_el = party_el.find("ram:URIUniversalCommunication/ram:URIID", _NS)
        if uri_el is not None:
            e_addr = (uri_el.text or "").strip()
            e_scheme = uri_el.get("schemeID", "EM")

    # Contact
    contact_el = party_el.find("ram:DefinedTradeContact", _NS) if party_el is not None else None
    contact_name = _text(contact_el, "ram:PersonName") if contact_el is not None else None
    contact_phone = None
    contact_email = None
    if contact_el is not None:
        contact_phone = _text(
            contact_el, "ram:TelephoneUniversalCommunication/ram:CompleteNumber"
        ) or None
        contact_email = _text(
            contact_el, "ram:EmailURIUniversalCommunication/ram:URIID"
        ) or None

    return InvoiceParty(
        name=name or "Unknown",
        address=address,
        vat_id=vat_id,
        tax_number=tax_number,
        electronic_address=e_addr,
        electronic_address_scheme=e_scheme,
        contact_name=contact_name or None,
        contact_phone=contact_phone,
        contact_email=contact_email,
    )


class XMLExtractor:
    """Extract Invoice data from CII-XML (ZUGFeRD / XRechnung)."""

    def extract_from_xml(self, xml_bytes: bytes) -> Invoice:
        """Parse CII-XML bytes into an Invoice model."""
        root = etree.fromstring(xml_bytes)
        return self._parse_document(root)

    def extract_from_pdf(self, pdf_path: Path) -> Invoice:
        """Extract embedded XML from a ZUGFeRD PDF and parse it."""
        pdf_bytes = pdf_path.read_bytes()
        _filename, xml_bytes = get_xml_from_pdf(pdf_bytes)
        if not xml_bytes:
            raise ValueError(f"No embedded XML found in {pdf_path}")
        return self.extract_from_xml(xml_bytes)

    def extract_from_file(self, file_path: Path) -> Invoice:
        """Auto-detect file type and extract invoice data."""
        suffix = file_path.suffix.lower()
        if suffix == ".xml":
            return self.extract_from_xml(file_path.read_bytes())
        elif suffix == ".pdf":
            return self.extract_from_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _parse_document(self, root: etree._Element) -> Invoice:
        """Parse a full CII CrossIndustryInvoice document."""
        # Header
        header = root.find("rsm:ExchangedDocument", _NS)
        invoice_number = _text(header, "ram:ID")
        type_code = _text(header, "ram:TypeCode") or "380"
        issue_date = _date(header, "ram:IssueDateTime/udt:DateTimeString")

        # Trade transaction
        trade = root.find("rsm:SupplyChainTradeTransaction", _NS)
        agreement = trade.find("ram:ApplicableHeaderTradeAgreement", _NS) if trade is not None else None
        settlement = trade.find("ram:ApplicableHeaderTradeSettlement", _NS) if trade is not None else None

        # Buyer reference
        buyer_reference = _text(agreement, "ram:BuyerReference") if agreement is not None else "-"

        # Parties
        seller_el = agreement.find("ram:SellerTradeParty", _NS) if agreement is not None else None
        buyer_el = agreement.find("ram:BuyerTradeParty", _NS) if agreement is not None else None
        seller = _parse_party(seller_el)
        buyer = _parse_party(buyer_el)

        # Currency
        currency_str = _text(settlement, "ram:InvoiceCurrencyCode") if settlement is not None else "EUR"
        try:
            currency = CurrencyCode(currency_str)
        except ValueError:
            currency = CurrencyCode.EUR

        # Payment reference
        payment_ref = _text(settlement, "ram:PaymentReference") if settlement is not None else None

        # Payment means
        pm_el = settlement.find("ram:SpecifiedTradeSettlementPaymentMeans", _NS) if settlement is not None else None
        pm_code = _text(pm_el, "ram:TypeCode") or "58"
        iban = _text(pm_el, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID") if pm_el is not None else None
        bic = _text(pm_el, "ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID") if pm_el is not None else None

        # Payment terms
        pt_el = settlement.find("ram:SpecifiedTradePaymentTerms", _NS) if settlement is not None else None
        pt_desc = _text(pt_el, "ram:Description") if pt_el is not None else None
        pt_due = _date(pt_el, "ram:DueDateDateTime/udt:DateTimeString") if pt_el is not None else None

        # Tax breakdown
        tax_breakdown: list[TaxBreakdown] = []
        if settlement is not None:
            for tax_el in settlement.findall("ram:ApplicableTradeTax", _NS):
                tax_breakdown.append(TaxBreakdown(
                    tax_category=_text(tax_el, "ram:CategoryCode") or "S",
                    tax_rate=_decimal(tax_el, "ram:RateApplicablePercent"),
                    taxable_amount=_decimal(tax_el, "ram:BasisAmount"),
                    tax_amount=_decimal(tax_el, "ram:CalculatedAmount"),
                ))

        # Monetary summation
        ms_el = settlement.find(
            "ram:SpecifiedTradeSettlementHeaderMonetarySummation", _NS
        ) if settlement is not None else None
        totals = InvoiceTotals(
            net_amount=_decimal(ms_el, "ram:LineTotalAmount"),
            tax_amount=_decimal(ms_el, "ram:TaxTotalAmount"),
            gross_amount=_decimal(ms_el, "ram:GrandTotalAmount"),
            due_amount=_decimal(ms_el, "ram:DuePayableAmount"),
            allowance_total=_decimal(ms_el, "ram:AllowanceTotalAmount"),
            charge_total=_decimal(ms_el, "ram:ChargeTotalAmount"),
            prepaid_amount=_decimal(ms_el, "ram:TotalPrepaidAmount"),
        )

        # Line items
        lines: list[InvoiceLine] = []
        if trade is not None:
            for idx, li_el in enumerate(
                trade.findall("ram:IncludedSupplyChainTradeLineItem", _NS), start=1
            ):
                doc_el = li_el.find("ram:AssociatedDocumentLineDocument", _NS)
                prod_el = li_el.find("ram:SpecifiedTradeProduct", _NS)
                agree_el = li_el.find("ram:SpecifiedLineTradeAgreement", _NS)
                deliv_el = li_el.find("ram:SpecifiedLineTradeDelivery", _NS)
                settl_el = li_el.find("ram:SpecifiedLineTradeSettlement", _NS)

                line_id = _text(doc_el, "ram:LineID") or str(idx)
                description = _text(prod_el, "ram:Name") if prod_el is not None else "Item"
                seller_id = _text(prod_el, "ram:SellerAssignedID") if prod_el is not None else None

                unit_price = _decimal(
                    agree_el,
                    "ram:NetPriceProductTradePrice/ram:ChargeAmount",
                ) if agree_el is not None else Decimal("0")

                qty_el = deliv_el.find("ram:BilledQuantity", _NS) if deliv_el is not None else None
                quantity = Decimal(qty_el.text) if qty_el is not None and qty_el.text else Decimal("0")
                unit_code = qty_el.get("unitCode", "C62") if qty_el is not None else "C62"

                line_tax_el = settl_el.find("ram:ApplicableTradeTax", _NS) if settl_el is not None else None
                tax_cat = _text(line_tax_el, "ram:CategoryCode") or "S"
                tax_rate = _decimal(line_tax_el, "ram:RateApplicablePercent")

                sum_el = settl_el.find(
                    "ram:SpecifiedTradeSettlementLineMonetarySummation", _NS
                ) if settl_el is not None else None
                net_amount = _decimal(sum_el, "ram:LineTotalAmount")

                lines.append(InvoiceLine(
                    line_id=line_id,
                    description=description,
                    quantity=quantity,
                    unit_code=unit_code,
                    unit_price=unit_price,
                    line_net_amount=net_amount,
                    tax_category=tax_cat,
                    tax_rate=tax_rate,
                    item_number=seller_id or None,
                ))

        # Ensure at least one line and one tax breakdown for model validation
        if not lines:
            lines.append(InvoiceLine(
                line_id="1", description="(extracted)", quantity=Decimal("1"),
                unit_price=totals.net_amount, line_net_amount=totals.net_amount,
                tax_rate=Decimal("19"),
            ))
        if not tax_breakdown:
            tax_breakdown.append(TaxBreakdown(
                tax_rate=Decimal("19"), taxable_amount=totals.net_amount,
                tax_amount=totals.tax_amount,
            ))

        # Map type code
        try:
            inv_type = InvoiceTypeCode(type_code)
        except ValueError:
            inv_type = InvoiceTypeCode.INVOICE

        return Invoice(
            invoice_number=invoice_number or "UNKNOWN",
            invoice_date=issue_date or date.today(),
            invoice_type_code=inv_type,
            currency_code=currency,
            buyer_reference=buyer_reference or "-",
            seller=seller,
            buyer=buyer,
            lines=lines,
            totals=totals,
            tax_breakdown=tax_breakdown,
            payment=PaymentTerms(
                description=pt_desc or None,
                due_date=pt_due,
                payment_means_code=pm_code,
                iban=iban or None,
                bic=bic or None,
                payment_reference=payment_ref or None,
            ),
            profile=ZUGFeRDProfile.EN16931,
            output_format=OutputFormat.ZUGFERD_PDF,
        )
