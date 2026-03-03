"""Tests for Phase 4 features: WebDAV, invoice2data, DB persistence, logging, migration."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    OutputFormat,
    PaymentTerms,
    TaxBreakdown,
    ZUGFeRDProfile,
)


# ── WebDAV Storage Tests ──


class TestWebDAVStorage:
    """Tests for the WebDAV storage backend."""

    def test_webdav_storage_import(self):
        """WebDAVStorage can be imported from storage module."""
        from app.core.storage import WebDAVStorage
        assert WebDAVStorage is not None

    def test_webdav_storage_init(self):
        """WebDAVStorage initializes with custom URL/credentials."""
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(
            url="https://nextcloud.example.com/remote.php/dav/files/user/invoices",
            username="testuser",
            password="testpass",
        )
        assert "nextcloud.example.com" in storage.base_url
        assert storage.username == "testuser"
        assert storage.password == "testpass"

    def test_webdav_url_builder(self):
        """WebDAVStorage builds correct URLs."""
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(url="https://dav.example.com/files")
        assert storage.base_url == "https://dav.example.com/files"

    @pytest.mark.asyncio
    async def test_webdav_is_available_false_when_no_url(self):
        """is_available returns False when no URL configured."""
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(url="")
        assert await storage.is_available() is False

    @pytest.mark.asyncio
    async def test_webdav_is_available_false_on_connection_error(self):
        """is_available returns False when server is unreachable."""
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(url="http://nonexistent.local:9999/dav")
        assert await storage.is_available() is False

    @pytest.mark.asyncio
    async def test_webdav_save_input(self):
        """save_input uploads file and returns remote path."""
        import httpx
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(url="http://dav.test/files", username="u", password="p")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            path = await storage.save_input("tenant1", "invoice.pdf", b"PDF content")
            assert "tenant1/input/" in path
            assert "invoice.pdf" in path

    @pytest.mark.asyncio
    async def test_webdav_save_output(self):
        """save_output uploads file and returns remote path."""
        from app.core.storage.webdav_storage import WebDAVStorage

        storage = WebDAVStorage(url="http://dav.test/files", username="u", password="p")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            path = await storage.save_output("tenant1", "output.xml", b"<xml/>")
            assert "tenant1/output/" in path
            assert "output.xml" in path


# ── Invoice2Data Extractor Tests ──


class TestInvoice2DataExtractor:
    """Tests for the invoice2data fallback extraction."""

    def test_invoice2data_extractor_import(self):
        """Invoice2DataExtractor can be imported."""
        from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor
        assert Invoice2DataExtractor is not None

    def test_safe_decimal(self):
        """_safe_decimal handles various input formats."""
        from app.core.extraction.invoice2data_extractor import _safe_decimal

        assert _safe_decimal("100.50") == Decimal("100.50")
        assert _safe_decimal("1234,56") == Decimal("1234.56")  # German comma
        assert _safe_decimal("1.234,56") == Decimal("0")  # Thousand separator + comma → invalid
        assert _safe_decimal(None) == Decimal("0")
        assert _safe_decimal("invalid") == Decimal("0")
        assert _safe_decimal(42) == Decimal("42")
        assert _safe_decimal(99.99) == Decimal("99.99")

    def test_safe_date(self):
        """_safe_date handles various date formats."""
        from app.core.extraction.invoice2data_extractor import _safe_date

        assert _safe_date(date(2026, 3, 1)) == date(2026, 3, 1)
        assert _safe_date(datetime(2026, 3, 1)) == date(2026, 3, 1)
        assert _safe_date("2026-03-01") == date(2026, 3, 1)
        assert _safe_date("01.03.2026") == date(2026, 3, 1)
        assert _safe_date(None) == date.today()
        assert _safe_date("invalid") == date.today()

    def test_map_to_invoice_minimal(self):
        """Mapping with minimal invoice2data output produces valid Invoice."""
        from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

        extractor = Invoice2DataExtractor()
        data = {
            "invoice_number": "RE-2026-042",
            "date": "2026-03-01",
            "amount": 119.0,
            "amount_untaxed": 100.0,
            "amount_tax": 19.0,
            "issuer": "Test GmbH",
            "currency": "EUR",
        }
        invoice = extractor._map_to_invoice(data)

        assert invoice.invoice_number == "RE-2026-042"
        assert invoice.invoice_date == date(2026, 3, 1)
        assert invoice.seller.name == "Test GmbH"
        assert invoice.totals.gross_amount == Decimal("119.0")
        assert invoice.totals.net_amount == Decimal("100.0")
        assert invoice.totals.tax_amount == Decimal("19.0")
        assert len(invoice.lines) == 1
        assert len(invoice.tax_breakdown) == 1

    def test_map_to_invoice_with_lines(self):
        """Mapping with line items produces correct invoice lines."""
        from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

        extractor = Invoice2DataExtractor()
        data = {
            "invoice_number": "RE-100",
            "date": "2026-01-15",
            "amount": 238.0,
            "amount_untaxed": 200.0,
            "amount_tax": 38.0,
            "issuer": "Lieferant AG",
            "lines": [
                {"description": "Beratung", "quantity": 2, "unit_price": 50.0, "amount": 100.0},
                {"description": "Material", "quantity": 1, "unit_price": 100.0, "amount": 100.0},
            ],
        }
        invoice = extractor._map_to_invoice(data)

        assert len(invoice.lines) == 2
        assert invoice.lines[0].description == "Beratung"
        assert invoice.lines[0].quantity == Decimal("2")
        assert invoice.lines[1].description == "Material"

    def test_map_to_invoice_gross_only(self):
        """When only gross amount is available, net and tax are estimated."""
        from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

        extractor = Invoice2DataExtractor()
        data = {
            "invoice_number": "RE-200",
            "amount": 119.0,
            "issuer": "Firma",
        }
        invoice = extractor._map_to_invoice(data)

        # With 19% default tax rate: 119 / 1.19 = 100
        assert invoice.totals.gross_amount == Decimal("119.0")
        assert invoice.totals.net_amount == Decimal("100.00")
        assert invoice.totals.tax_amount == Decimal("19.00")

    def test_map_with_payment_info(self):
        """Payment info (IBAN, BIC, due_date) is mapped correctly."""
        from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

        extractor = Invoice2DataExtractor()
        data = {
            "invoice_number": "RE-300",
            "amount": 100.0,
            "amount_untaxed": 100.0,
            "amount_tax": 0.0,
            "issuer": "Firma",
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
            "due_date": "2026-04-01",
        }
        invoice = extractor._map_to_invoice(data)

        assert invoice.payment.iban == "DE89370400440532013000"
        assert invoice.payment.bic == "COBADEFFXXX"
        assert invoice.payment.due_date == date(2026, 4, 1)


# ── DB Service Tests ──


class TestInvoiceService:
    """Tests for the DB service layer."""

    def test_service_import(self):
        """InvoiceService can be imported."""
        from app.db.service import InvoiceService
        assert InvoiceService is not None

    def test_service_init(self):
        """InvoiceService initializes with a session."""
        from app.db.service import InvoiceService

        mock_session = MagicMock()
        svc = InvoiceService(mock_session)
        assert svc.session is mock_session


# ── Alembic Migration Tests ──


class TestAlembicMigration:
    """Tests for Alembic migration scripts."""

    def test_migration_file_exists(self):
        """Initial migration file exists."""
        path = Path("app/db/migrations/versions/001_initial_schema.py")
        assert path.exists()

    def test_migration_has_upgrade_and_downgrade(self):
        """Migration defines both upgrade() and downgrade() functions."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_001",
            "app/db/migrations/versions/001_initial_schema.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)

    def test_migration_revision_metadata(self):
        """Migration has correct revision metadata."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_001",
            "app/db/migrations/versions/001_initial_schema.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "001"
        assert mod.down_revision is None

    def test_alembic_env_exists(self):
        """Alembic env.py exists."""
        assert Path("app/db/migrations/env.py").exists()

    def test_alembic_ini_exists(self):
        """alembic.ini exists at project root."""
        assert Path("alembic.ini").exists()


# ── Structured Logging Tests ──


class TestStructuredLogging:
    """Tests for the logging configuration."""

    def test_json_formatter(self):
        """JSONFormatter produces valid JSON output."""
        import logging
        from app.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message %s",
            args=("value",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "app.test"
        assert "Test message value" in parsed["message"]
        assert "timestamp" in parsed

    def test_json_formatter_with_extras(self):
        """JSONFormatter includes extra fields like job_id."""
        import logging
        from app.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.api",
            level=logging.INFO,
            pathname="api.py",
            lineno=42,
            msg="Processing",
            args=(),
            exc_info=None,
        )
        record.job_id = "abc123"
        record.tenant_id = "tenant-1"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["job_id"] == "abc123"
        assert parsed["tenant_id"] == "tenant-1"

    def test_dev_formatter(self):
        """DevFormatter produces colored output."""
        import logging
        from app.logging_config import DevFormatter

        formatter = DevFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "Warning message" in output
        # Should contain ANSI color code for warning (yellow)
        assert "\033[33m" in output

    def test_setup_logging_import(self):
        """setup_logging can be imported and called."""
        from app.logging_config import setup_logging
        # Should not raise
        setup_logging()


# ── API Endpoint Tests (records) ──


class TestAPIRecordEndpoints:
    """Tests for the new /records API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_list_records_returns_empty(self, client):
        """GET /api/v1/invoices/records returns empty list when DB unavailable."""
        response = client.get("/api/v1/invoices/records")
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []
        assert data["total"] == 0

    def test_list_records_with_params(self, client):
        """GET /api/v1/invoices/records accepts limit/offset params."""
        response = client.get("/api/v1/invoices/records?limit=10&offset=5")
        assert response.status_code == 200

    def test_get_record_invalid_uuid(self, client):
        """GET /api/v1/invoices/records/{id} returns 503 for invalid UUID when DB unavailable."""
        response = client.get("/api/v1/invoices/records/not-a-uuid")
        assert response.status_code == 503

    def test_formats_endpoint_still_works(self, client):
        """GET /api/v1/invoices/formats still returns format info."""
        response = client.get("/api/v1/invoices/formats")
        assert response.status_code == 200
        data = response.json()
        assert "output_formats" in data
        assert "zugferd_profiles" in data


