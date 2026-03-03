"""Generate UBL 2.1 Invoice XML for XRechnung.

This module maps our Invoice Pydantic model to the UBL 2.1 Invoice schema
used by XRechnung and PEPPOL BIS Billing 3.0.

Unlike CII (used by ZUGFeRD), UBL uses a different XML structure with
cac/cbc namespace prefixes (Common Aggregate/Basic Components).
"""

from __future__ import annotations

from lxml import etree

from app.models.invoice import Invoice, ZUGFeRDProfile

# UBL 2.1 namespaces
_NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

_NSMAP = {
    None: _NS_INVOICE,
    "cac": _NS_CAC,
    "cbc": _NS_CBC,
}

# XRechnung customization IDs
_CUSTOMIZATION_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.EN16931: "urn:cen.eu:en16931:2017",
    ZUGFeRDProfile.XRECHNUNG: (
        "urn:cen.eu:en16931:2017#compliant#"
        "urn:xeinkauf.de:kosit:xrechnung_3.0"
    ),
}


def _cbc(parent: etree._Element, tag: str, text: str, **attribs: str) -> etree._Element:
    """Create a cbc: element with text content."""
    el = etree.SubElement(parent, f"{{{_NS_CBC}}}{tag}")
    el.text = text
    for k, v in attribs.items():
        el.set(k, v)
    return el


def _cac(parent: etree._Element, tag: str) -> etree._Element:
    """Create an empty cac: element."""
    return etree.SubElement(parent, f"{{{_NS_CAC}}}{tag}")


