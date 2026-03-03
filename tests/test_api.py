"""API endpoint tests."""

from base64 import b64decode

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.invoice import Invoice


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestFormatsEndpoint:
    def test_list_formats(self, client: TestClient) -> None:
        response = client.get("/api/v1/invoices/formats")
        assert response.status_code == 200
        data = response.json()
        assert "output_formats" in data
        assert "zugferd_profiles" in data
        assert len(data["output_formats"]) >= 3
        assert len(data["zugferd_profiles"]) >= 5


class TestConvertEndpoint:
    def test_convert_to_zugferd(
        self, client: TestClient, sample_invoice: Invoice
    ) -> None:
        response = client.post(
            "/api/v1/invoices/convert",
            content=sample_invoice.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["invoice_number"] == "RE-2026-001"
        assert data["xml_base64"] is not None
        assert data["pdf_base64"] is not None

        # Verify the base64 decodes to valid XML
        xml = b64decode(data["xml_base64"])
        assert b"CrossIndustryInvoice" in xml

        # Verify the base64 decodes to a valid PDF
        pdf = b64decode(data["pdf_base64"])
        assert pdf[:5] == b"%PDF-"

    def test_convert_download_pdf(
        self, client: TestClient, sample_invoice: Invoice
    ) -> None:
        response = client.post(
            "/api/v1/invoices/convert/download",
            content=sample_invoice.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert b"%PDF-" in response.content[:10]


class TestValidateEndpoint:
    def test_validate_valid_xml(
        self, client: TestClient, sample_invoice: Invoice
    ) -> None:
        # First generate XML
        from app.core.generation.cii_generator import CIIGenerator

        gen = CIIGenerator(sample_invoice)
        xml = gen.generate()

        response = client.post(
            "/api/v1/invoices/validate",
            files={"file": ("invoice.xml", xml, "application/xml")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True

    def test_validate_invalid_xml(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/invoices/validate",
            files={"file": ("bad.xml", b"<not-valid>", "application/xml")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_rejects_non_xml(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/invoices/validate",
            files={"file": ("test.pdf", b"%PDF-fake", "application/pdf")},
        )
        assert response.status_code == 415