# ── Docker Config Tests ──


class TestDockerConfig:
    """Tests for Docker configuration files."""

    def test_dockerfile_exists(self):
        """Dockerfile exists."""
        assert Path("Dockerfile").exists()

    def test_dockerfile_has_entrypoint(self):
        """Dockerfile uses docker-entrypoint.sh."""
        content = Path("Dockerfile").read_text()
        assert "docker-entrypoint.sh" in content
        assert "ENTRYPOINT" in content

    def test_entrypoint_script_exists(self):
        """docker-entrypoint.sh exists."""
        assert Path("docker-entrypoint.sh").exists()

    def test_entrypoint_runs_migrations(self):
        """Entrypoint script runs Alembic migrations."""
        content = Path("docker-entrypoint.sh").read_text()
        assert "alembic upgrade head" in content

    def test_docker_compose_has_kosit(self):
        """docker-compose.yml includes KoSIT validator service."""
        content = Path("docker-compose.yml").read_text()
        assert "kosit-validator" in content
        assert "kosit_data" in content

    def test_docker_compose_has_healthchecks(self):
        """docker-compose.yml has healthchecks for API service."""
        content = Path("docker-compose.yml").read_text()
        assert "healthcheck" in content
        assert "health" in content

    def test_docker_compose_profiles(self):
        """KoSIT uses Docker Compose profiles."""
        content = Path("docker-compose.yml").read_text()
        assert "profiles:" in content
        assert "full" in content

    def test_worker_command_correct(self):
        """Worker service uses correct ARQ module path."""
        content = Path("docker-compose.yml").read_text()
        assert "app.worker.settings.WorkerSettings" in content
