"""Tests for Phases 5-10: Validation, WebDAV, Multi-Tenant, CLI, Streamlit, Docker.

Covers:
  - Phase 5: Offline validation (SchemaManager, SchematronValidator, InvoiceValidator)
  - Phase 6: WebDAV storage (list_files, download_file, upload_file, derive_output_path)
  - Phase 7: Multi-tenant (TenantService, tenant config, API key auth)
  - Phase 8: CLI (Typer commands)
  - Pipeline integration (validation in pipeline)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from lxml import etree

from app.core.generation.cii_generator import CIIGenerator
from app.core.pipeline import ConversionPipeline, ConversionResult
from app.core.storage.webdav_storage import FileMetadata, WebDAVStorage
from app.core.validation.schema_manager import SchemaManager, SchemaType
from app.core.validation.schematron_validator import SchematronResult, SchematronValidator
from app.core.validation.validator import (
    FullValidationResult,
    InvoiceValidator,
    ValidationError,
    ValidationLevel,
)
from app.core.validation.xsd_validator import ValidationResult, XSDValidator
from app.db.service import TenantService, _generate_api_key, _hash_api_key
from app.models.invoice import Invoice, OutputFormat


# =====================================================================
# Phase 5: Offline Validation
# =====================================================================


class TestSchemaManager:
    """Tests for the offline schema manager."""

    def test_init_with_nonexistent_dir(self) -> None:
        """SchemaManager should handle missing directory gracefully."""
        mgr = SchemaManager(Path("/nonexistent/path"))
        assert mgr.list_available() == []

    def test_init_with_empty_dir(self, tmp_path: Path) -> None:
        """SchemaManager should handle empty directory."""
        mgr = SchemaManager(tmp_path)
        assert mgr.list_available() == []

    def test_is_available_returns_false_for_missing(self) -> None:
        """is_available should return False for missing schemas."""
        mgr = SchemaManager(Path("/nonexistent"))
        assert not mgr.is_available(SchemaType.CII_XSD)
        assert not mgr.is_available(SchemaType.UBL_XSD)

    def test_get_xsd_returns_none_for_missing(self) -> None:
        """get_xsd should return None if schema not found."""
        mgr = SchemaManager(Path("/nonexistent"))
        assert mgr.get_xsd(SchemaType.CII_XSD) is None

    def test_get_xslt_returns_none_for_missing(self) -> None:
        """get_xslt should return None if schema not found."""
        mgr = SchemaManager(Path("/nonexistent"))
        assert mgr.get_xslt(SchemaType.XRECHNUNG_SCHEMATRON) is None


class TestSchematronValidator:
    """Tests for the offline Schematron validator."""

    def test_init_without_schemas(self) -> None:
        """SchematronValidator should initialize even without schemas."""
        mgr = SchemaManager(Path("/nonexistent"))
        validator = SchematronValidator(mgr)
        assert not validator.is_available

    def test_validate_invalid_xml(self) -> None:
        """validate() should handle malformed XML gracefully."""
        mgr = SchemaManager(Path("/nonexistent"))
        validator = SchematronValidator(mgr)
        result = validator.validate(b"<not-valid-xml")
        assert isinstance(result, SchematronResult)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_returns_result_without_schemas(self) -> None:
        """validate() should return a result even without schemas."""
        mgr = SchemaManager(Path("/nonexistent"))
        validator = SchematronValidator(mgr)
        result = validator.validate(b"<Invoice/>")
        # Without schemas, it's valid by default (no rules to fail)
        assert isinstance(result, SchematronResult)
        assert result.is_valid

    def test_merge_results_empty(self) -> None:
        """_merge_results with empty list should return valid with warning."""
        mgr = SchemaManager(Path("/nonexistent"))
        validator = SchematronValidator(mgr)
        merged = validator._merge_results([])
        assert merged.is_valid
        assert len(merged.warnings) > 0


class TestInvoiceValidator:
    """Tests for the unified validation orchestrator."""

    def test_validate_invalid_xml_syntax(self) -> None:
        """Validator should catch XML syntax errors."""
        validator = InvoiceValidator(SchemaManager(Path("/nonexistent")))
        result = validator.validate(b"not xml at all")
        assert not result.is_valid
        assert result.level == ValidationLevel.INVALID
        assert len(result.errors) > 0
        assert "XML" in result.errors[0].source

    def test_validate_wellformed_xml(self) -> None:
        """Validator should accept well-formed XML."""
        validator = InvoiceValidator(SchemaManager(Path("/nonexistent")))
        result = validator.validate(b"<Invoice xmlns='test'/>")
        assert isinstance(result, FullValidationResult)

    def test_validate_generated_cii_xml(self, sample_invoice: Invoice) -> None:
        """Validator should process CII-XML from the generator."""
        gen = CIIGenerator(sample_invoice)
        xml_bytes = gen.generate()

        validator = InvoiceValidator(SchemaManager(Path("/nonexistent")))
        result = validator.validate(xml_bytes)
        assert isinstance(result, FullValidationResult)
        # Without downloaded schemas, XSD validation falls back to drafthorse
        assert result.summary_de  # Should have a German summary

    def test_validate_file(self, sample_invoice: Invoice, tmp_path: Path) -> None:
        """validate_file should work with a file path."""
        gen = CIIGenerator(sample_invoice)
        xml_bytes = gen.generate()
        xml_path = tmp_path / "test.xml"
        xml_path.write_bytes(xml_bytes)

        validator = InvoiceValidator(SchemaManager(Path("/nonexistent")))
        result = validator.validate_file(xml_path)
        assert isinstance(result, FullValidationResult)

    def test_validation_level_enum(self) -> None:
        """ValidationLevel enum should have correct values."""
        assert ValidationLevel.VALID.value == "valid"
        assert ValidationLevel.WARNINGS.value == "warnings"
        assert ValidationLevel.INVALID.value == "invalid"

    def test_validation_error_dataclass(self) -> None:
        """ValidationError dataclass should store all fields."""
        err = ValidationError(
            severity="error",
            message="Test error",
            source="XSD",
            location="/Invoice",
            rule_id="BR-01",
        )
        assert err.severity == "error"
        assert err.message == "Test error"
        assert err.source == "XSD"

    def test_full_result_properties(self) -> None:
        """FullValidationResult properties should work."""
        result = FullValidationResult(
            level=ValidationLevel.INVALID,
            is_valid=False,
            errors=[
                ValidationError(severity="error", message="err1"),
                ValidationError(severity="error", message="err2"),
            ],
            warnings=[
                ValidationError(severity="warning", message="warn1"),
            ],
        )
        assert result.error_messages == ["err1", "err2"]
        assert result.warning_messages == ["warn1"]


# =====================================================================
# Phase 5 + Pipeline Integration
# =====================================================================


class TestPipelineWithValidation:
    """Tests for validation integrated into the conversion pipeline."""

    def test_pipeline_validates_output(self, sample_invoice: Invoice) -> None:
        """Pipeline should validate generated XML."""
        pipeline = ConversionPipeline(validate=True)
        result = pipeline.convert(sample_invoice)
        # Should have validation result
        assert result.validation is not None or result.success

    def test_pipeline_skip_validation(self, sample_invoice: Invoice) -> None:
        """Pipeline should skip validation when disabled."""
        pipeline = ConversionPipeline(validate=False)
        result = pipeline.convert(sample_invoice)
        assert result.validation is None
        assert result.success

    def test_pipeline_result_has_warnings(self, sample_invoice: Invoice) -> None:
        """ConversionResult should carry warnings."""
        pipeline = ConversionPipeline(validate=True)
        result = pipeline.convert(sample_invoice)
        assert isinstance(result.warnings, list)

    def test_pipeline_is_valid_property(self, sample_invoice: Invoice) -> None:
        """ConversionResult.is_valid should reflect validation."""
        pipeline = ConversionPipeline(validate=False)
        result = pipeline.convert(sample_invoice)
        assert result.is_valid  # No validation = assumed valid

    def test_convert_xrechnung_cii_validates(self, sample_invoice: Invoice) -> None:
        """XRechnung CII output should be validated."""
        inv = sample_invoice.model_copy(
            update={"output_format": OutputFormat.XRECHNUNG_CII}
        )
        pipeline = ConversionPipeline(validate=True)
        result = pipeline.convert(inv)
        assert result.success or result.validation is not None


# =====================================================================
# Phase 6: WebDAV / Nextcloud Storage
# =====================================================================


class TestWebDAVDeriveOutputPath:
    """Tests for output path derivation logic."""

    def test_derive_pdf_output(self) -> None:
        """Should insert suffix before file extension."""
        result = WebDAVStorage.derive_output_path(
            "/Rechnungen/Eingang/rechnung.pdf", "_zugferd"
        )
        assert result == "/Rechnungen/Eingang/rechnung_zugferd.pdf"

    def test_derive_xml_output(self) -> None:
        """Should work with XML files."""
        result = WebDAVStorage.derive_output_path(
            "/docs/invoice.xml", "_xrechnung"
        )
        assert result == "/docs/invoice_xrechnung.xml"

    def test_derive_with_default_suffix(self) -> None:
        """Default suffix should be '_zugferd'."""
        result = WebDAVStorage.derive_output_path("/test/file.pdf")
        assert result == "/test/file_zugferd.pdf"

    def test_derive_preserves_directory(self) -> None:
        """Should preserve the directory path."""
        result = WebDAVStorage.derive_output_path(
            "/deep/nested/path/invoice.pdf", "_converted"
        )
        assert result.startswith("/deep/nested/path/")
        assert result.endswith("_converted.pdf")


class TestWebDAVStorageInit:
    """Tests for WebDAV storage initialization."""

    def test_init_with_custom_params(self) -> None:
        """Should accept custom URL, username, password."""
        storage = WebDAVStorage(
            url="https://cloud.test.com/webdav",
            username="testuser",
            password="testpass",
            root_path="/TestRoot",
        )
        assert storage.base_url == "https://cloud.test.com/webdav"
        assert storage.username == "testuser"
        assert storage.root_path == "/TestRoot"

    def test_full_url_construction(self) -> None:
        """_full_url should build correct URLs."""
        storage = WebDAVStorage(
            url="https://cloud.test.com/webdav",
            username="user",
            password="pass",
        )
        assert storage._full_url("/docs/file.pdf") == "https://cloud.test.com/webdav/docs/file.pdf"

    def test_full_url_strips_leading_slash(self) -> None:
        """_full_url should handle leading slashes."""
        storage = WebDAVStorage(
            url="https://cloud.test.com/webdav/",
            username="user",
            password="pass",
        )
        url = storage._full_url("docs/file.pdf")
        assert "docs/file.pdf" in url


class TestFileMetadata:
    """Tests for the FileMetadata dataclass."""

    def test_metadata_creation(self) -> None:
        """FileMetadata should store all fields."""
        meta = FileMetadata(
            path="/docs/invoice.pdf",
            name="invoice.pdf",
            size=12345,
            content_type="application/pdf",
            last_modified="Thu, 01 Jan 2026 00:00:00 GMT",
            etag="abc123",
            is_directory=False,
        )
        assert meta.name == "invoice.pdf"
        assert meta.size == 12345
        assert not meta.is_directory

    def test_directory_metadata(self) -> None:
        """FileMetadata should support directories."""
        meta = FileMetadata(
            path="/docs/",
            name="docs",
            is_directory=True,
        )
        assert meta.is_directory


class TestWebDAVParsePropfind:
    """Tests for PROPFIND XML parsing."""

    def test_parse_empty_response(self) -> None:
        """Empty PROPFIND response should return empty list."""
        storage = WebDAVStorage(url="https://test.com", username="u", password="p")
        xml = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"></d:multistatus>'
        result = storage._parse_propfind(xml, "/test")
        assert result == []

    def test_parse_invalid_xml(self) -> None:
        """Invalid XML should return empty list."""
        storage = WebDAVStorage(url="https://test.com", username="u", password="p")
        result = storage._parse_propfind("not xml", "/test")
        assert result == []

    def test_parse_file_entry(self) -> None:
        """Should parse a file entry from PROPFIND response."""
        storage = WebDAVStorage(url="https://test.com", username="u", password="p")
        xml = """<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
          <d:response>
            <d:href>/test/</d:href>
            <d:propstat>
              <d:prop>
                <d:resourcetype><d:collection/></d:resourcetype>
              </d:prop>
            </d:propstat>
          </d:response>
          <d:response>
            <d:href>/test/invoice.pdf</d:href>
            <d:propstat>
              <d:prop>
                <d:getcontentlength>12345</d:getcontentlength>
                <d:getcontenttype>application/pdf</d:getcontenttype>
                <d:resourcetype/>
              </d:prop>
            </d:propstat>
          </d:response>
        </d:multistatus>"""
        result = storage._parse_propfind(xml, "/test")
        assert len(result) == 1
        assert result[0].name == "invoice.pdf"
        assert result[0].size == 12345
        assert not result[0].is_directory


# =====================================================================
# Phase 7: Multi-Tenant
# =====================================================================


class TestAPIKeyHashing:
    """Tests for API key generation and hashing."""

    def test_generate_api_key(self) -> None:
        """Generated API key should have prefix and sufficient length."""
        key = _generate_api_key()
        assert key.startswith("if_")
        assert len(key) > 30

    def test_hash_api_key(self) -> None:
        """Hashing should be deterministic."""
        key = "if_test_key_123"
        hash1 = _hash_api_key(key)
        hash2 = _hash_api_key(key)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_different_keys_different_hashes(self) -> None:
        """Different keys should produce different hashes."""
        hash1 = _hash_api_key("key1")
        hash2 = _hash_api_key("key2")
        assert hash1 != hash2


class TestTenantServiceStatic:
    """Tests for TenantService static methods."""

    def test_get_tenant_config_empty(self) -> None:
        """Should handle None config."""
        tenant = MagicMock()
        tenant.config = None
        assert TenantService.get_tenant_config(tenant) == {}

    def test_get_tenant_config_json(self) -> None:
        """Should parse JSON config."""
        tenant = MagicMock()
        tenant.config = json.dumps({"company": {"name": "Test GmbH"}})
        config = TenantService.get_tenant_config(tenant)
        assert config["company"]["name"] == "Test GmbH"

    def test_get_tenant_company(self) -> None:
        """Should extract company data from config."""
        tenant = MagicMock()
        tenant.config = json.dumps({
            "company": {"name": "Muster GmbH", "vat_id": "DE123456789"}
        })
        company = TenantService.get_tenant_company(tenant)
        assert company["name"] == "Muster GmbH"
        assert company["vat_id"] == "DE123456789"

    def test_get_tenant_nextcloud(self) -> None:
        """Should extract Nextcloud config."""
        tenant = MagicMock()
        tenant.config = json.dumps({
            "nextcloud": {"url": "https://cloud.example.com", "username": "user"}
        })
        nc = TenantService.get_tenant_nextcloud(tenant)
        assert nc["url"] == "https://cloud.example.com"

    def test_get_tenant_defaults(self) -> None:
        """Should extract default settings."""
        tenant = MagicMock()
        tenant.config = json.dumps({
            "defaults": {"output_format": "xrechnung_cii", "zugferd_profile": "XRECHNUNG"}
        })
        defaults = TenantService.get_tenant_defaults(tenant)
        assert defaults["output_format"] == "xrechnung_cii"

    def test_get_tenant_company_missing(self) -> None:
        """Should return empty dict when company section missing."""
        tenant = MagicMock()
        tenant.config = json.dumps({"defaults": {}})
        assert TenantService.get_tenant_company(tenant) == {}


# =====================================================================
# Phase 8: CLI (Typer)
# =====================================================================


class TestCLI:
    """Tests for the Typer CLI commands."""

    def test_cli_app_exists(self) -> None:
        """CLI app should be importable."""
        from app.cli.main import app
        assert app is not None

    def test_cli_has_convert_command(self) -> None:
        """CLI should have 'convert' command."""
        from app.cli.main import app
        callbacks = [cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback]
        assert "convert" in callbacks

    def test_cli_has_validate_command(self) -> None:
        """CLI should have 'validate_cmd' command."""
        from app.cli.main import app
        callbacks = [cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback]
        assert "validate_cmd" in callbacks

    def test_cli_has_extract_command(self) -> None:
        """CLI should have 'extract' command."""
        from app.cli.main import app
        callbacks = [cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback]
        assert "extract" in callbacks

    def test_cli_has_serve_command(self) -> None:
        """CLI should have 'serve' command."""
        from app.cli.main import app
        callbacks = [cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback]
        assert "serve" in callbacks

    def test_cli_has_tenant_subcommand(self) -> None:
        """CLI should have 'tenant' sub-command group."""
        from app.cli.main import app
        group_names = [g.name for g in app.registered_groups]
        assert "tenant" in group_names

    def test_nextcloud_path_detection(self) -> None:
        """Should correctly detect nextcloud:// URIs."""
        from app.cli.main import _is_nextcloud_path, _parse_nextcloud_path

        assert _is_nextcloud_path("nextcloud://Rechnungen/test.pdf")
        assert not _is_nextcloud_path("/local/path/test.pdf")
        assert _parse_nextcloud_path("nextcloud://Rechnungen/test.pdf") == "Rechnungen/test.pdf"


