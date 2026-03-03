"""XSD validation for CII and UBL XML documents using lxml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class ValidationResult:
    """Result of an XML validation run."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class XSDValidator:
    """Validate XML documents against XSD schemas.

    For inline (fast) validation. Full Schematron validation
    requires the KoSIT Validator (Java sidecar).
    """

    def __init__(self, schema_path: Path) -> None:
        with open(schema_path, "rb") as f:
            schema_doc = etree.parse(f)
        self.schema = etree.XMLSchema(schema_doc)

    def validate(self, xml_bytes: bytes) -> ValidationResult:
        """Validate XML bytes against the loaded XSD schema."""
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return ValidationResult(is_valid=False, errors=[f"XML parse error: {e}"])

        is_valid = self.schema.validate(doc)
        errors = [str(err) for err in self.schema.error_log] if not is_valid else []
        return ValidationResult(is_valid=is_valid, errors=errors)

    def validate_file(self, xml_path: Path) -> ValidationResult:
        """Validate an XML file against the loaded XSD schema."""
        with open(xml_path, "rb") as f:
            return self.validate(f.read())
