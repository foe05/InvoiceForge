"""HTMX-powered web UI routes for InvoiceForge.

These routes serve Jinja2 templates and handle form submissions
via HTMX partial responses. The UI is a lightweight admin interface
for converting, extracting, and validating invoices.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import LLMProvider, settings
from app.core.extraction.xml_extractor import XMLExtractor
from app.core.pipeline import ConversionPipeline
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

router = APIRouter()

_template_dir = Path(__file__).resolve().parent.parent.parent / "ui" / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

_pipeline = ConversionPipeline()
_xml_extractor = XMLExtractor()

# In-memory file cache for downloads (short-lived)
_download_cache: dict[str, tuple[bytes, str, str]] = {}  # id -> (data, filename, media_type)


def _render(request: Request, template_name: str, **kwargs):
    """Render a Jinja2 template with the standard context."""
    context = {"version": __version__, **kwargs}
    return templates.TemplateResponse(request, template_name, context)


# --- Page routes ---


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return _render(request, "dashboard.html", active_page="dashboard")


@router.get("/ui/convert", response_class=HTMLResponse)
async def convert_page(request: Request):
    return _render(request, "convert.html", active_page="convert")


@router.get("/ui/extract", response_class=HTMLResponse)
async def extract_page(request: Request):
    return _render(
        request, "extract.html",
        active_page="extract",
        llm_available=settings.llm_provider != LLMProvider.NONE,
    )


@router.get("/ui/validate", response_class=HTMLResponse)
async def validate_page(request: Request):
    return _render(request, "validate.html", active_page="validate")


# --- HTMX action routes ---


@router.post("/ui/convert", response_class=HTMLResponse)
async def convert_file(request: Request, file: UploadFile, output_format: str = Form("zugferd_pdf"), profile: str = Form("EN 16931")):
    """Convert uploaded JSON invoice file."""
    content = await file.read()
    try:
        invoice = Invoice.model_validate_json(content.decode("utf-8"))
        invoice.output_format = OutputFormat(output_format)
        invoice.profile = ZUGFeRDProfile(profile)
    except Exception as e:
        return _render(request, "partials/result.html",
                       success=False, errors=[f"Ungueltige JSON-Daten: {e}"])

    result = _pipeline.convert(invoice)
    if not result.success:
        return _render(request, "partials/result.html",
                       success=False, errors=result.errors)

    # Cache file for download
    dl_id = uuid.uuid4().hex[:12]
    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
    if result.pdf_bytes:
        _download_cache[dl_id] = (result.pdf_bytes, f"{safe_name}.pdf", "application/pdf")
    else:
        _download_cache[dl_id] = (result.xml_bytes, f"{safe_name}.xml", "application/xml")

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"Rechnung {invoice.invoice_number} erfolgreich konvertiert ({output_format}).",
                   download_url=f"/ui/download/{dl_id}")


@router.post("/ui/convert/json", response_class=HTMLResponse)
async def convert_json(request: Request, invoice_json: str = Form(...), output_format: str = Form("zugferd_pdf"), profile: str = Form("EN 16931")):
    """Convert JSON text input."""
    try:
        invoice = Invoice.model_validate_json(invoice_json)
        invoice.output_format = OutputFormat(output_format)
        invoice.profile = ZUGFeRDProfile(profile)
    except Exception as e:
        return _render(request, "partials/result.html",
                       success=False, errors=[f"Ungueltige JSON-Daten: {e}"])

    result = _pipeline.convert(invoice)
    if not result.success:
        return _render(request, "partials/result.html",
                       success=False, errors=result.errors)

    dl_id = uuid.uuid4().hex[:12]
    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
    if result.pdf_bytes:
        _download_cache[dl_id] = (result.pdf_bytes, f"{safe_name}.pdf", "application/pdf")
    else:
        _download_cache[dl_id] = (result.xml_bytes, f"{safe_name}.xml", "application/xml")

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"Rechnung {invoice.invoice_number} erfolgreich konvertiert.",
                   download_url=f"/ui/download/{dl_id}")


@router.post("/ui/extract", response_class=HTMLResponse)
async def extract_file(request: Request, file: UploadFile):
    """Extract structured data from ZUGFeRD/XRechnung file."""
    content = await file.read()
    suffix = ".pdf" if "pdf" in (file.content_type or "") else ".xml"

    try:
        with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            invoice = _xml_extractor.extract_from_file(Path(tmp.name))
    except Exception as e:
        return _render(request, "partials/result.html",
                       success=False, errors=[f"Extraktion fehlgeschlagen: {e}"])

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"Rechnung {invoice.invoice_number} erfolgreich extrahiert.",
                   invoice_json=invoice.model_dump_json(indent=2))


@router.post("/ui/extract/llm", response_class=HTMLResponse)
async def extract_llm(request: Request, file: UploadFile):
    """Extract data from unstructured PDF using LLM."""
    from app.core.extraction.llm_extractor import LLMExtractor
    from app.core.extraction.pdf_extractor import PDFExtractor

    content = await file.read()

    try:
        with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            pdf_ext = PDFExtractor(Path(tmp.name))
            text = pdf_ext.extract_text()
            tables = pdf_ext.extract_tables()

        llm_ext = LLMExtractor()
        invoice = await llm_ext.extract(text, tables)
    except Exception as e:
        return _render(request, "partials/result.html",
                       success=False, errors=[f"LLM-Extraktion fehlgeschlagen: {e}"])

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"KI-Extraktion erfolgreich: {invoice.invoice_number}",
                   invoice_json=invoice.model_dump_json(indent=2))


@router.post("/ui/validate", response_class=HTMLResponse)
async def validate_file(request: Request, file: UploadFile, use_kosit: str = Form("")):
    """Validate XML with XSD and optionally KoSIT."""
    content = await file.read()

    from lxml import etree
    try:
        etree.fromstring(content)
    except etree.XMLSyntaxError as e:
        return _render(request, "partials/result.html",
                       success=False, errors=[f"XML-Syntaxfehler: {e}"])

    errors: list[str] = []
    warnings: list[str] = []

    # XSD validation
    try:
        from drafthorse.utils import validate_xml
        validate_xml(content, schema="FACTUR-X_EN16931")
    except Exception as e:
        errors.append(f"XSD: {e}")

    # KoSIT validation
    if use_kosit == "true":
        from app.core.validation.kosit_client import KoSITClient
        client = KoSITClient()
        result = await client.validate(content)
        if not result.is_valid:
            errors.extend(result.errors)
        warnings.extend(result.warnings)

    if errors:
        return _render(request, "partials/result.html",
                       success=False, errors=errors, warnings=warnings)

    return _render(request, "partials/result.html",
                   success=True,
                   message="XML-Validierung bestanden.",
                   warnings=warnings)


@router.get("/ui/download/{dl_id}")
async def download_file(dl_id: str):
    """Serve a cached download file."""
    if dl_id not in _download_cache:
        return Response("Datei nicht gefunden oder abgelaufen.", status_code=404)

    data, filename, media_type = _download_cache.pop(dl_id)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
