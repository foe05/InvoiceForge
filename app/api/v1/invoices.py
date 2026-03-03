"""Invoice API endpoints – convert, validate, and manage invoices."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

router = APIRouter()


# --- Request / Response schemas ---


class ConvertRequest(Invoice):
    """Request body for invoice conversion (inherits full Invoice model)."""


class ConvertResponse(Invoice):
    """Successful conversion response with job metadata."""

    job_id: str
    status: str = "completed"
    output_file: str | None = None
    validation_passed: bool | None = None


class ValidationResult(Invoice):
    """Validation result."""

    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []


# --- Endpoints ---


@router.post(
    "/convert",
    response_model=ConvertResponse,
    status_code=status.HTTP_200_OK,
    summary="Convert invoice data to E-Rechnung",
)
async def convert_invoice(request: ConvertRequest) -> ConvertResponse:
    """Convert structured invoice data to ZUGFeRD PDF or XRechnung XML.

    Accepts a complete invoice object (EN 16931 data model) and generates
    the specified output format.
    """
    # TODO: Implement conversion pipeline
    # 1. Validate input data
    # 2. Generate CII/UBL XML via drafthorse
    # 3. If ZUGFeRD: embed XML in PDF/A-3 via factur-x
    # 4. Validate output via KoSIT
    # 5. Store result and return

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Conversion pipeline not yet implemented",
    )


@router.post(
    "/extract",
    response_model=ConvertResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract invoice data from uploaded file",
)
async def extract_invoice(
    file: UploadFile,
    output_format: OutputFormat = OutputFormat.ZUGFERD_PDF,
    profile: ZUGFeRDProfile = ZUGFeRDProfile.EN16931,
) -> ConvertResponse:
    """Upload a PDF/image/CSV and extract invoice data.

    Uses OCR + LLM-based extraction to parse the document, then optionally
    converts to the target E-Rechnung format.
    """
    if file.content_type not in (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/csv",
        "application/xml",
        "text/xml",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}",
        )

    # TODO: Implement extraction pipeline
    # 1. Save uploaded file
    # 2. Extract text (pdfplumber / Tesseract)
    # 3. Map fields via LLM or invoice2data
    # 4. Build Invoice model
    # 5. Convert to target format

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Extraction pipeline not yet implemented",
    )


@router.post(
    "/validate",
    status_code=status.HTTP_200_OK,
    summary="Validate an E-Rechnung XML file",
)
async def validate_invoice(file: UploadFile) -> dict:
    """Upload an XRechnung/ZUGFeRD XML for validation against XSD + Schematron rules."""
    if file.content_type not in ("application/xml", "text/xml"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only XML files can be validated",
        )

    # TODO: Implement validation
    # 1. XSD validation (inline, lxml)
    # 2. KoSIT Validator call (Docker sidecar)

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Validation endpoint not yet implemented",
    )


@router.get(
    "/formats",
    summary="List supported output formats and profiles",
)
async def list_formats() -> dict:
    """Return the available output formats and ZUGFeRD profiles."""
    return {
        "output_formats": [f.value for f in OutputFormat],
        "zugferd_profiles": [p.value for p in ZUGFeRDProfile],
    }
