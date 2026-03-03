"""Manage offline validation schemas (XSD + Schematron).

Handles discovery, loading, and caching of validation schemas from the
local filesystem. Schemas can be downloaded via scripts/download_schemas.sh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

# Default schema directory relative to project root
_DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "schemas"


class SchemaType(str, Enum):
    """Supported schema types."""

    CII_XSD = "cii_xsd"
    UBL_XSD = "ubl_xsd"
    XRECHNUNG_SCHEMATRON = "xrechnung_schematron"
    EN16931_CII_SCHEMATRON = "en16931_cii_schematron"
    EN16931_UBL_SCHEMATRON = "en16931_ubl_schematron"


@dataclass
class SchemaInfo:
    """Metadata about a loaded validation schema."""

    schema_type: SchemaType
    path: Path
    version: str = ""
    available: bool = False


class SchemaManager:
    """Discover and manage offline validation schemas.

    Searches for schemas in the configured directory and provides
    lxml XMLSchema / XSLT objects for validation.
    """

    def __init__(self, schema_dir: Path | None = None) -> None:
        self.schema_dir = schema_dir or _DEFAULT_SCHEMA_DIR
        self._xsd_cache: dict[SchemaType, etree.XMLSchema] = {}
        self._xslt_cache: dict[SchemaType, etree.XSLT] = {}
        self._schemas: dict[SchemaType, SchemaInfo] = {}
        self._discover_schemas()

    def _discover_schemas(self) -> None:
        """Scan the schema directory for available validation artefacts."""
        if not self.schema_dir.exists():
            logger.info(
                "Schema-Verzeichnis nicht gefunden: %s – "
                "Offline-Validierung deaktiviert. "
                "Bitte scripts/download_schemas.sh ausführen.",
                self.schema_dir,
            )
            return

        # CII XSD (Factur-X)
        cii_xsd = self._find_file(
            self.schema_dir,
            ["cii/FACTUR-X_EN16931.xsd", "cii/*.xsd"],
        )
        if cii_xsd:
            self._schemas[SchemaType.CII_XSD] = SchemaInfo(
                schema_type=SchemaType.CII_XSD,
                path=cii_xsd,
                available=True,
            )

        # UBL XSD
        ubl_xsd = self._find_file(
            self.schema_dir,
            [
                "ubl/xsd/maindoc/UBL-Invoice-2.1.xsd",
                "ubl/xsdrt/maindoc/UBL-Invoice-2.1.xsd",
                "ubl/**/UBL-Invoice-2.1.xsd",
            ],
        )
        if ubl_xsd:
            self._schemas[SchemaType.UBL_XSD] = SchemaInfo(
                schema_type=SchemaType.UBL_XSD,
                path=ubl_xsd,
                available=True,
            )

        # XRechnung Schematron (compiled XSLT)
        xr_xslt = self._find_file(
            self.schema_dir,
            [
                "xrechnung-schematron/**/*.xsl",
                "xrechnung-schematron/**/*.xslt",
            ],
        )
        if xr_xslt:
            self._schemas[SchemaType.XRECHNUNG_SCHEMATRON] = SchemaInfo(
                schema_type=SchemaType.XRECHNUNG_SCHEMATRON,
                path=xr_xslt,
                available=True,
            )

        # EN 16931 CII Schematron
        en_cii = self._find_file(
            self.schema_dir,
            [
                "en16931/**/EN16931-CII-validation.xslt",
                "en16931/**/cii/**/*.xsl",
                "en16931/**/CII/**/*.xsl",
            ],
        )
        if en_cii:
            self._schemas[SchemaType.EN16931_CII_SCHEMATRON] = SchemaInfo(
                schema_type=SchemaType.EN16931_CII_SCHEMATRON,
                path=en_cii,
                available=True,
            )

        # EN 16931 UBL Schematron
        en_ubl = self._find_file(
            self.schema_dir,
            [
                "en16931/**/EN16931-UBL-validation.xslt",
                "en16931/**/ubl/**/*.xsl",
                "en16931/**/UBL/**/*.xsl",
            ],
        )
        if en_ubl:
            self._schemas[SchemaType.EN16931_UBL_SCHEMATRON] = SchemaInfo(
                schema_type=SchemaType.EN16931_UBL_SCHEMATRON,
                path=en_ubl,
                available=True,
            )

        available = [s.schema_type.value for s in self._schemas.values() if s.available]
        logger.info("Verfügbare Validierungsschemas: %s", available or "(keine)")

    def _find_file(self, base: Path, patterns: list[str]) -> Path | None:
        """Find the first file matching any of the given glob patterns."""
        for pattern in patterns:
            matches = sorted(base.glob(pattern))
            if matches:
                return matches[0]
        return None

    def is_available(self, schema_type: SchemaType) -> bool:
        """Check whether a schema type is available for offline validation."""
        info = self._schemas.get(schema_type)
        return info.available if info else False

    def get_xsd(self, schema_type: SchemaType) -> etree.XMLSchema | None:
        """Load and cache an XSD schema. Returns None if not available."""
        if schema_type in self._xsd_cache:
            return self._xsd_cache[schema_type]

        info = self._schemas.get(schema_type)
        if not info or not info.available:
            return None

        try:
            with open(info.path, "rb") as f:
                schema_doc = etree.parse(f)
            xsd = etree.XMLSchema(schema_doc)
            self._xsd_cache[schema_type] = xsd
            logger.debug("XSD geladen: %s (%s)", schema_type.value, info.path)
            return xsd
        except Exception as e:
            logger.warning("XSD-Schema konnte nicht geladen werden (%s): %s", info.path, e)
            return None

    def get_xslt(self, schema_type: SchemaType) -> etree.XSLT | None:
        """Load and cache an XSLT (compiled Schematron). Returns None if not available."""
        if schema_type in self._xslt_cache:
            return self._xslt_cache[schema_type]

        info = self._schemas.get(schema_type)
        if not info or not info.available:
            return None

        try:
            xslt_doc = etree.parse(str(info.path))
            xslt = etree.XSLT(xslt_doc)
            self._xslt_cache[schema_type] = xslt
            logger.debug("XSLT geladen: %s (%s)", schema_type.value, info.path)
            return xslt
        except Exception as e:
            logger.warning("XSLT konnte nicht geladen werden (%s): %s", info.path, e)
            return None

    def list_available(self) -> list[SchemaInfo]:
        """Return a list of all available schemas."""
        return [s for s in self._schemas.values() if s.available]
