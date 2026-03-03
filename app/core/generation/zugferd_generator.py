"""Generate ZUGFeRD PDF/A-3 by embedding CII-XML into a PDF.

Uses factur-x to combine a visual PDF with the machine-readable XML.
"""

from __future__ import annotations

from pathlib import Path

from facturx import generate_from_binary

from app.core.generation.cii_generator import CIIGenerator
from app.models.invoice import Invoice, ZUGFeRDProfile

# Map our profiles to factur-x level strings
_LEVEL_MAP: dict[ZUGFeRDProfile, str] = {
    ZUGFeRDProfile.MINIMUM: "minimum",
    ZUGFeRDProfile.BASIC_WL: "basicwl",
    ZUGFeRDProfile.BASIC: "basic",
    ZUGFeRDProfile.EN16931: "en16931",
    ZUGFeRDProfile.EXTENDED: "extended",
    ZUGFeRDProfile.XRECHNUNG: "en16931",
}


class ZUGFeRDGenerator:
    """Generate a ZUGFeRD PDF/A-3 invoice."""

    def __init__(self, invoice: Invoice) -> None:
        self.invoice = invoice

    def generate_from_pdf_bytes(self, pdf_bytes: bytes) -> bytes:
        """Embed CII-XML into visual PDF bytes to create a ZUGFeRD PDF/A-3.

        Args:
            pdf_bytes: The visual PDF as bytes.

        Returns:
            ZUGFeRD PDF/A-3 file contents as bytes.
        """
        # Step 1: Generate CII-XML
        cii_gen = CIIGenerator(self.invoice)
        xml_bytes = cii_gen.generate()

        # Step 2: Embed XML into PDF/A-3 via factur-x
        level = _LEVEL_MAP.get(self.invoice.profile, "en16931")
        zugferd_pdf = generate_from_binary(
            pdf_bytes,
            xml_bytes,
            flavor="factur-x",
            level=level,
            check_xsd=True,
            pdf_metadata={
                "author": self.invoice.seller.name,
                "title": f"Rechnung {self.invoice.invoice_number}",
                "subject": (
                    f"ZUGFeRD {self.invoice.profile.value} – "
                    f"Rechnung {self.invoice.invoice_number}"
                ),
            },
        )
        return zugferd_pdf

    def generate(self, pdf_path: Path, output_path: Path) -> Path:
        """Embed CII-XML into a visual PDF file to create a ZUGFeRD PDF/A-3.

        Args:
            pdf_path: Path to the visual PDF (rendered from HTML template).
            output_path: Where to write the ZUGFeRD PDF/A-3.

        Returns:
            Path to the generated ZUGFeRD PDF file.
        """
        pdf_bytes = pdf_path.read_bytes()
        zugferd_pdf = self.generate_from_pdf_bytes(pdf_bytes)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(zugferd_pdf)
        return output_path