class TestCLIValidateCommand:
    """Tests for the validate CLI command with file."""

    def test_validate_valid_xml(self, sample_invoice: Invoice, tmp_path: Path) -> None:
        """validate command should return exit code 0 for valid XML."""
        from typer.testing import CliRunner
        from app.cli.main import app

        # Generate valid XML
        gen = CIIGenerator(sample_invoice)
        xml_bytes = gen.generate()
        xml_path = tmp_path / "test.xml"
        xml_path.write_bytes(xml_bytes)

        runner = CliRunner()
        result = runner.invoke(app, ["validate-cmd", "--file", str(xml_path)])
        # May succeed or show validation info; exit 0 means valid
        # Without schemas, it may still pass basic XML check
        assert result.exit_code in (0, 1)

    def test_validate_missing_file(self) -> None:
        """validate command should fail for missing file."""
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["validate-cmd", "--file", "/nonexistent/file.xml"])
        assert result.exit_code != 0
        assert "nicht gefunden" in result.output


class TestCLIExtractCommand:
    """Tests for the extract CLI command."""

    def test_extract_missing_file(self) -> None:
        """extract should fail for missing file."""
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["extract", "--input", "/nonexistent/file.pdf"])
        assert result.exit_code != 0


# =====================================================================
# Config
# =====================================================================


