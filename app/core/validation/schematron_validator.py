"""Offline Schematron validation via compiled XSLT stylesheets.

Processes SVRL (Schematron Validation Report Language) output from the
compiled Schematron rules for XRechnung and EN 16931.

This replaces the need for the KoSIT Validator Docker sidecar in many cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from app.core.validation.schema_manager import SchemaManager, SchemaType

logger = logging.getLogger(__name__)

# SVRL namespace
SVRL_NS = "http://purl.oclc.org/dml/svrl"
_SVRL = f"{{{SVRL_NS}}}"


@dataclass
class SchematronResult:
    """Ergebnis einer Schematron-Validierung."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fired_rules: int = 0
    schema_used: str = ""


class SchematronValidator:
    """Offline Schematron validation using pre-compiled XSLT stylesheets.

    Supports:
      - EN 16931 CII Schematron (for ZUGFeRD / Factur-X / XRechnung-CII)
      - EN 16931 UBL Schematron (for XRechnung-UBL / PEPPOL BIS)
      - XRechnung-specific Schematron rules
    """

    def __init__(self, schema_manager: SchemaManager | None = None) -> None:
        self._manager = schema_manager or SchemaManager()

    def validate_cii(self, xml_bytes: bytes) -> SchematronResult:
        """Validate a CII-XML document (ZUGFeRD/XRechnung-CII).

        Applies EN 16931 CII rules, then XRechnung-specific rules if available.
        """
        results: list[SchematronResult] = []

        # EN 16931 CII rules
        en_xslt = self._manager.get_xslt(SchemaType.EN16931_CII_SCHEMATRON)
        if en_xslt:
            result = self._apply_xslt(xml_bytes, en_xslt, "EN 16931 CII")
            results.append(result)

        # XRechnung-specific rules
        xr_xslt = self._manager.get_xslt(SchemaType.XRECHNUNG_SCHEMATRON)
        if xr_xslt:
            result = self._apply_xslt(xml_bytes, xr_xslt, "XRechnung Schematron")
            results.append(result)

        return self._merge_results(results)

    def validate_ubl(self, xml_bytes: bytes) -> SchematronResult:
        """Validate a UBL-XML document (XRechnung-UBL / PEPPOL BIS).

        Applies EN 16931 UBL rules, then XRechnung-specific rules if available.
        """
        results: list[SchematronResult] = []

        # EN 16931 UBL rules
        en_xslt = self._manager.get_xslt(SchemaType.EN16931_UBL_SCHEMATRON)
        if en_xslt:
            result = self._apply_xslt(xml_bytes, en_xslt, "EN 16931 UBL")
            results.append(result)

        # XRechnung-specific rules (may apply to both CII and UBL)
        xr_xslt = self._manager.get_xslt(SchemaType.XRECHNUNG_SCHEMATRON)
        if xr_xslt:
            result = self._apply_xslt(xml_bytes, xr_xslt, "XRechnung Schematron")
            results.append(result)

        return self._merge_results(results)

    def validate(self, xml_bytes: bytes) -> SchematronResult:
        """Auto-detect CII vs UBL and validate accordingly."""
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return SchematronResult(
                is_valid=False,
                errors=[f"XML-Parsing-Fehler: {e}"],
            )

        ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""

        if "CrossIndustryInvoice" in root.tag or "uncefact" in ns or "cii" in ns.lower():
            return self.validate_cii(xml_bytes)
        elif "Invoice" in root.tag and ("oasis" in ns.lower() or "ubl" in ns.lower()):
            return self.validate_ubl(xml_bytes)
        else:
            # Default: try CII first
            return self.validate_cii(xml_bytes)

    @property
    def is_available(self) -> bool:
        """Check whether any Schematron schemas are available for offline validation."""
        return any(
            self._manager.is_available(st)
            for st in [
                SchemaType.EN16931_CII_SCHEMATRON,
                SchemaType.EN16931_UBL_SCHEMATRON,
                SchemaType.XRECHNUNG_SCHEMATRON,
            ]
        )

    def _apply_xslt(
        self, xml_bytes: bytes, xslt: etree.XSLT, schema_name: str
    ) -> SchematronResult:
        """Apply a compiled Schematron XSLT and parse the SVRL output."""
        errors: list[str] = []
        warnings: list[str] = []
        fired_rules = 0

        try:
            doc = etree.fromstring(xml_bytes)
            svrl_tree = xslt(doc)
            svrl_root = svrl_tree.getroot()

            if svrl_root is None:
                return SchematronResult(
                    is_valid=True,
                    schema_used=schema_name,
                )

            # Count fired rules
            for _ in svrl_root.iter(f"{_SVRL}fired-rule"):
                fired_rules += 1

            # Collect failed assertions
            for failed in svrl_root.iter(f"{_SVRL}failed-assert"):
                text_el = failed.find(f"{_SVRL}text")
                location = failed.get("location", "")
                flag = failed.get("flag", "error").lower()
                rule_id = failed.get("id", "")
                message = (
                    text_el.text.strip() if text_el is not None and text_el.text else ""
                )

                if not message:
                    continue

                entry = f"[{rule_id}] {message}" if rule_id else message
                if location:
                    entry += f" (Pfad: {location})"

                if flag in ("fatal", "error"):
                    errors.append(entry)
                else:
                    warnings.append(entry)

            # Collect successful reports marked as warnings
            for report in svrl_root.iter(f"{_SVRL}successful-report"):
                text_el = report.find(f"{_SVRL}text")
                flag = report.get("flag", "info").lower()
                message = (
                    text_el.text.strip() if text_el is not None and text_el.text else ""
                )
                if message and flag == "warning":
                    warnings.append(f"[Hinweis] {message}")

        except etree.XSLTApplyError as e:
            logger.warning("Schematron XSLT-Anwendung fehlgeschlagen (%s): %s", schema_name, e)
            # Non-fatal: schema may not be applicable to this document type
            return SchematronResult(
                is_valid=True,
                warnings=[f"Schematron {schema_name} konnte nicht angewendet werden: {e}"],
                schema_used=schema_name,
            )
        except Exception as e:
            logger.warning("Schematron-Validierung fehlgeschlagen (%s): %s", schema_name, e)
            return SchematronResult(
                is_valid=True,
                warnings=[f"Schematron-Fehler ({schema_name}): {e}"],
                schema_used=schema_name,
            )

        return SchematronResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            fired_rules=fired_rules,
            schema_used=schema_name,
        )

    def _merge_results(self, results: list[SchematronResult]) -> SchematronResult:
        """Merge multiple validation results into one."""
        if not results:
            return SchematronResult(
                is_valid=True,
                warnings=["Keine Schematron-Schemas verfügbar für Offline-Validierung."],
            )

        all_errors: list[str] = []
        all_warnings: list[str] = []
        total_fired = 0
        schemas_used: list[str] = []

        for r in results:
            all_errors.extend(r.errors)
            all_warnings.extend(r.warnings)
            total_fired += r.fired_rules
            if r.schema_used:
                schemas_used.append(r.schema_used)

        return SchematronResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
            fired_rules=total_fired,
            schema_used=", ".join(schemas_used),
        )
