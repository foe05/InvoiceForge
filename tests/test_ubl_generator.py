"""Tests for UBL 2.1 XRechnung XML generation."""

from lxml import etree

from app.core.generation.ubl_generator import UBLGenerator
from app.models.invoice import OutputFormat, ZUGFeRDProfile

# UBL namespaces for XPath queries
_NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


class TestUBLGenerator:
    def test_generate_valid_xml(self, sample_invoice):
        """UBL generator produces well-formed XML."""
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        sample_invoice.profile = ZUGFeRDProfile.XRECHNUNG
        gen = UBLGenerator(sample_invoice)
        xml_bytes = gen.generate()

        assert xml_bytes
        root = etree.fromstring(xml_bytes)
        assert root.tag == "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice"

    def test_ubl_version(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        version = root.find("cbc:UBLVersionID", _NS)
        assert version is not None
        assert version.text == "2.1"

    def test_customization_id_xrechnung(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        sample_invoice.profile = ZUGFeRDProfile.XRECHNUNG
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        cust = root.find("cbc:CustomizationID", _NS)
        assert cust is not None
        assert "xrechnung" in cust.text.lower()

    def test_invoice_number(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        inv_id = root.find("cbc:ID", _NS)
        assert inv_id is not None
        assert inv_id.text == "RE-2026-001"

    def test_issue_date(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        issue_date = root.find("cbc:IssueDate", _NS)
        assert issue_date is not None
        assert issue_date.text == "2026-03-01"

    def test_currency(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        currency = root.find("cbc:DocumentCurrencyCode", _NS)
        assert currency is not None
        assert currency.text == "EUR"

    def test_seller_name(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        seller_name = root.find(
            "cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name", _NS
        )
        assert seller_name is not None
        assert seller_name.text == "Muster GmbH"

    def test_buyer_name(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        buyer_name = root.find(
            "cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name", _NS
        )
        assert buyer_name is not None
        assert buyer_name.text == "Käufer AG"

    def test_seller_vat_id(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        company_id = root.find(
            "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", _NS
        )
        assert company_id is not None
        assert company_id.text == "DE123456789"

    def test_invoice_lines(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        lines = root.findall("cac:InvoiceLine", _NS)
        assert len(lines) == 2

        # First line
        line1_id = lines[0].find("cbc:ID", _NS)
        assert line1_id.text == "1"

        item_name = lines[0].find("cac:Item/cbc:Name", _NS)
        assert item_name.text == "Beratungsleistung"

        price = lines[0].find("cac:Price/cbc:PriceAmount", _NS)
        assert price.text == "150.00"

    def test_tax_total(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        tax_total = root.find("cac:TaxTotal/cbc:TaxAmount", _NS)
        assert tax_total is not None
        assert tax_total.text == "332.50"
        assert tax_total.get("currencyID") == "EUR"

    def test_monetary_total(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        mt = root.find("cac:LegalMonetaryTotal", _NS)
        assert mt is not None

        net = mt.find("cbc:LineExtensionAmount", _NS)
        assert net.text == "1750.00"

        gross = mt.find("cbc:TaxInclusiveAmount", _NS)
        assert gross.text == "2082.50"

        payable = mt.find("cbc:PayableAmount", _NS)
        assert payable.text == "2082.50"

    def test_payment_means(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        pm = root.find("cac:PaymentMeans", _NS)
        assert pm is not None

        code = pm.find("cbc:PaymentMeansCode", _NS)
        assert code.text == "58"

        iban = pm.find("cac:PayeeFinancialAccount/cbc:ID", _NS)
        assert iban.text == "DE89370400440532013000"

    def test_due_date(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        due = root.find("cbc:DueDate", _NS)
        assert due is not None
        assert due.text == "2026-03-31"

    def test_buyer_reference(self, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        gen = UBLGenerator(sample_invoice)
        root = etree.fromstring(gen.generate())

        ref = root.find("cbc:BuyerReference", _NS)
        assert ref is not None
        assert ref.text == "-"