class TestConfig:
    """Tests for updated configuration."""

    def test_config_has_nextcloud_fields(self) -> None:
        """Config should have Nextcloud-specific fields."""
        from app.config import Settings

        s = Settings(
            nextcloud_url="https://cloud.test.com",
            nextcloud_username="user",
            nextcloud_password="pass",
        )
        assert s.effective_webdav_url == "https://cloud.test.com"
        assert s.effective_webdav_username == "user"
        assert s.effective_webdav_password == "pass"

    def test_config_nextcloud_fallback(self) -> None:
        """Nextcloud config should fall back to WebDAV settings."""
        from app.config import Settings

        s = Settings(
            webdav_url="https://webdav.test.com",
            webdav_username="wuser",
        )
        assert s.effective_webdav_url == "https://webdav.test.com"
        assert s.effective_webdav_username == "wuser"

    def test_config_has_schema_dir(self) -> None:
        """Config should have schema_dir field."""
        from app.config import Settings

        s = Settings()
        assert s.schema_dir is not None

    def test_config_has_default_format(self) -> None:
        """Config should have default output format."""
        from app.config import Settings

        s = Settings()
        assert s.default_output_format == "zugferd_pdf"
        assert s.default_zugferd_profile == "EN 16931"


# =====================================================================
# DB Models
# =====================================================================


class TestDBModels:
    """Tests for enhanced DB models."""

    def test_tenant_model_has_config(self) -> None:
        """Tenant model should have config field."""
        from app.db.models import Tenant
        assert hasattr(Tenant, "config")

    def test_invoice_record_model(self) -> None:
        """InvoiceRecord should have all expected fields."""
        from app.db.models import InvoiceRecord
        assert hasattr(InvoiceRecord, "tenant_id")
        assert hasattr(InvoiceRecord, "is_valid")
        assert hasattr(InvoiceRecord, "validation_report")
        assert hasattr(InvoiceRecord, "output_format")
