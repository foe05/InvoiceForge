"""Central conversion pipeline – orchestrates the full Invoice → E-Rechnung workflow.

Usage:
    from app.core.pipeline import ConversionPipeline, ConversionResult

    pipeline = ConversionPipeline()
    result = pipeline.convert(invoice)
    # result.xml_bytes   → CII-XML or UBL-XML
    # result.pdf_bytes   → ZUGFeRD PDF/A-3  (if requested)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.generation.cii_generator import CIIGenerator
from app.core.generation.pdf_renderer import PDFRenderer
from app.core.generation.ubl_generator import UBLGenerator
from app.core.generation.zugferd_generator import ZUGFeRDGenerator
from app.core.validation.xsd_validator import ValidationResult, XSDValidator
from app.models.invoice import Invoice, OutputFormat


@dataclass
class ConversionResult:
    """Result of a conversion pipeline run."""

    invoice: Invoice
    xml_bytes: bytes
    pdf_bytes: bytes | None = None
    validation: ValidationResult | None = None
    output_format: OutputFormat = OutputFormat.ZUGFERD_PDF
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class ConversionPipeline:
    """Orchestrate the end-to-end conversion of an Invoice to E-Rechnung output."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self.pdf_renderer = PDFRenderer(template_dir=template_dir)

    def convert(self, invoice: Invoice) -> ConversionResult:
        """Run the full conversion pipeline.

        Steps:
            1. Generate XML (CII for ZUGFeRD/XRechnung-CII, UBL for XRechnung-UBL)
            2. If ZUGFeRD PDF requested: render visual PDF, embed CII-XML
            3. Return result

        Returns:
            ConversionResult with XML bytes, optionally PDF bytes, and validation info.
        """
        errors: list[str] = []
        xml_bytes = b""
        pdf_bytes: bytes | None = None

        # Step 1: Generate XML based on output format
        if invoice.output_format == OutputFormat.XRECHNUNG_UBL:
            try:
                ubl_gen = UBLGenerator(invoice)
                xml_bytes = ubl_gen.generate()
            except Exception as e:
                errors.append(f"UBL-XML generation failed: {e}")
                return ConversionResult(
                    invoice=invoice,
                    xml_bytes=xml_bytes,
                    output_format=invoice.output_format,
                    errors=errors,
                )
        else:
            # CII-XML for ZUGFeRD and XRechnung-CII
            try:
                cii_gen = CIIGenerator(invoice)
                xml_bytes = cii_gen.generate()
            except Exception as e:
                errors.append(f"CII-XML generation failed: {e}")
                return ConversionResult(
                    invoice=invoice,
                    xml_bytes=xml_bytes,
                    output_format=invoice.output_format,
                    errors=errors,
                )

        # Step 2: If ZUGFeRD PDF, render visual PDF and embed XML
        if invoice.output_format == OutputFormat.ZUGFERD_PDF:
            try:
                visual_pdf = self.pdf_renderer.render_pdf(invoice)
                zugferd_gen = ZUGFeRDGenerator(invoice)
                pdf_bytes = zugferd_gen.generate_from_pdf_bytes(visual_pdf)
            except Exception as e:
                errors.append(f"ZUGFeRD PDF generation failed: {e}")

        return ConversionResult(
            invoice=invoice,
            xml_bytes=xml_bytes,
            pdf_bytes=pdf_bytes,
            output_format=invoice.output_format,
            errors=errors,
        )

    def convert_to_file(
        self, invoice: Invoice, output_dir: Path
    ) -> tuple[ConversionResult, Path]:
        """Convert and write the result to a file.

        Returns:
            Tuple of (ConversionResult, output_file_path).
        """
        result = self.convert(invoice)
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")

        if invoice.output_format == OutputFormat.ZUGFERD_PDF and result.pdf_bytes:
            out_path = output_dir / f"{safe_name}.pdf"
            out_path.write_bytes(result.pdf_bytes)
        else:
            out_path = output_dir / f"{safe_name}.xml"
            out_path.write_bytes(result.xml_bytes)

        return result, out_path
