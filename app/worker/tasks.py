"""ARQ background tasks for long-running invoice processing.

Tasks are enqueued by the API and processed by an ARQ worker.
Results are persisted to the database via InvoiceRecord.

Usage:
    # Start the worker:
    arq app.worker.settings.WorkerSettings

    # Enqueue from the API:
    job = await arq_pool.enqueue_job("convert_invoice", invoice_data, tenant_id)
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from app.config import settings
from app.core.extraction.xml_extractor import XMLExtractor
from app.core.pipeline import ConversionPipeline
from app.core.storage.local_storage import LocalStorage
from app.models.invoice import Invoice

logger = logging.getLogger(__name__)

_storage = LocalStorage()


async def convert_invoice(
    ctx: dict,
    invoice_json: str,
    tenant_id: str,
    job_id: str | None = None,
) -> dict:
    """Background task: convert an Invoice to E-Rechnung output.

    Args:
        ctx: ARQ context (contains redis connection).
        invoice_json: Serialized Invoice model (JSON string).
        tenant_id: Tenant identifier for file isolation.
        job_id: Optional pre-assigned job ID.

    Returns:
        Dict with job_id, success flag, output_path, and errors.
    """
    job_id = job_id or uuid.uuid4().hex[:12]
    logger.info("Job %s: Starting conversion for tenant %s", job_id, tenant_id)

    try:
        invoice = Invoice.model_validate_json(invoice_json)
    except Exception as e:
        logger.error("Job %s: Invalid invoice data: %s", job_id, e)
        return {"job_id": job_id, "success": False, "errors": [str(e)]}

    pipeline = ConversionPipeline()
    result = pipeline.convert(invoice)

    if not result.success:
        logger.error("Job %s: Conversion failed: %s", job_id, result.errors)
        return {"job_id": job_id, "success": False, "errors": result.errors}

    # Save output file
    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
    if result.pdf_bytes:
        output_path = _storage.save_output(tenant_id, f"{safe_name}.pdf", result.pdf_bytes)
    else:
        output_path = _storage.save_output(tenant_id, f"{safe_name}.xml", result.xml_bytes)

    logger.info("Job %s: Conversion complete -> %s", job_id, output_path)
    return {
        "job_id": job_id,
        "success": True,
        "output_path": str(output_path),
        "output_format": invoice.output_format.value,
        "errors": [],
    }


async def extract_invoice(
    ctx: dict,
    file_bytes: bytes,
    filename: str,
    tenant_id: str,
    job_id: str | None = None,
) -> dict:
    """Background task: extract invoice data from uploaded file.

    Supports structured XML/PDF extraction. For unstructured PDFs, the LLM
    extraction pipeline is triggered automatically when configured.
    """
    job_id = job_id or uuid.uuid4().hex[:12]
    logger.info("Job %s: Starting extraction of %s for tenant %s", job_id, filename, tenant_id)

    # Save input file
    input_path = _storage.save_input(tenant_id, filename, file_bytes)

    suffix = Path(filename).suffix.lower()

    # Try structured extraction first (XML / ZUGFeRD PDF)
    try:
        extractor = XMLExtractor()
        invoice = extractor.extract_from_file(input_path)
        logger.info("Job %s: Structured extraction successful", job_id)
        return {
            "job_id": job_id,
            "success": True,
            "invoice": json.loads(invoice.model_dump_json()),
            "extraction_method": "structured",
            "errors": [],
        }
    except Exception as e:
        logger.info("Job %s: Structured extraction failed (%s), trying LLM", job_id, e)

    # Fallback: LLM-based extraction for unstructured PDFs
    if suffix == ".pdf":
        try:
            from app.core.extraction.llm_extractor import LLMExtractor
            from app.core.extraction.pdf_extractor import PDFExtractor

            pdf_ext = PDFExtractor(input_path)
            text = pdf_ext.extract_text()
            tables = pdf_ext.extract_tables()

            llm_ext = LLMExtractor()
            invoice = await llm_ext.extract(text, tables)
            logger.info("Job %s: LLM extraction successful", job_id)
            return {
                "job_id": job_id,
                "success": True,
                "invoice": json.loads(invoice.model_dump_json()),
                "extraction_method": "llm",
                "errors": [],
            }
        except Exception as e:
            logger.error("Job %s: LLM extraction failed: %s", job_id, e)
            return {"job_id": job_id, "success": False, "errors": [str(e)]}

    return {
        "job_id": job_id,
        "success": False,
        "errors": [f"Could not extract invoice data from {filename}"],
    }


async def validate_invoice(
    ctx: dict,
    xml_bytes: bytes,
    use_kosit: bool = True,
    job_id: str | None = None,
) -> dict:
    """Background task: validate XML with XSD and optionally KoSIT.

    Args:
        ctx: ARQ context.
        xml_bytes: Raw CII or UBL XML bytes.
        use_kosit: Whether to run KoSIT Schematron validation.
        job_id: Optional job ID.
    """
    job_id = job_id or uuid.uuid4().hex[:12]
    errors: list[str] = []
    warnings: list[str] = []

    # Step 1: XSD validation via drafthorse
    try:
        from drafthorse.utils import validate_xml
        validate_xml(xml_bytes, schema="FACTUR-X_EN16931")
    except Exception as e:
        errors.append(f"XSD validation: {e}")

    # Step 2: KoSIT Schematron validation (if available)
    kosit_result = None
    if use_kosit:
        from app.core.validation.kosit_client import KoSITClient
        client = KoSITClient()
        kosit_result = await client.validate(xml_bytes)
        if not kosit_result.is_valid:
            errors.extend(kosit_result.errors)
        warnings.extend(kosit_result.warnings)

    return {
        "job_id": job_id,
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "kosit_available": kosit_result is not None and "not reachable" not in str(kosit_result.errors),
    }
