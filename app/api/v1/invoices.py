"""Invoice API endpoints – convert, validate, extract, and download invoices."""

from __future__ import annotations

import logging
import uuid
from base64 import b64encode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth.dependencies import require_user
from app.config import settings
from app.core.extraction.chain import ExtractionFailed, run_extraction_chain
from app.core.pipeline import ConversionPipeline, ConversionResult
from app.db.models import User
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

logger = logging.getLogger(__name__)

# Every /api/v1/invoices/* endpoint requires either a session cookie or a
# valid X-API-Key header. Both paths are handled by require_user.
router = APIRouter(dependencies=[Depends(require_user)])

_pipeline = ConversionPipeline()


# --- Response schemas ---


class ConvertResponse(BaseModel):
    job_id: str
    success: bool
    invoice_number: str
    output_format: str
    errors: list[str] = []
    xml_base64: str | None = None
    pdf_base64: str | None = None


class ExtractResponse(BaseModel):
    job_id: str
    success: bool
    invoice: Invoice | None = None
    extraction_method: str = "structured"
    errors: list[str] = []


class ValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    kosit_available: bool = False


class EnrichResponse(BaseModel):
    job_id: str
    success: bool
    invoice: Invoice | None = None
    extraction_method: str = ""
    pdf_source: str | None = None  # "original" | "rerender" | None
    pdf_base64: str | None = None
    errors: list[str] = []
    warnings: list[str] = []


class InvoiceRecordResponse(BaseModel):
    id: str
    invoice_number: str
    seller_name: str
    buyer_name: str
    gross_amount: float
    currency: str
    status: str
    output_format: str
    created_at: str


class InvoiceListResponse(BaseModel):
    records: list[InvoiceRecordResponse]
    total: int


# --- DB helpers (graceful when DB unavailable) ---


async def _try_persist_conversion(
    invoice: Invoice,
    job_id: str,
    success: bool,
    errors: list[str],
    tenant_id: str,
) -> None:
    """Attempt to persist a conversion record to the database, scoped to a tenant."""
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.create_record(invoice, tenant_id)
            await svc.update_status(
                record.id,
                status="completed" if success else "failed",
                error_message="; ".join(errors) if errors else None,
            )
            await session.commit()
    except Exception as e:
        logger.debug("DB persistence skipped: %s", e)


async def _try_persist_extraction(
    invoice: Invoice | None,
    job_id: str,
    method: str,
    success: bool,
    errors: list[str],
    tenant_id: str,
) -> None:
    """Attempt to persist an extraction record to the database, scoped to a tenant."""
    if not invoice or not success:
        return
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.create_record(invoice, tenant_id)
            await svc.update_status(record.id, status="extracted")
            await session.commit()
    except Exception as e:
        logger.debug("DB persistence skipped: %s", e)


# --- Endpoints ---


@router.post(
    "/convert",
    response_model=ConvertResponse,
    summary="Convert invoice data to E-Rechnung",
)
async def convert_invoice(
    invoice: Invoice,
    user: User = Depends(require_user),
) -> ConvertResponse:
    """Convert structured invoice data to ZUGFeRD PDF, XRechnung CII, or XRechnung UBL.

    Accepts a complete Invoice object (EN 16931) and returns the
    generated output as base64-encoded data.
    """
    job_id = uuid.uuid4().hex[:12]
    logger.info("Convert job %s: %s -> %s", job_id, invoice.invoice_number, invoice.output_format.value)

    result = _pipeline.convert(invoice)

    # Persist to DB (non-blocking, best-effort), scoped to the caller's tenant.
    await _try_persist_conversion(
        invoice, job_id, result.success, result.errors, str(user.tenant_id)
    )

    return ConvertResponse(
        job_id=job_id,
        success=result.success,
        invoice_number=invoice.invoice_number,
        output_format=invoice.output_format.value,
        errors=result.errors,
        xml_base64=b64encode(result.xml_bytes).decode() if result.xml_bytes else None,
        pdf_base64=b64encode(result.pdf_bytes).decode() if result.pdf_bytes else None,
    )


@router.post(
    "/convert/download",
    summary="Convert and download as file",
)
async def convert_and_download(invoice: Invoice) -> Response:
    """Convert invoice and return the generated file directly."""
    result = _pipeline.convert(invoice)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": result.errors},
        )

    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")

    if invoice.output_format == OutputFormat.ZUGFERD_PDF and result.pdf_bytes:
        return Response(
            content=result.pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )

    return Response(
        content=result.xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xml"'},
    )


