"""Invoice API endpoints – convert, validate, extract, and download invoices."""

from __future__ import annotations

import uuid
from base64 import b64encode
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

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
    errors: list[str] = []


class ValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []


# --- Endpoints ---


@router.post(
    "/convert",
    response_model=ConvertResponse,
    summary="Convert invoice data to E-Rechnung",
)
async def convert_invoice(invoice: Invoice) -> ConvertResponse:
    """Convert structured invoice data to ZUGFeRD PDF or XRechnung XML.

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
    summary="Extract invoice data from uploaded ZUGFeRD PDF or XRechnung XML",
)
async def extract_invoice(file: UploadFile) -> ExtractResponse:
    """Upload a ZUGFeRD PDF or XRechnung XML and extract the structured
    invoice data. Returns an Invoice model that can be modified and
    re-submitted to /convert.
    """
    job_id = uuid.uuid4().hex[:12]

    if file.content_type not in ("application/pdf", "application/xml", "text/xml"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported: {file.content_type}. Use PDF or XML.",
        )

    content = await file.read()
    suffix = ".pdf" if "pdf" in (file.content_type or "") else ".xml"

    try:
        with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            invoice = _xml_extractor.extract_from_file(Path(tmp.name))
    except Exception as e:
        return ExtractResponse(job_id=job_id, success=False, errors=[str(e)])

    return ExtractResponse(job_id=job_id, success=True, invoice=invoice)


@router.post(
    "/validate",
    response_model=ValidateResponse,
    summary="Validate an E-Rechnung XML file",
)
async def validate_invoice(file: UploadFile) -> ValidateResponse:
    """Upload a CII-XML for XSD validation."""
    if file.content_type not in ("application/xml", "text/xml"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only XML files can be validated",
        )

    content = await file.read()

    from drafthorse.utils import validate_xml
    from lxml import etree

    try:
        etree.fromstring(content)
    except etree.XMLSyntaxError as e:
        return ValidateResponse(is_valid=False, errors=[f"XML parse error: {e}"])

    # XSD validation via drafthorse utility
    try:
        validate_xml(content, schema="FACTUR-X_EN16931")
        return ValidateResponse(is_valid=True)
    except Exception as e:
        return ValidateResponse(is_valid=False, errors=[str(e)])


@router.get(
    "/formats",
    summary="List supported output formats and profiles",
)
async def list_formats() -> dict:
    """Return the available output formats and ZUGFeRD profiles."""
    return {
        "output_formats": [{"value": f.value, "label": f.name} for f in OutputFormat],
        "zugferd_profiles": [{"value": p.value, "label": p.name} for p in ZUGFeRDProfile],
    }
