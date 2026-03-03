"""Invoice API endpoints – convert, validate, extract, and download invoices."""

from __future__ import annotations

import logging
import uuid
from base64 import b64encode
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import LLMProvider, settings
from app.core.extraction.xml_extractor import XMLExtractor
from app.core.pipeline import ConversionPipeline
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

logger = logging.getLogger(__name__)

router = APIRouter()

_pipeline = ConversionPipeline()
_xml_extractor = XMLExtractor()


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
    invoice: Invoice, job_id: str, success: bool, errors: list[str]
) -> None:
    """Attempt to persist a conversion record to the database."""
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.create_record(invoice, "default")
            await svc.update_status(
                record.id,
                status="completed" if success else "failed",
                error_message="; ".join(errors) if errors else None,
            )
            await session.commit()
    except Exception as e:
        logger.debug("DB persistence skipped: %s", e)


async def _try_persist_extraction(
    invoice: Invoice | None, job_id: str, method: str, success: bool, errors: list[str]
) -> None:
    """Attempt to persist an extraction record to the database."""
    if not invoice or not success:
        return
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.create_record(invoice, "default")
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
async def convert_invoice(invoice: Invoice) -> ConvertResponse:
    """Convert structured invoice data to ZUGFeRD PDF, XRechnung CII, or XRechnung UBL.

    Accepts a complete Invoice object (EN 16931) and returns the
    generated output as base64-encoded data.
    """
    job_id = uuid.uuid4().hex[:12]
    logger.info("Convert job %s: %s -> %s", job_id, invoice.invoice_number, invoice.output_format.value)

    result = _pipeline.convert(invoice)

    # Persist to DB (non-blocking, best-effort)
    await _try_persist_conversion(invoice, job_id, result.success, result.errors)

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
async def extract_invoice(file: UploadFile) -> ExtractResponse:
    """Upload a ZUGFeRD PDF, XRechnung XML, or unstructured PDF and extract
    the invoice data. Falls back to LLM-based extraction for unstructured PDFs
    when configured.
    """
    job_id = uuid.uuid4().hex[:12]

    allowed_types = ("application/pdf", "application/xml", "text/xml")
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported: {file.content_type}. Use PDF or XML.",
        )

    content = await file.read()
    suffix = ".pdf" if "pdf" in (file.content_type or "") else ".xml"
    logger.info("Extract job %s: %s (%s)", job_id, file.filename, suffix)

    # Try structured extraction first
    try:
        with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            invoice = _xml_extractor.extract_from_file(Path(tmp.name))
        await _try_persist_extraction(invoice, job_id, "structured", True, [])
        return ExtractResponse(
            job_id=job_id, success=True, invoice=invoice, extraction_method="structured"
        )
    except Exception:
        pass

    # Fallback 1: invoice2data template matching for PDFs
    if suffix == ".pdf":
        try:
            from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

            with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(content)
                tmp.flush()
                i2d = Invoice2DataExtractor()
                invoice = i2d.extract(Path(tmp.name))
            await _try_persist_extraction(invoice, job_id, "invoice2data", True, [])
            return ExtractResponse(
                job_id=job_id, success=True, invoice=invoice, extraction_method="invoice2data"
            )
        except ImportError:
            pass  # invoice2data not installed
        except Exception:
            pass  # No matching template

    # Fallback 2: LLM extraction for PDFs
    if suffix == ".pdf" and settings.llm_provider != LLMProvider.NONE:
        try:
            from app.core.extraction.llm_extractor import LLMExtractor
            from app.core.extraction.pdf_extractor import PDFExtractor

            with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(content)
                tmp.flush()
                pdf_ext = PDFExtractor(Path(tmp.name))
                text = pdf_ext.extract_text()
                tables = pdf_ext.extract_tables()

            llm_ext = LLMExtractor()
            invoice = await llm_ext.extract(text, tables)
            await _try_persist_extraction(invoice, job_id, "llm", True, [])
            return ExtractResponse(
                job_id=job_id, success=True, invoice=invoice, extraction_method="llm"
            )
        except Exception as e:
            return ExtractResponse(
                job_id=job_id, success=False, errors=[f"LLM extraction failed: {e}"]
            )

    return ExtractResponse(
        job_id=job_id,
        success=False,
        errors=["Could not extract structured data. Configure LLM_PROVIDER for unstructured PDFs."],
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Validate an E-Rechnung XML file",
)
async def validate_invoice(file: UploadFile) -> ValidateResponse:
    """Upload a CII or UBL XML for XSD validation and optional KoSIT Schematron check."""
    if file.content_type not in ("application/xml", "text/xml"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only XML files can be validated",
        )

    content = await file.read()

    from lxml import etree

    try:
        etree.fromstring(content)
    except etree.XMLSyntaxError as e:
        return ValidateResponse(is_valid=False, errors=[f"XML parse error: {e}"])

    errors: list[str] = []
    warnings: list[str] = []

    # XSD validation via drafthorse (CII only – UBL passes through)
    try:
        from drafthorse.utils import validate_xml
        validate_xml(content, schema="FACTUR-X_EN16931")
    except Exception as e:
        errors.append(f"XSD: {e}")

    # KoSIT Schematron validation (if sidecar is available)
    kosit_available = False
    from app.core.validation.kosit_client import KoSITClient
    client = KoSITClient()
    if await client.is_available():
        kosit_available = True
        result = await client.validate(content)
        if not result.is_valid:
            errors.extend(result.errors)
        warnings.extend(result.warnings)

    return ValidateResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        kosit_available=kosit_available,
    )


@router.get(
    "/records",
    response_model=InvoiceListResponse,
    summary="List invoice processing records",
)
async def list_records(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InvoiceListResponse:
    """List persisted invoice records (newest first)."""
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            records = await svc.list_records("default", limit=limit, offset=offset)
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
async def get_record(record_id: str) -> dict:
    """Retrieve a single invoice record with its stored data."""
    try:
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        record_uuid = uuid.UUID(record_id)
        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.get_record(record_uuid)
            if record is None:
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