@router.post(
    "/extract",
    response_model=ExtractResponse,
    summary="Extract invoice data from uploaded file",
)
async def extract_invoice(
    file: UploadFile,
    user: User = Depends(require_user),
) -> ExtractResponse:
    """Upload a ZUGFeRD PDF, XRechnung XML, or unstructured PDF and extract
    the invoice data. Falls back to LLM-based extraction for unstructured PDFs
    when configured.
    """
    job_id = uuid.uuid4().hex[:12]
    tenant_id = str(user.tenant_id)

    allowed_types = ("application/pdf", "application/xml", "text/xml")
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported: {file.content_type}. Use PDF or XML.",
        )

    content = await file.read()
    suffix = ".pdf" if "pdf" in (file.content_type or "") else ".xml"
    logger.info("Extract job %s: %s (%s)", job_id, file.filename, suffix)

    try:
        result = await run_extraction_chain(content, suffix)
    except ExtractionFailed as e:
        return ExtractResponse(job_id=job_id, success=False, errors=[str(e)])

    await _try_persist_extraction(
        result.invoice, job_id, result.method, True, [], tenant_id
    )
    return ExtractResponse(
        job_id=job_id,
        success=True,
        invoice=result.invoice,
        extraction_method=result.method,
    )


# --- Enrich: PDF in, conformant ZUGFeRD-PDF (original + embedded XML) out ---


async def _run_enrich(
    content: bytes,
    suffix: str,
    *,
    profile: ZUGFeRDProfile,
    force_rerender: bool,
    tenant_id: str,
    job_id: str,
) -> tuple[Invoice | None, str, ConversionResult | None, list[str], list[str]]:
    """Shared core for enrich endpoints. Returns (invoice, method, result, errors, warnings)."""
    if suffix != ".pdf":
        return (
            None,
            "",
            None,
            ["Anreichern unterstützt nur PDF-Eingaben."],
            [],
        )

    try:
        ex = await run_extraction_chain(content, suffix)
    except ExtractionFailed as e:
        return (None, "", None, [str(e)], [])

    invoice = ex.invoice
    invoice.output_format = OutputFormat.ZUGFERD_PDF
    invoice.profile = profile

    result = _pipeline.convert(
        invoice,
        source_pdf_bytes=None if force_rerender else content,
        force_rerender=force_rerender,
    )

    await _try_persist_conversion(invoice, job_id, result.success, result.errors, tenant_id)

    return invoice, ex.method, result, list(result.errors), list(result.warnings)


@router.post(
    "/enrich",
    response_model=EnrichResponse,
    summary="Enrich a PDF: extract data and embed XML to produce a ZUGFeRD PDF",
)
async def enrich_invoice(
    file: UploadFile,
    profile: ZUGFeRDProfile = Form(ZUGFeRDProfile.EN16931),
    force_rerender: bool = Form(False),
    user: User = Depends(require_user),
) -> EnrichResponse:
    """Upload a PDF invoice. The endpoint extracts the invoice data
    (structured / invoice2data / LLM fallback chain), generates a
    standards-conformant CII-XML, and embeds it into the **original PDF**.

    On embedding failure (e.g., source PDF is malformed), the pipeline
    automatically falls back to a freshly rendered visual PDF and reports
    the reason in `warnings`. Set `force_rerender=true` to skip the original
    pass-through (e.g., when strict PDF/A-3 conformance is required).
    """
    job_id = uuid.uuid4().hex[:12]
    tenant_id = str(user.tenant_id)

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Anreichern braucht ein PDF, nicht {file.content_type}.",
        )

    content = await file.read()
    logger.info("Enrich job %s: %s (force_rerender=%s)", job_id, file.filename, force_rerender)

    invoice, method, result, errors, warnings = await _run_enrich(
        content,
        ".pdf",
        profile=profile,
        force_rerender=force_rerender,
        tenant_id=tenant_id,
        job_id=job_id,
    )

    if result is None:
        return EnrichResponse(job_id=job_id, success=False, errors=errors, warnings=warnings)

    return EnrichResponse(
        job_id=job_id,
        success=result.success,
        invoice=invoice,
        extraction_method=method,
        pdf_source=result.pdf_source,
        pdf_base64=b64encode(result.pdf_bytes).decode() if result.pdf_bytes else None,
        errors=errors,
        warnings=warnings,
    )


