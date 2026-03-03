"""Tests for Phase 3 features: UBL pipeline, LLM extractor, KoSIT client, UI."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from lxml import etree

from app.core.extraction.llm_extractor import LLMExtractor
from app.core.pipeline import ConversionPipeline
from app.core.validation.kosit_client import KoSITClient, KoSITResult
from app.main import app
from app.models.invoice import OutputFormat, ZUGFeRDProfile


# --- UBL Pipeline Integration ---


class TestUBLPipeline:
    """Test UBL generation through the full pipeline."""

    def test_pipeline_ubl_output(self, sample_invoice):
        """Pipeline generates UBL XML when format is XRECHNUNG_UBL."""
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        sample_invoice.profile = ZUGFeRDProfile.XRECHNUNG
        pipeline = ConversionPipeline()
        result = pipeline.convert(sample_invoice)

        assert result.success
        assert result.xml_bytes
        assert result.pdf_bytes is None  # UBL doesn't produce PDF

        root = etree.fromstring(result.xml_bytes)
        assert "Invoice" in root.tag

    def test_pipeline_cii_still_works(self, sample_invoice):
        """CII generation still works after UBL was added."""
        sample_invoice.output_format = OutputFormat.XRECHNUNG_CII
        pipeline = ConversionPipeline()
        result = pipeline.convert(sample_invoice)

        assert result.success
        assert result.xml_bytes
        assert b"CrossIndustryInvoice" in result.xml_bytes

    def test_pipeline_zugferd_still_works(self, sample_invoice):
        """ZUGFeRD PDF generation still works."""
        sample_invoice.output_format = OutputFormat.ZUGFERD_PDF
        pipeline = ConversionPipeline()
        result = pipeline.convert(sample_invoice)

        assert result.success
        assert result.xml_bytes
        assert result.pdf_bytes
        assert result.pdf_bytes[:4] == b"%PDF"


# --- KoSIT Validator Client ---


class TestKoSITClient:
    """Test KoSIT validator report parsing."""

    def test_parse_accept_report(self):
        """KoSIT report with accept recommendation is parsed correctly."""
        report = """<?xml version="1.0" encoding="UTF-8"?>
        <rep:report xmlns:rep="http://www.xoev.de/de/validator/varl/1">
            <rep:assessment>
                <rep:accept/>
            </rep:assessment>
        </rep:report>"""

        client = KoSITClient()
        result = client._parse_report(report)

        assert result.is_valid
        assert result.recommendation == "accept"
        assert len(result.errors) == 0

    def test_parse_reject_report(self):
        """KoSIT report with reject recommendation is parsed correctly."""
        report = """<?xml version="1.0" encoding="UTF-8"?>
        <rep:report xmlns:rep="http://www.xoev.de/de/validator/varl/1">
            <rep:assessment>
                <rep:reject/>
            </rep:assessment>
        </rep:report>"""

        client = KoSITClient()
        result = client._parse_report(report)

        assert not result.is_valid
        assert result.recommendation == "reject"

    def test_parse_svrl_errors(self):
        """SVRL failed-assert elements are extracted as errors."""
        report = """<?xml version="1.0" encoding="UTF-8"?>
        <rep:report xmlns:rep="http://www.xoev.de/de/validator/varl/1"
                    xmlns:svrl="http://purl.oclc.org/dml/svrl">
            <rep:assessment>
                <rep:reject/>
            </rep:assessment>
            <svrl:schematron-output>
                <svrl:failed-assert flag="error" location="/Invoice/ID">
                    <svrl:text>Invoice ID is required</svrl:text>
                </svrl:failed-assert>
                <svrl:failed-assert flag="warning" location="/Invoice/Note">
                    <svrl:text>Note is recommended</svrl:text>
                </svrl:failed-assert>
            </svrl:schematron-output>
        </rep:report>"""

        client = KoSITClient()
        result = client._parse_report(report)

        assert not result.is_valid
        assert len(result.errors) == 1
        assert "Invoice ID is required" in result.errors[0]
        assert len(result.warnings) == 1
        assert "Note is recommended" in result.warnings[0]

    def test_parse_malformed_xml_fallback(self):
        """Non-XML report falls back to text matching."""
        client = KoSITClient()
        result = client._parse_report("not xml but acceptable")

        assert result.is_valid

    def test_parse_malformed_xml_invalid(self):
        client = KoSITClient()
        result = client._parse_report("not xml and not valid")

        assert not result.is_valid


# --- LLM Extractor ---


class TestLLMExtractor:
    """Test LLM extractor JSON parsing (without actual API calls)."""

    def test_parse_valid_response(self):
        """LLM JSON response is correctly parsed into Invoice model."""
        extractor = LLMExtractor()
        json_response = json.dumps({
            "invoice_number": "RE-2026-099",
            "invoice_date": "2026-01-15",
            "currency_code": "EUR",
            "buyer_reference": "-",
            "seller": {
                "name": "Test Seller GmbH",
                "street": "Teststr. 1",
                "city": "Berlin",
                "postal_code": "10115",
                "country_code": "DE",
                "vat_id": "DE999999999",
            },
            "buyer": {
                "name": "Test Buyer AG",
                "street": "Buyerweg 2",
                "city": "Hamburg",
                "postal_code": "20095",
            },
            "lines": [
                {
                    "line_id": "1",
                    "description": "Consulting",
                    "quantity": 5,
                    "unit_price": 200,
                    "line_net_amount": 1000,
                    "tax_rate": 19,
                }
            ],
            "totals": {
                "net_amount": 1000,
                "tax_amount": 190,
                "gross_amount": 1190,
                "due_amount": 1190,
            },
            "tax_breakdown": [
                {"tax_rate": 19, "taxable_amount": 1000, "tax_amount": 190}
            ],
            "payment": {
                "iban": "DE89370400440532013000",
                "payment_means_code": "58",
            },
        })

        invoice = extractor._parse_response(json_response)

        assert invoice.invoice_number == "RE-2026-099"
        assert invoice.seller.name == "Test Seller GmbH"
        assert invoice.buyer.name == "Test Buyer AG"
        assert len(invoice.lines) == 1
        assert invoice.totals.gross_amount == 1190
        assert invoice.payment.iban == "DE89370400440532013000"

    def test_parse_response_with_markdown_fences(self):
        """Markdown code fences are stripped before parsing."""
        extractor = LLMExtractor()
        json_str = json.dumps({
            "invoice_number": "TEST-001",
            "invoice_date": "2026-01-01",
            "seller": {"name": "S", "street": "S", "city": "S", "postal_code": "00000"},
            "buyer": {"name": "B", "street": "B", "city": "B", "postal_code": "00000"},
            "lines": [{"description": "X", "quantity": 1, "unit_price": 100, "line_net_amount": 100, "tax_rate": 19}],
            "totals": {"net_amount": 100, "tax_amount": 19, "gross_amount": 119, "due_amount": 119},
        })
        wrapped = f"```json\n{json_str}\n```"

        invoice = extractor._parse_response(wrapped)
        assert invoice.invoice_number == "TEST-001"

    def test_parse_defaults_for_missing_fields(self):
        """Missing optional fields get sensible defaults."""
        extractor = LLMExtractor()
        json_response = json.dumps({
            "invoice_number": "MIN-001",
            "seller": {"name": "Seller"},
            "buyer": {"name": "Buyer"},
            "lines": [{"description": "Item", "quantity": 1, "unit_price": 100, "line_net_amount": 100}],
            "totals": {"net_amount": 100, "tax_amount": 19, "gross_amount": 119},
        })

        invoice = extractor._parse_response(json_response)
        assert invoice.invoice_number == "MIN-001"
        assert invoice.seller.address.country_code == "DE"
        assert invoice.currency_code.value == "EUR"
        assert len(invoice.tax_breakdown) == 1  # Auto-generated


# --- API: UBL Conversion ---


class TestAPIUBLConversion:
    """Test the API endpoints with UBL output."""

    @pytest.fixture
    def client(self):
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        )

    @pytest.mark.asyncio
    async def test_convert_to_ubl(self, client, sample_invoice):
        sample_invoice.output_format = OutputFormat.XRECHNUNG_UBL
        sample_invoice.profile = ZUGFeRDProfile.XRECHNUNG

        response = await client.post(
            "/api/v1/invoices/convert",
            json=json.loads(sample_invoice.model_dump_json()),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        assert data["output_format"] == "xrechnung_ubl"
        assert data["xml_base64"] is not None

    @pytest.mark.asyncio
    async def test_formats_includes_ubl(self, client):
        response = await client.get("/api/v1/invoices/formats")
        assert response.status_code == 200
        data = response.json()
        format_values = [f["value"] for f in data["output_formats"]]
        assert "xrechnung_ubl" in format_values


# --- UI Routes ---


class TestUIRoutes:
    """Test the HTMX admin UI routes return HTML."""

    @pytest.fixture
    def client(self):
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        )

    @pytest.mark.asyncio
    async def test_dashboard(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert "InvoiceForge" in response.text

    @pytest.mark.asyncio
    async def test_convert_page(self, client):
        response = await client.get("/ui/convert")
        assert response.status_code == 200
        assert "Konvertieren" in response.text

    @pytest.mark.asyncio
    async def test_extract_page(self, client):
        response = await client.get("/ui/extract")
        assert response.status_code == 200
        assert "Extrahieren" in response.text

    @pytest.mark.asyncio
    async def test_validate_page(self, client):
        response = await client.get("/ui/validate")
        assert response.status_code == 200
        assert "Validieren" in response.text
