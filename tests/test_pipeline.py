"""Integration tests for the conversion pipeline."""

from pathlib import Path
from tempfile import TemporaryDirectory

from lxml import etree

from app.core.extraction.xml_extractor import XMLExtractor
from app.core.generation.cii_generator import CIIGenerator
from app.core.pipeline import ConversionPipeline
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile


class TestCIIGenerator:
    """Tests for CII-XML generation via drafthorse."""

    def test_generate_en16931_xml(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert len(xml) > 0
        root = etree.fromstring(xml)
        # Check root element is CrossIndustryInvoice
        assert root.tag.endswith("CrossIndustryInvoice")

    def test_xml_contains_seller_name(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert b"Muster GmbH" in xml

    def test_xml_contains_buyer_name(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert "Käufer AG".encode("utf-8") in xml

    def test_xml_contains_invoice_number(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert b"RE-2026-001" in xml

    def test_xml_contains_line_items(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert b"Beratungsleistung" in xml
        assert b"Reisekosten" in xml

    def test_xml_contains_tax_info(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        assert b"DE123456789" in xml  # VAT ID
        assert b"332.50" in xml  # Tax amount

    def test_xml_xsd_validation_passes(self, sample_invoice: Invoice) -> None:
        """Drafthorse serialize() runs XSD validation – so if it succeeds
        without exception, the XML is XSD-valid."""
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()  # raises if XSD invalid
        assert len(xml) > 100


class TestConversionPipeline:
    """Tests for the full conversion pipeline."""

    def test_convert_to_zugferd_pdf(self, sample_invoice: Invoice) -> None:
        pipeline = ConversionPipeline()
        result = pipeline.convert(sample_invoice)

        assert result.success, f"Pipeline errors: {result.errors}"
        assert result.xml_bytes is not None
        assert len(result.xml_bytes) > 0
        assert result.pdf_bytes is not None
        assert len(result.pdf_bytes) > 0
        # PDF starts with %PDF
        assert result.pdf_bytes[:5] == b"%PDF-"

    def test_convert_to_xrechnung_cii(self, sample_invoice: Invoice) -> None:
        inv = sample_invoice.model_copy(
            update={"output_format": OutputFormat.XRECHNUNG_CII}
        )
        pipeline = ConversionPipeline()
        result = pipeline.convert(inv)

        assert result.success
        assert result.xml_bytes is not None
        assert len(result.xml_bytes) > 0
        # No PDF expected for pure XML output
        assert result.pdf_bytes is None

    def test_convert_to_file(self, sample_invoice: Invoice) -> None:
        pipeline = ConversionPipeline()

        with TemporaryDirectory() as tmpdir:
            result, out_path = pipeline.convert_to_file(
                sample_invoice, Path(tmpdir)
            )
            assert result.success
            assert out_path.exists()
            assert out_path.suffix == ".pdf"
            assert out_path.stat().st_size > 0

    def test_convert_cii_to_file(self, sample_invoice: Invoice) -> None:
        inv = sample_invoice.model_copy(
            update={"output_format": OutputFormat.XRECHNUNG_CII}
        )
        pipeline = ConversionPipeline()

        with TemporaryDirectory() as tmpdir:
            result, out_path = pipeline.convert_to_file(inv, Path(tmpdir))
            assert result.success
            assert out_path.exists()
            assert out_path.suffix == ".xml"


class TestXMLExtractor:
    """Tests for XML extraction / roundtrip."""

    def test_roundtrip_xml(self, sample_invoice: Invoice) -> None:
        """Generate XML, then extract it back – key fields must match."""
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        extractor = XMLExtractor()
        restored = extractor.extract_from_xml(xml)

        assert restored.invoice_number == sample_invoice.invoice_number
        assert restored.seller.name == sample_invoice.seller.name
        assert restored.buyer.name == sample_invoice.buyer.name
        assert restored.totals.gross_amount == sample_invoice.totals.gross_amount
        assert restored.totals.net_amount == sample_invoice.totals.net_amount
        assert len(restored.lines) == len(sample_invoice.lines)

    def test_roundtrip_line_items(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        extractor = XMLExtractor()
        restored = extractor.extract_from_xml(xml)

        for orig, rest in zip(sample_invoice.lines, restored.lines):
            assert rest.description == orig.description
            assert rest.quantity == orig.quantity
            assert rest.unit_price == orig.unit_price
            assert rest.line_net_amount == orig.line_net_amount

    def test_roundtrip_payment(self, sample_invoice: Invoice) -> None:
        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        extractor = XMLExtractor()
        restored = extractor.extract_from_xml(xml)

        assert restored.payment.iban == sample_invoice.payment.iban
        assert restored.payment.payment_reference == sample_invoice.payment.payment_reference


class TestFullRoundtrip:
    """End-to-end: Invoice → ZUGFeRD PDF → extract back → compare."""

    def test_pdf_roundtrip(self, sample_invoice: Invoice) -> None:
        """Generate a ZUGFeRD PDF, then extract the invoice data back."""
        pipeline = ConversionPipeline()
        result = pipeline.convert(sample_invoice)
        assert result.success and result.pdf_bytes

        # Write to temp file and extract
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test.pdf"
            pdf_path.write_bytes(result.pdf_bytes)

            extractor = XMLExtractor()
            restored = extractor.extract_from_pdf(pdf_path)

        assert restored.invoice_number == sample_invoice.invoice_number
        assert restored.seller.name == sample_invoice.seller.name
        assert restored.totals.gross_amount == sample_invoice.totals.gross_amount