@router.post(
    "/enrich/download",
    summary="Enrich a PDF and stream the result file directly",
)
async def enrich_and_download(
    file: UploadFile,
    profile: ZUGFeRDProfile = Form(ZUGFeRDProfile.EN16931),
    force_rerender: bool = Form(False),
    user: User = Depends(require_user),
) -> Response:
    """Same flow as /enrich but returns the ZUGFeRD PDF directly as a
    file stream. Warnings (e.g., fallback to rerender) are exposed via the
    custom X-InvoiceForge-Warnings header.
    """
    job_id = uuid.uuid4().hex[:12]
    tenant_id = str(user.tenant_id)

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Anreichern braucht ein PDF, nicht {file.content_type}.",
        )

    content = await file.read()
    invoice, _method, result, errors, warnings = await _run_enrich(
        content,
        ".pdf",
        profile=profile,
        force_rerender=force_rerender,
        tenant_id=tenant_id,
        job_id=job_id,
    )

    if result is None or not result.success or not result.pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors, "warnings": warnings},
        )

    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_") if invoice else job_id
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}_zugferd.pdf"',
        "X-InvoiceForge-PDF-Source": result.pdf_source or "",
    }
    if warnings:
        # Header values must be ASCII-safe; join + collapse newlines.
        headers["X-InvoiceForge-Warnings"] = " | ".join(w.replace("\n", " ") for w in warnings)

    return Response(content=result.pdf_bytes, media_type="application/pdf", headers=headers)


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Validate an E-Rechnung file (XML or ZUGFeRD/Factur-X PDF)",
)
async def validate_invoice(file: UploadFile) -> ValidateResponse:
    """Upload a CII/UBL XML or a ZUGFeRD/Factur-X PDF and run the full
    validator chain: XSD + offline Schematron + (optional) KoSIT.

    For PDFs, the embedded CII-XML is extracted first; the validation runs
    against that XML.
    """
    is_xml = file.content_type in ("application/xml", "text/xml")
    is_pdf = file.content_type == "application/pdf" or (
        (file.filename or "").lower().endswith(".pdf")
    )
    if not (is_xml or is_pdf):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Use XML or PDF (ZUGFeRD/Factur-X).",
        )

    content = await file.read()

    if is_pdf:
        try:
            from facturx import get_xml_from_pdf

            _name, xml_bytes = get_xml_from_pdf(content)
        except Exception as e:
            return ValidateResponse(is_valid=False, errors=[f"PDF/XML extract failed: {e}"])
        if not xml_bytes:
            return ValidateResponse(
                is_valid=False, errors=["No embedded e-invoice XML found in PDF."]
            )
    else:
        xml_bytes = content

    from app.core.validation.validator import InvoiceValidator

    validator = InvoiceValidator(kosit_url=settings.kosit_validator_url)
    result = await validator.validate_full(xml_bytes)

    return ValidateResponse(
        is_valid=result.is_valid,
        errors=[f"{e.source}: {e.message}" for e in result.errors],
        warnings=[f"{w.source}: {w.message}" for w in result.warnings],
        kosit_available=result.kosit_valid is not None,
    )


@router.get(
    "/records",
    response_model=InvoiceListResponse,
    summary="List invoice processing records",
)
async def list_records(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
) -> InvoiceListResponse:
    """List persisted invoice records for the current user's tenant (newest first)."""
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            records = await svc.list_records(
                str(user.tenant_id), limit=limit, offset=offset
            )
            return InvoiceListResponse(
                records=[
                    InvoiceRecordResponse(
                        id=str(r.id),
                        invoice_number=r.invoice_number,
                        seller_name=r.seller_name,
                        buyer_name=r.buyer_name,
                        gross_amount=float(r.gross_amount),
                        currency=r.currency,
                        status=r.status,
                        output_format=r.output_format,
                        created_at=r.created_at.isoformat(),
                    )
                    for r in records
                ],
                total=len(records),
            )
    except Exception as e:
        logger.debug("DB not available: %s", e)
        return InvoiceListResponse(records=[], total=0)


@router.get(
    "/records/{record_id}",
    summary="Get a single invoice record",
)
async def get_record(
    record_id: str,
    user: User = Depends(require_user),
) -> dict:
    """Retrieve a single invoice record with its stored data.

    Records are tenant-scoped — a user can only fetch records belonging to
    their own tenant. Cross-tenant requests return 404 (not 403) to avoid
    leaking record existence.
    """
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        record_uuid = uuid.UUID(record_id)
        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.get_record(record_uuid)
            if record is None or record.tenant_id != user.tenant_id:
                raise HTTPException(status_code=404, detail="Record not found")
            invoice_data = await svc.get_invoice_data(record_uuid)
            return {
                "id": str(record.id),
                "invoice_number": record.invoice_number,
                "seller_name": record.seller_name,
                "buyer_name": record.buyer_name,
                "gross_amount": float(record.gross_amount),
                "currency": record.currency,
                "status": record.status,
                "output_format": record.output_format,
                "created_at": record.created_at.isoformat(),
                "invoice_data": invoice_data.model_dump() if invoice_data else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")


@router.get(
    "/formats",
    summary="List supported output formats and profiles",
)
async def list_formats() -> dict:
    """Return the available output formats and ZUGFeRD profiles."""
    return {
        "output_formats": [{"value": f.value, "label": f.name} for f in OutputFormat],
        "zugferd_profiles": [{"value": p.value, "label": p.name} for p in ZUGFeRDProfile],
        "llm_provider": settings.llm_provider.value,
    }
