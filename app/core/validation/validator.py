"""Unified invoice validation orchestrator.

Combines XSD validation, offline Schematron, and optional KoSIT Validator
into a single validation pipeline with structured results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lxml import etree

from app.core.validation.schema_manager import SchemaManager, SchemaType
from app.core.validation.schematron_validator import SchematronValidator
from app.core.validation.xsd_validator import ValidationResult

logger = logging.getLogger(__name__)


class ValidationLevel(str, Enum):
    """Validation severity level for display (green/yellow/red)."""

    VALID = "valid"          # Grün – keine Fehler
    WARNINGS = "warnings"    # Gelb – gültig, aber mit Warnungen
    INVALID = "invalid"      # Rot – ungültig, Fehler vorhanden


@dataclass
class ValidationError:
    """Einzelner Validierungsfehler/-warnung mit Kontext."""

    severity: str  # "error", "warning", "info"
    message: str
    source: str = ""  # "XSD", "Schematron", "KoSIT"
    location: str = ""
    rule_id: str = ""


@dataclass
class FullValidationResult:
    """Vollständiges Validierungsergebnis mit allen Details."""

    level: ValidationLevel
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    xsd_valid: bool | None = None
    schematron_valid: bool | None = None
    kosit_valid: bool | None = None
    schemas_used: list[str] = field(default_factory=list)
    summary_de: str = ""

    @property
    def error_messages(self) -> list[str]:
        """Flache Liste aller Fehlermeldungen."""
        return [e.message for e in self.errors]

    @property
    def warning_messages(self) -> list[str]:
        """Flache Liste aller Warnungen."""
        return [w.message for w in self.warnings]


class InvoiceValidator:
    """Orchestriert die vollständige Validierung einer E-Rechnung.

    Validierungsschritte:
      1. XML-Wohlgeformtheit
      2. XSD-Schemavalidierung (Struktur)
      3. Schematron-Regelprüfung (Geschäftsregeln, offline)
      4. KoSIT-Validator (optional, falls verfügbar)
    """

    def __init__(
        self,
        schema_manager: SchemaManager | None = None,
        kosit_url: str | None = None,
    ) -> None:
        self._schema_manager = schema_manager or SchemaManager()
        self._schematron = SchematronValidator(self._schema_manager)
        self._kosit_url = kosit_url

    def validate(self, xml_bytes: bytes) -> FullValidationResult:
        """Führe synchrone Validierung durch (XSD + offline Schematron)."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        schemas_used: list[str] = []
        xsd_valid: bool | None = None
        schematron_valid: bool | None = None

        # Step 1: XML well-formedness
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return FullValidationResult(
                level=ValidationLevel.INVALID,
                is_valid=False,
                errors=[
                    ValidationError(
                        severity="error",
                        message=f"XML-Parsing-Fehler: {e}",
                        source="XML",
                    )
                ],
                summary_de="Das Dokument ist kein gültiges XML.",
            )

        # Detect document type
        is_ubl = "Invoice" in root.tag and (
            "oasis" in root.tag.lower() or "ubl" in root.tag.lower()
        )
        is_cii = "CrossIndustryInvoice" in root.tag or not is_ubl

        # Step 2: XSD validation
        xsd_schema_type = SchemaType.UBL_XSD if is_ubl else SchemaType.CII_XSD
        xsd = self._schema_manager.get_xsd(xsd_schema_type)

        if xsd:
            is_valid_xsd = xsd.validate(root)
            xsd_valid = is_valid_xsd
            schemas_used.append(f"XSD ({xsd_schema_type.value})")

            if not is_valid_xsd:
                for err in xsd.error_log:
                    errors.append(
                        ValidationError(
                            severity="error",
                            message=str(err),
                            source="XSD",
                        )
                    )
        else:
            # Fallback: try drafthorse/factur-x XSD for CII
            if is_cii:
                try:
                    from facturx import xml_check_xsd

                    xml_check_xsd(xml_bytes)
                    xsd_valid = True
                    schemas_used.append("XSD (Factur-X)")
                except ImportError:
                    # factur-x not available, skip XSD
                    pass
                except Exception as e:
                    xsd_valid = False
                    errors.append(
                        ValidationError(
                            severity="error",
                            message=f"XSD-Validierung fehlgeschlagen: {e}",
                            source="XSD",
                        )
                    )

        # Step 3: Offline Schematron
        if self._schematron.is_available:
            sch_result = self._schematron.validate(xml_bytes)
            schematron_valid = sch_result.is_valid

            if sch_result.schema_used:
                schemas_used.append(f"Schematron ({sch_result.schema_used})")

            for msg in sch_result.errors:
                errors.append(
                    ValidationError(
                        severity="error",
                        message=msg,
                        source="Schematron",
                    )
                )
            for msg in sch_result.warnings:
                warnings.append(
                    ValidationError(
                        severity="warning",
                        message=msg,
                        source="Schematron",
                    )
                )

        # Determine overall level
        is_valid = len(errors) == 0
        if not is_valid:
            level = ValidationLevel.INVALID
        elif warnings:
            level = ValidationLevel.WARNINGS
        else:
            level = ValidationLevel.VALID

        # German summary
        if level == ValidationLevel.VALID:
            summary = "Die E-Rechnung ist gültig."
        elif level == ValidationLevel.WARNINGS:
            summary = (
                f"Die E-Rechnung ist gültig, "
                f"aber es gibt {len(warnings)} Warnung(en)."
            )
        else:
            summary = (
                f"Die E-Rechnung ist ungültig: "
                f"{len(errors)} Fehler gefunden."
            )

        return FullValidationResult(
            level=level,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            xsd_valid=xsd_valid,
            schematron_valid=schematron_valid,
            schemas_used=schemas_used,
            summary_de=summary,
        )

    async def validate_full(self, xml_bytes: bytes) -> FullValidationResult:
        """Vollständige Validierung inkl. KoSIT-Validator (async).

        Führt zunächst die synchrone Validierung durch und ergänzt
        optional das Ergebnis des KoSIT-Validators.
        """
        result = self.validate(xml_bytes)

        # Step 4: KoSIT Validator (optional, async)
        if self._kosit_url:
            try:
                from app.core.validation.kosit_client import KoSITClient

                client = KoSITClient(self._kosit_url)
                if await client.is_available():
                    kosit_result = await client.validate(xml_bytes)
                    result.kosit_valid = kosit_result.is_valid
                    result.schemas_used.append("KoSIT Validator")

                    for msg in kosit_result.errors:
                        result.errors.append(
                            ValidationError(
                                severity="error",
                                message=msg,
                                source="KoSIT",
                            )
                        )
                    for msg in kosit_result.warnings:
                        result.warnings.append(
                            ValidationError(
                                severity="warning",
                                message=msg,
                                source="KoSIT",
                            )
                        )

                    # Re-evaluate level
                    if result.errors:
                        result.level = ValidationLevel.INVALID
                        result.is_valid = False
                    elif result.warnings:
                        result.level = ValidationLevel.WARNINGS

                    # Update summary
                    if result.level == ValidationLevel.VALID:
                        result.summary_de = (
                            "Die E-Rechnung ist gültig (XSD + Schematron + KoSIT)."
                        )
                    elif result.level == ValidationLevel.WARNINGS:
                        result.summary_de = (
                            f"Die E-Rechnung ist gültig, "
                            f"aber es gibt {len(result.warnings)} Warnung(en)."
                        )
                    else:
                        result.summary_de = (
                            f"Die E-Rechnung ist ungültig: "
                            f"{len(result.errors)} Fehler gefunden."
                        )
            except Exception as e:
                logger.debug("KoSIT-Validator nicht verfügbar: %s", e)

        return result

    def validate_file(self, file_path: Path) -> FullValidationResult:
        """Validiere eine XML-Datei."""
        with open(file_path, "rb") as f:
            return self.validate(f.read())
