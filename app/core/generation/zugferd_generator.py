"""Generate ZUGFeRD PDF/A-3 by embedding CII-XML into a PDF.

Uses factur-x to combine a visual PDF with the machine-readable XML.
"""

from __future__ import annotations

from pathlib import Path

from facturx import generate_from_file

from app.core.generation.cii_generator import CIIGenerator
from app.models.invoice import Invoice, ZUGFeRDProfile

# Map our profiles to factur-x flavor strings
_FACTURX_FLAVOR_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.MINIMUM: "factur-x-minimum",
    ZUGFeRDProfile.BASIC_WL: "factur-x-basicwl",
    ZUGFeRDProfile.BASIC: "factur-x-basic",
    ZUGFeRDProfile.EN16931: "factur-x-en16931",
    ZUGFeRDProfile.EXTENDED: "factur-x-extended",
    ZUGFeRDProfile.XRECHNUNG: "factur-x-xrechnung",
}


class ZUGFeRDGenerator:
    """Generate a ZUGFeRD PDF/A-3 invoice."""

    def __init__(self, invoice: Invoice) -> None:
        self.invoice = invoice

    def generate(self, pdf_path: Path, output_path: Path) -> Path:
        """Embed CII-XML into a visual PDF to create a ZUGFeRD PDF/A-3.

        Args:
            pdf_path: Path to the visual PDF (rendered from HTML template).
            output_path: Where to write the ZUGFeRD PDF/A-3.

        Returns:
            Path to the generated ZUGFeRD PDF file.
        """
        # Step 1: Generate CII-XML
        cii_gen = CIIGenerator(self.invoice)
        xml_bytes = cii_gen.generate()

        # Step 2: Embed XML into PDF/A-3
        flavor = _FACTURX_FLAVOR_MAP.get(self.invoice.profile, "factur-x-en16931")

        with open(pdf_path, "rb") as pdf_file:
            zugferd_pdf = generate_from_file(
                pdf_file,
                xml_bytes,
                flavor=flavor,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as out:
            out.write(zugferd_pdf)

        return output_path
