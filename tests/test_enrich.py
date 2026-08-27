"""Tests for the enrich workflow (PDF in -> conformant ZUGFeRD-PDF out).

Focuses on the pipeline-level changes (source_pdf_bytes, force_rerender,
auto-fallback to rerender) and on the shared extraction chain helper.
The HTTP layer is exercised indirectly via the pipeline; full request-cycle
tests live in test_api.py.
"""

from __future__ import annotations

import pytest

from app.core.extraction.chain import ExtractionFailed, run_extraction_chain
from app.core.pipeline import ConversionPipeline
from app.models.invoice import OutputFormat


# --- Pipeline: source_pdf_bytes happy path + fallback ---


def test_convert_with_source_pdf_uses_original(sample_invoice):
    """When source_pdf_bytes is a valid PDF, the result PDF embeds XML into
    that source verbatim and reports pdf_source='original'."""
    sample_invoice.output_format = OutputFormat.ZUGFERD_PDF

    pipeline = ConversionPipeline(validate=False)
    # Render any valid PDF first so we have realistic source bytes
    source_bytes = pipeline.pdf_renderer.render_pdf(sample_invoice)

    result = pipeline.convert(sample_invoice, source_pdf_bytes=source_bytes)

    assert result.success, f"errors: {result.errors}"
    assert result.pdf_bytes is not None
    assert result.pdf_source == "original"
    # No fallback warning expected on this path
    assert not any("fehlgeschlagen" in w.lower() for w in result.warnings)


def test_convert_with_broken_source_pdf_falls_back_to_rerender(sample_invoice):
    """When source_pdf_bytes is malformed, factur-x rejects it. The pipeline
    must fall back to rerendering the visual PDF and emit a warning, not an
    error.
    """
    sample_invoice.output_format = OutputFormat.ZUGFERD_PDF

    pipeline = ConversionPipeline(validate=False)
    result = pipeline.convert(sample_invoice, source_pdf_bytes=b"not a pdf")

    assert result.success, f"errors: {result.errors}"
    assert result.pdf_bytes is not None
    assert result.pdf_source == "rerender"
    assert any("Original" in w for w in result.warnings), (
        f"expected fallback warning, got: {result.warnings}"
    )


def test_convert_with_force_rerender_ignores_source(sample_invoice):
    """force_rerender=True must skip the original even if source_pdf_bytes
    is given and valid."""
    sample_invoice.output_format = OutputFormat.ZUGFERD_PDF

    pipeline = ConversionPipeline(validate=False)
    source_bytes = pipeline.pdf_renderer.render_pdf(sample_invoice)

    result = pipeline.convert(
        sample_invoice, source_pdf_bytes=source_bytes, force_rerender=True
    )

    assert result.success
    assert result.pdf_source == "rerender"
    # No fallback warning, since we never tried the original
    assert not any("Einbettung in Original-PDF" in w for w in result.warnings)


def test_convert_without_source_renders_visual_as_before(sample_invoice):
    """No source_pdf_bytes -> behave exactly like before: rerender path."""
    sample_invoice.output_format = OutputFormat.ZUGFERD_PDF

    pipeline = ConversionPipeline(validate=False)
    result = pipeline.convert(sample_invoice)

    assert result.success
    assert result.pdf_bytes is not None
    assert result.pdf_source == "rerender"


# --- Extraction chain ---


@pytest.mark.asyncio
async def test_extraction_chain_succeeds_on_zugferd_pdf(sample_invoice):
    """A freshly produced ZUGFeRD PDF goes through the chain via the
    structured extractor — no LLM call needed."""
    sample_invoice.output_format = OutputFormat.ZUGFERD_PDF
    pipeline = ConversionPipeline(validate=False)
    result = pipeline.convert(sample_invoice)
    assert result.pdf_bytes is not None

    ex = await run_extraction_chain(result.pdf_bytes, ".pdf")
    assert ex.method == "structured"
    assert ex.invoice.invoice_number == sample_invoice.invoice_number


@pytest.mark.asyncio
async def test_extraction_chain_raises_on_garbage_without_llm():
    """Raw garbage with no LLM available must fail loudly with an
    aggregated error mentioning each method that was tried.
    """
    with pytest.raises(ExtractionFailed) as excinfo:
        await run_extraction_chain(b"%PDF-not-real", ".pdf", allow_llm=False)
    msg = str(excinfo.value)
    assert "structured" in msg


@pytest.mark.asyncio
async def test_extraction_chain_reports_llm_unconfigured(monkeypatch):
    """When LLM_PROVIDER is NONE, the chain must surface that fact in the
    aggregated failure message so callers know what to fix."""
    from app.config import LLMProvider, settings

    monkeypatch.setattr(settings, "llm_provider", LLMProvider.NONE)
    with pytest.raises(ExtractionFailed) as excinfo:
        await run_extraction_chain(b"%PDF-not-real", ".pdf")
    assert "LLM_PROVIDER not configured" in str(excinfo.value)
