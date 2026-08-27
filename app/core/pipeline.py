"""Central conversion pipeline – orchestrates the full Invoice → E-Rechnung workflow.

Usage:
    from app.core.pipeline import ConversionPipeline, ConversionResult

    pipeline = ConversionPipeline()
    result = pipeline.convert(invoice)
    # result.xml_bytes   → CII-XML or UBL-XML
    # result.pdf_bytes   → ZUGFeRD PDF/A-3  (if requested)
    # result.validation  → FullValidationResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.generation.cii_generator import CIIGenerator
from app.core.generation.pdf_renderer import PDFRenderer
from app.core.generation.ubl_generator import UBLGenerator
from app.core.generation.zugferd_generator import ZUGFeRDGenerator
from app.core.validation.validator import FullValidationResult, InvoiceValidator, ValidationLevel
from app.models.invoice import Invoice, OutputFormat

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    """Result of a conversion pipeline run."""

    invoice: Invoice
    xml_bytes: bytes
    pdf_bytes: bytes | None = None
    validation: FullValidationResult | None = None
    output_format: OutputFormat = OutputFormat.ZUGFERD_PDF
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # "original" if pdf_bytes is the user's source PDF with XML embedded,
    # "rerender" if it was generated from the Jinja invoice template,
    # None if no PDF was produced.
    pdf_source: str | None = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def is_valid(self) -> bool:
        """Prüfe ob die Validierung bestanden wurde."""
        if self.validation is None:
            return True
        return self.validation.is_valid


class ConversionPipeline:
    """Orchestrate the end-to-end conversion of an Invoice to E-Rechnung output."""

    def __init__(
        self,
        template_dir: Path | None = None,
        validate: bool = True,
        validator: InvoiceValidator | None = None,
    ) -> None:
        self.pdf_renderer = PDFRenderer(template_dir=template_dir)
        self._validate = validate
        self._validator = validator

    def _get_validator(self) -> InvoiceValidator:
        """Lazy-init the validator."""
        if self._validator is None:
            from app.config import settings

            self._validator = InvoiceValidator(kosit_url=settings.kosit_validator_url)
        return self._validator

    def convert(
        self,
        invoice: Invoice,
        source_pdf_bytes: bytes | None = None,
        force_rerender: bool = False,
    ) -> ConversionResult:
        """Run the full conversion pipeline.

        Steps:
            1. Generate XML (CII for ZUGFeRD/XRechnung-CII, UBL for XRechnung-UBL)
            2. Validate generated XML (XSD + Schematron)
            3. If ZUGFeRD PDF requested:
                - if source_pdf_bytes is given and not force_rerender, embed XML
                  into that original PDF; on failure fall back to a rerendered
                  visual PDF and emit a warning
                - otherwise (or after fallback) render visual PDF from template
                  and embed XML
            4. Return result with validation info

        Args:
            invoice: The semantic invoice to convert.
            source_pdf_bytes: Optional original PDF bytes (e.g., the user's
                uploaded invoice). When set and the output format is
                ZUGFERD_PDF, the XML is embedded into these bytes verbatim,
                preserving the original visual appearance.
            force_rerender: If True, always render a fresh visual PDF from the
                Jinja template, ignoring source_pdf_bytes. Use when strict
                PDF/A-3 conformance is required.

        Returns:
            ConversionResult with XML bytes, optionally PDF bytes, and validation info.
        """
        errors: list[str] = []
        warnings: list[str] = []
        xml_bytes = b""
        pdf_bytes: bytes | None = None
        pdf_source: str | None = None
        validation: FullValidationResult | None = None

        # Step 1: Generate XML based on output format
        if invoice.output_format == OutputFormat.XRECHNUNG_UBL:
            try:
                ubl_gen = UBLGenerator(invoice)
                xml_bytes = ubl_gen.generate()
            except Exception as e:
                errors.append(f"UBL-XML-Generierung fehlgeschlagen: {e}")
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
                errors.append(f"CII-XML-Generierung fehlgeschlagen: {e}")
                return ConversionResult(
                    invoice=invoice,
                    xml_bytes=xml_bytes,
                    output_format=invoice.output_format,
                    errors=errors,
                )

        # Step 2: Validate generated XML
        if self._validate and xml_bytes:
            try:
                validator = self._get_validator()
                validation = validator.validate(xml_bytes)

                if not validation.is_valid:
                    for err in validation.errors:
                        errors.append(f"Validierung: {err.message}")
                for warn in validation.warnings:
                    warnings.append(f"Validierung: {warn.message}")

                if validation.is_valid:
                    logger.info(
                        "Validierung bestanden: %s (%s)",
                        invoice.invoice_number,
                        ", ".join(validation.schemas_used),
                    )
                else:
                    logger.warning(
                        "Validierung fehlgeschlagen (%d Fehler): %s",
                        len(validation.errors),
                        invoice.invoice_number,
                    )
            except Exception as e:
                logger.warning("Validierung übersprungen: %s", e)
                warnings.append(f"Validierung konnte nicht durchgeführt werden: {e}")

        # Step 3: If ZUGFeRD PDF, embed XML into a visual PDF
        if invoice.output_format == OutputFormat.ZUGFERD_PDF:
            zugferd_gen = ZUGFeRDGenerator(invoice)

            use_original = source_pdf_bytes is not None and not force_rerender
            if use_original:
                try:
                    pdf_bytes = zugferd_gen.generate_from_pdf_bytes(source_pdf_bytes)
                    pdf_source = "original"
                except Exception as e:
                    logger.warning(
                        "Einbettung ins Original-PDF fehlgeschlagen, fallback auf Rerender: %s", e
                    )
                    warnings.append(
                        "Einbettung in Original-PDF fehlgeschlagen "
                        f"({e}). Visual-PDF aus Template erzeugt — "
                        "Optik weicht vom Original ab."
                    )
                    use_original = False  # fall through to rerender

            if not use_original:
                try:
                    visual_pdf = self.pdf_renderer.render_pdf(invoice)
                    pdf_bytes = zugferd_gen.generate_from_pdf_bytes(visual_pdf)
                    pdf_source = "rerender"
                except Exception as e:
                    errors.append(f"ZUGFeRD-PDF-Generierung fehlgeschlagen: {e}")

        return ConversionResult(
            invoice=invoice,
            xml_bytes=xml_bytes,
            pdf_bytes=pdf_bytes,
            validation=validation,
            output_format=invoice.output_format,
            errors=errors,
            warnings=warnings,
            pdf_source=pdf_source,
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