class UBLGenerator:
    """Generate UBL 2.1 Invoice XML from an Invoice model."""

    def __init__(self, invoice: Invoice) -> None:
        self.invoice = invoice

    def generate(self) -> bytes:
        """Generate UBL Invoice XML bytes."""
        inv = self.invoice
        currency = inv.currency_code.value

        # Root element
        root = etree.Element(f"{{{_NS_INVOICE}}}Invoice", nsmap=_NSMAP)

        # --- Header ---
        _cbc(root, "UBLVersionID", "2.1")
        _cbc(root, "CustomizationID", _CUSTOMIZATION_MAP.get(
            inv.profile, _CUSTOMIZATION_MAP[ZUGFeRDProfile.XRECHNUNG]
        ))
        _cbc(root, "ProfileID", inv.business_process)
        _cbc(root, "ID", inv.invoice_number)
        _cbc(root, "IssueDate", inv.invoice_date.isoformat())
        if inv.payment.due_date:
            _cbc(root, "DueDate", inv.payment.due_date.isoformat())
        _cbc(root, "InvoiceTypeCode", inv.invoice_type_code.value)
        if inv.note:
            _cbc(root, "Note", inv.note)
        _cbc(root, "DocumentCurrencyCode", currency)
        _cbc(root, "BuyerReference", inv.buyer_reference)

        # Order reference (BT-13)
        if inv.order_reference:
            order_ref = _cac(root, "OrderReference")
            _cbc(order_ref, "ID", inv.order_reference)

        # --- Seller (AccountingSupplierParty) ---
        self._build_supplier_party(root, inv)

        # --- Buyer (AccountingCustomerParty) ---
        self._build_customer_party(root, inv)

        # --- Payment means (BG-16) ---
        self._build_payment_means(root, inv, currency)

        # --- Payment terms (BT-20) ---
        if inv.payment.description or inv.payment.due_date:
            pt = _cac(root, "PaymentTerms")
            if inv.payment.description:
                _cbc(pt, "Note", inv.payment.description)

        # --- Tax total (BG-23) ---
        self._build_tax_total(root, inv, currency)

        # --- Legal monetary total (BG-22) ---
        self._build_monetary_total(root, inv, currency)

        # --- Invoice lines (BG-25) ---
        for line in inv.lines:
            self._build_invoice_line(root, line, currency)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

    def _build_supplier_party(self, root: etree._Element, inv: Invoice) -> None:
        supplier = _cac(root, "AccountingSupplierParty")
        party = _cac(supplier, "Party")

        if inv.seller.electronic_address:
            _cbc(party, "EndpointID", inv.seller.electronic_address,
                 schemeID=inv.seller.electronic_address_scheme)

        # Party name
        party_name = _cac(party, "PartyName")
        _cbc(party_name, "Name", inv.seller.name)

        # Postal address
        self._build_address(party, inv.seller.address)

        # Tax scheme (VAT ID)
        if inv.seller.vat_id:
            tax_scheme_wrap = _cac(party, "PartyTaxScheme")
            _cbc(tax_scheme_wrap, "CompanyID", inv.seller.vat_id)
            ts = _cac(tax_scheme_wrap, "TaxScheme")
            _cbc(ts, "ID", "VAT")

        # Tax number (FC registration)
        if inv.seller.tax_number:
            tax_scheme_wrap2 = _cac(party, "PartyTaxScheme")
            _cbc(tax_scheme_wrap2, "CompanyID", inv.seller.tax_number)
            ts2 = _cac(tax_scheme_wrap2, "TaxScheme")
            _cbc(ts2, "ID", "TAX")

        # Legal entity
        legal = _cac(party, "PartyLegalEntity")
        _cbc(legal, "RegistrationName", inv.seller.registration_name or inv.seller.name)

        # Contact
        if inv.seller.contact_name or inv.seller.contact_phone or inv.seller.contact_email:
            contact = _cac(party, "Contact")
            if inv.seller.contact_name:
                _cbc(contact, "Name", inv.seller.contact_name)
            if inv.seller.contact_phone:
                _cbc(contact, "Telephone", inv.seller.contact_phone)
            if inv.seller.contact_email:
                _cbc(contact, "ElectronicMail", inv.seller.contact_email)

    def _build_customer_party(self, root: etree._Element, inv: Invoice) -> None:
        customer = _cac(root, "AccountingCustomerParty")
        party = _cac(customer, "Party")

        if inv.buyer.electronic_address:
            _cbc(party, "EndpointID", inv.buyer.electronic_address,
                 schemeID=inv.buyer.electronic_address_scheme)

        party_name = _cac(party, "PartyName")
        _cbc(party_name, "Name", inv.buyer.name)

        self._build_address(party, inv.buyer.address)

        if inv.buyer.vat_id:
            tax_scheme_wrap = _cac(party, "PartyTaxScheme")
            _cbc(tax_scheme_wrap, "CompanyID", inv.buyer.vat_id)
            ts = _cac(tax_scheme_wrap, "TaxScheme")
            _cbc(ts, "ID", "VAT")

        legal = _cac(party, "PartyLegalEntity")
        _cbc(legal, "RegistrationName", inv.buyer.registration_name or inv.buyer.name)

        if inv.buyer.contact_name or inv.buyer.contact_phone or inv.buyer.contact_email:
            contact = _cac(party, "Contact")
            if inv.buyer.contact_name:
                _cbc(contact, "Name", inv.buyer.contact_name)
            if inv.buyer.contact_phone:
                _cbc(contact, "Telephone", inv.buyer.contact_phone)
            if inv.buyer.contact_email:
                _cbc(contact, "ElectronicMail", inv.buyer.contact_email)

    @staticmethod
    def _build_address(party: etree._Element, address) -> None:
        addr = _cac(party, "PostalAddress")
        _cbc(addr, "StreetName", address.street)
        if address.additional_line:
            _cbc(addr, "AdditionalStreetName", address.additional_line)
        _cbc(addr, "CityName", address.city)
        _cbc(addr, "PostalZone", address.postal_code)
        if address.country_subdivision:
            _cbc(addr, "CountrySubentity", address.country_subdivision)
        country = _cac(addr, "Country")
        _cbc(country, "IdentificationCode", address.country_code)

    def _build_payment_means(self, root: etree._Element, inv: Invoice, currency: str) -> None:
        pm = _cac(root, "PaymentMeans")
        _cbc(pm, "PaymentMeansCode", inv.payment.payment_means_code)
        if inv.payment.payment_reference:
            _cbc(pm, "PaymentID", inv.payment.payment_reference)

        if inv.payment.iban:
            account = _cac(pm, "PayeeFinancialAccount")
            _cbc(account, "ID", inv.payment.iban)
            if inv.payment.bank_name:
                _cbc(account, "Name", inv.payment.bank_name)
            if inv.payment.bic:
                institution = _cac(account, "FinancialInstitutionBranch")
                _cbc(institution, "ID", inv.payment.bic)

    def _build_tax_total(self, root: etree._Element, inv: Invoice, currency: str) -> None:
        tax_total = _cac(root, "TaxTotal")
        _cbc(tax_total, "TaxAmount", f"{inv.totals.tax_amount:.2f}", currencyID=currency)

        for tb in inv.tax_breakdown:
            subtotal = _cac(tax_total, "TaxSubtotal")
            _cbc(subtotal, "TaxableAmount", f"{tb.taxable_amount:.2f}", currencyID=currency)
            _cbc(subtotal, "TaxAmount", f"{tb.tax_amount:.2f}", currencyID=currency)
            cat = _cac(subtotal, "TaxCategory")
            _cbc(cat, "ID", tb.tax_category)
            _cbc(cat, "Percent", f"{tb.tax_rate:.2f}")
            ts = _cac(cat, "TaxScheme")
            _cbc(ts, "ID", "VAT")

    def _build_monetary_total(self, root: etree._Element, inv: Invoice, currency: str) -> None:
        mt = _cac(root, "LegalMonetaryTotal")
        _cbc(mt, "LineExtensionAmount", f"{inv.totals.net_amount:.2f}", currencyID=currency)
        _cbc(mt, "TaxExclusiveAmount", f"{inv.totals.net_amount:.2f}", currencyID=currency)
        _cbc(mt, "TaxInclusiveAmount", f"{inv.totals.gross_amount:.2f}", currencyID=currency)
        _cbc(mt, "AllowanceTotalAmount", f"{inv.totals.allowance_total:.2f}", currencyID=currency)
        _cbc(mt, "ChargeTotalAmount", f"{inv.totals.charge_total:.2f}", currencyID=currency)
        _cbc(mt, "PrepaidAmount", f"{inv.totals.prepaid_amount:.2f}", currencyID=currency)
        _cbc(mt, "PayableAmount", f"{inv.totals.due_amount:.2f}", currencyID=currency)

    @staticmethod
    def _build_invoice_line(
        root: etree._Element, line, currency: str
    ) -> None:
        il = _cac(root, "InvoiceLine")
        _cbc(il, "ID", line.line_id)
        _cbc(il, "InvoicedQuantity", f"{line.quantity:.2f}", unitCode=line.unit_code)
        _cbc(il, "LineExtensionAmount", f"{line.line_net_amount:.2f}", currencyID=currency)

        # Item
        item = _cac(il, "Item")
        _cbc(item, "Name", line.description)

        if line.item_number:
            seller_id = _cac(item, "SellersItemIdentification")
            _cbc(seller_id, "ID", line.item_number)

        if line.buyer_reference:
            buyer_id = _cac(item, "BuyersItemIdentification")
            _cbc(buyer_id, "ID", line.buyer_reference)

        # Tax category on the line
        tax_cat = _cac(item, "ClassifiedTaxCategory")
        _cbc(tax_cat, "ID", line.tax_category)
        _cbc(tax_cat, "Percent", f"{line.tax_rate:.2f}")
        ts = _cac(tax_cat, "TaxScheme")
        _cbc(ts, "ID", "VAT")

        # Price
        price = _cac(il, "Price")
        _cbc(price, "PriceAmount", f"{line.unit_price:.2f}", currencyID=currency)
