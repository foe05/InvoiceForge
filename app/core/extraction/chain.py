"""Shared extraction chain used by /extract, /enrich, and the CLI.

The chain tries extractors in order from cheapest/most-precise to most-expensive:

    1. XMLExtractor       — structured CII/UBL/ZUGFeRD (no LLM, deterministic)
    2. Invoice2DataExtractor — template matching (PDFs only, optional dep)
    3. LLMExtractor       — LLM-based extraction (PDFs only, requires LLM_PROVIDER)

Each extractor is awaited only if the previous one fails. The first success
wins. If all extractors fail or are unavailable, ExtractionFailed is raised
with a single aggregated message that pinpoints what was tried.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.config import LLMProvider, settings
from app.core.extraction.xml_extractor import XMLExtractor
from app.models.invoice import Invoice


class ExtractionFailed(Exception):
    """Raised when no extractor in the chain produces a valid Invoice."""


@dataclass
class ExtractionResult:
    invoice: Invoice
    method: str  # "structured" | "invoice2data" | "llm"


async def run_extraction_chain(
    content: bytes,
    suffix: str,
    *,
    allow_llm: bool = True,
) -> ExtractionResult:
    """Run the standard extraction fallback chain on raw file bytes.

    Args:
        content: The raw file bytes (PDF or XML).
        suffix: File suffix including dot, e.g. ".pdf" or ".xml". Drives
            which fallback extractors are eligible (LLM/i2d are PDF-only).
        allow_llm: When False, the LLM step is skipped even if configured.
            Useful for headless callers that want deterministic behavior.

    Returns:
        ExtractionResult with the parsed Invoice and the method that won.

    Raises:
        ExtractionFailed: when no extractor produced a result.
    """
    failures: list[str] = []

    # Step 1: structured (CII/UBL/ZUGFeRD)
    with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        tmp_path = Path(tmp.name)

        try:
            invoice = XMLExtractor().extract_from_file(tmp_path)
            return ExtractionResult(invoice=invoice, method="structured")
        except Exception as e:
            failures.append(f"structured: {e}")

        if suffix == ".pdf":
            # Step 2: invoice2data templates
            try:
                from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

                invoice = Invoice2DataExtractor().extract(tmp_path)
                return ExtractionResult(invoice=invoice, method="invoice2data")
            except ImportError:
                failures.append("invoice2data: extra not installed")
            except Exception as e:
                failures.append(f"invoice2data: {e}")

            # Step 3: LLM
            if allow_llm and settings.llm_provider != LLMProvider.NONE:
                try:
                    from app.core.extraction.llm_extractor import LLMExtractor
                    from app.core.extraction.pdf_extractor import PDFExtractor

                    pdf_ext = PDFExtractor(tmp_path)
                    text = pdf_ext.extract_text()
                    tables = pdf_ext.extract_tables()

                    invoice = await LLMExtractor().extract(text, tables)
                    return ExtractionResult(invoice=invoice, method="llm")
                except Exception as e:
                    failures.append(f"llm: {e}")
            elif allow_llm:
                failures.append("llm: LLM_PROVIDER not configured")

    raise ExtractionFailed(
        "Keine Extraktionsmethode war erfolgreich. Versucht: " + "; ".join(failures)
    )
