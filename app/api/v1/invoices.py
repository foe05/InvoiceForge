"""Invoice API endpoints – convert, validate, extract, and download invoices."""

from __future__ import annotations

import uuid
from base64 import b64encode
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import LLMProvider, settings
from app.core.extraction.xml_extractor import XMLExtractor
from app.core.pipeline import ConversionPipeline
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

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
    result = _pipeline.convert(invoice)

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

    # Try structured extraction first
    try:
        with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            invoice = _xml_extractor.extract_from_file(Path(tmp.name))
        return ExtractResponse(
            job_id=job_id, success=True, invoice=invoice, extraction_method="structured"
        )
    except Exception:
        pass

    # Fallback: LLM extraction for PDFs
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
