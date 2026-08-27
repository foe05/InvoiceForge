"""HTMX-powered web UI routes for InvoiceForge.

These routes serve Jinja2 templates and handle form submissions
via HTMX partial responses. The UI is a lightweight admin interface
for converting, extracting, enriching, and validating invoices.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

from app import __version__
from app.auth.dependencies import require_user
from app.config import LLMProvider, settings
from app.core.extraction.chain import ExtractionFailed, run_extraction_chain
from app.core.extraction.xml_extractor import XMLExtractor
from app.core.pipeline import ConversionPipeline, ConversionResult
from app.db.models import User
from app.models.invoice import Invoice, OutputFormat, ZUGFeRDProfile

# Every UI route requires an authenticated session. require_user redirects
# unauthenticated browser visits to /login and 401s API-style requests.
router = APIRouter(dependencies=[Depends(require_user)])

_template_dir = Path(__file__).resolve().parent.parent.parent / "ui" / "templates"
templates = Jinja2Templates(directory=str(_template_dir))

_pipeline = ConversionPipeline()
_xml_extractor = XMLExtractor()

# In-memory file cache for downloads (short-lived)
_download_cache: dict[str, tuple[bytes, str, str]] = {}  # id -> (data, filename, media_type)

# Short-lived cache of uploaded source PDFs awaiting an enrich finalize step.
# Key: random id; value: (pdf_bytes, original_filename, created_at_unix).
_source_cache: dict[str, tuple[bytes, str, float]] = {}
_SOURCE_TTL_SECONDS = 1800  # 30 minutes


def _gc_source_cache() -> None:
    now = time.time()
    expired = [k for k, (_, _, t) in _source_cache.items() if now - t > _SOURCE_TTL_SECONDS]
    for k in expired:
        _source_cache.pop(k, None)


async def _persist_record(
    invoice: Invoice,
    tenant_id: str,
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    """Best-effort tenant-scoped persistence for UI flows.

    UI routes call this after a successful conversion / extraction / enrich
    so the action shows up in the user's history. Failures are logged but
    do not break the response — the user already has their result file.
    """
    try:
        from app.db.service import InvoiceService
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            svc = InvoiceService(session)
            record = await svc.create_record(invoice, tenant_id)
            await svc.update_status(record.id, status=status, error_message=error_message)
            await session.commit()
    except Exception as e:
        logger.warning("UI: konnte Record nicht persistieren: %s", e)


def _render(request: Request, template_name: str, user: User | None = None, **kwargs):
    """Render a Jinja2 template with the standard context."""
    context = {"version": __version__, "user": user, **kwargs}
    return templates.TemplateResponse(request, template_name, context)


# --- Page routes ---


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(require_user)):
    return _render(request, "dashboard.html", user=user, active_page="dashboard")


@router.get("/ui/convert", response_class=HTMLResponse)
async def convert_page(request: Request, user: User = Depends(require_user)):
    return _render(request, "convert.html", user=user, active_page="convert")


@router.get("/ui/extract", response_class=HTMLResponse)
async def extract_page(request: Request, user: User = Depends(require_user)):
    return _render(
        request, "extract.html",
        user=user,
        active_page="extract",
        llm_available=settings.llm_provider != LLMProvider.NONE,
    )


@router.get("/ui/validate", response_class=HTMLResponse)
async def validate_page(request: Request, user: User = Depends(require_user)):
    return _render(request, "validate.html", user=user, active_page="validate")


@router.get("/ui/enrich", response_class=HTMLResponse)
async def enrich_page(request: Request, user: User = Depends(require_user)):
    return _render(
        request,
        "enrich.html",
        user=user,
        active_page="enrich",
        llm_available=settings.llm_provider != LLMProvider.NONE,
    )


@router.get("/ui/records", response_class=HTMLResponse)
async def records_page(request: Request, user: User = Depends(require_user)):
    """Job history — invoices the current tenant has converted/extracted."""
    from app.db.service import InvoiceService
    from app.db.session import async_session_factory

    records: list = []
    db_error: str | None = None
    try:
        async with async_session_factory() as session:
            svc = InvoiceService(session)
            records = await svc.list_records(str(user.tenant_id), limit=200, offset=0)
    except Exception as e:
        db_error = str(e)

    return _render(
        request,
        "records.html",
        user=user,
        active_page="records",
        records=records,
        db_error=db_error,
    )


# --- HTMX action routes ---


@router.post("/ui/convert", response_class=HTMLResponse)
async def convert_file(
    request: Request,
    file: UploadFile,
    output_format: str = Form("zugferd_pdf"),
    profile: str = Form("EN 16931"),
    user: User = Depends(require_user),
):
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
        await _persist_record(
            invoice, str(user.tenant_id),
            status="failed", error_message="; ".join(result.errors),
        )
        return _render(request, "partials/result.html",
                       success=False, errors=result.errors)

    await _persist_record(invoice, str(user.tenant_id), status="completed")

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
async def convert_json(
    request: Request,
    invoice_json: str = Form(...),
    output_format: str = Form("zugferd_pdf"),
    profile: str = Form("EN 16931"),
    user: User = Depends(require_user),
):
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
        await _persist_record(
            invoice, str(user.tenant_id),
            status="failed", error_message="; ".join(result.errors),
        )
        return _render(request, "partials/result.html",
                       success=False, errors=result.errors)

    await _persist_record(invoice, str(user.tenant_id), status="completed")

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
async def extract_file(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_user),
):
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

    await _persist_record(invoice, str(user.tenant_id), status="extracted")

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"Rechnung {invoice.invoice_number} erfolgreich extrahiert.",
                   invoice_json=invoice.model_dump_json(indent=2))


@router.post("/ui/extract/llm", response_class=HTMLResponse)
async def extract_llm(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_user),
):
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

    await _persist_record(invoice, str(user.tenant_id), status="extracted")

    return _render(request, "partials/result.html",
                   success=True,
                   message=f"KI-Extraktion erfolgreich: {invoice.invoice_number}",
                   invoice_json=invoice.model_dump_json(indent=2))


@router.post("/ui/validate", response_class=HTMLResponse)
async def validate_file(request: Request, file: UploadFile, use_kosit: str = Form("")):
    """Validate an e-invoice. Accepts a CII/UBL XML or a ZUGFeRD/Factur-X PDF.

    For PDFs, the embedded CII-XML is extracted first. The full validator
    chain (XSD + offline Schematron + optional KoSIT) is then run on the XML
    and a unified result with errors/warnings/level is rendered.
    """
    content = await file.read()
    is_pdf = (file.content_type or "") == "application/pdf" or (
        file.filename or ""
    ).lower().endswith(".pdf")

    # Step 0: if it's a PDF, pull the embedded CII-XML out
    if is_pdf:
        try:
            from facturx import get_xml_from_pdf

            _name, xml_bytes = get_xml_from_pdf(content)
        except Exception as e:
            return _render(
                request, "partials/result.html",
                success=False,
                errors=[f"Konnte eingebettete XML nicht aus PDF lesen: {e}"],
            )
        if not xml_bytes:
            return _render(
                request, "partials/result.html",
                success=False,
                errors=["Im PDF wurde keine eingebettete E-Rechnungs-XML gefunden."],
            )
    else:
        xml_bytes = content

    # Step 1+: full validator chain
    from app.config import settings as _settings
    from app.core.validation.validator import InvoiceValidator, ValidationLevel

    validator = InvoiceValidator(
        kosit_url=_settings.kosit_validator_url if use_kosit == "true" else None
    )
    result = await validator.validate_full(xml_bytes)

    error_msgs = [f"{e.source}: {e.message}" for e in result.errors]
    warning_msgs = [f"{w.source}: {w.message}" for w in result.warnings]

    summary_prefix = "PDF (eingebettete XML)" if is_pdf else "XML"
    summary = f"{summary_prefix} – {result.summary_de or 'Validierung abgeschlossen.'}"
    summary += f" Schemata: {', '.join(result.schemas_used) or '–'}"

    return _render(
        request, "partials/result.html",
        success=result.level != ValidationLevel.INVALID,
        message=summary,
        errors=error_msgs,
        warnings=warning_msgs,
    )


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


# --- Enrich actions ---


@router.post("/ui/enrich/preview", response_class=HTMLResponse)
async def enrich_preview(
    request: Request,
    file: UploadFile,
    profile: str = Form("EN 16931"),
    auto_finalize: str = Form(""),
    force_rerender: str = Form(""),
    user: User = Depends(require_user),
):
    """Step 1 of the enrich flow: extract data from the uploaded PDF.

    If `auto_finalize=on`, the conversion is run immediately and a download
    link is returned. Otherwise an editable JSON preview is rendered so the
    user can correct the LLM output before generating the ZUGFeRD PDF.
    """
    if file.content_type != "application/pdf":
        return _render(
            request,
            "partials/result.html",
            success=False,
            errors=["Anreichern braucht eine PDF-Datei."],
        )

    content = await file.read()

    try:
        ex = await run_extraction_chain(content, ".pdf")
    except ExtractionFailed as e:
        return _render(
            request,
            "partials/result.html",
            success=False,
            errors=[str(e)],
        )

    invoice = ex.invoice

    # Cache the original PDF bytes for the finalize step
    _gc_source_cache()
    src_id = uuid.uuid4().hex[:12]
    _source_cache[src_id] = (content, file.filename or "rechnung.pdf", time.time())

    if auto_finalize == "on":
        invoice.output_format = OutputFormat.ZUGFERD_PDF
        try:
            invoice.profile = ZUGFeRDProfile(profile)
        except ValueError:
            invoice.profile = ZUGFeRDProfile.EN16931
        force = force_rerender == "on"
        result = _pipeline.convert(
            invoice,
            source_pdf_bytes=None if force else content,
            force_rerender=force,
        )
        _source_cache.pop(src_id, None)
        await _persist_record(
            invoice,
            str(user.tenant_id),
            status="completed" if result.success else "failed",
            error_message="; ".join(result.errors) if result.errors else None,
        )
        return _render_enrich_result(request, invoice, result)

    return _render(
        request,
        "partials/enrich_preview.html",
        success=True,
        invoice=invoice,
        invoice_json=invoice.model_dump_json(indent=2),
        method=ex.method,
        src_id=src_id,
        profile=profile,
        force_rerender=(force_rerender == "on"),
    )


@router.post("/ui/enrich/finalize", response_class=HTMLResponse)
async def enrich_finalize(
    request: Request,
    src_id: str = Form(...),
    invoice_json: str = Form(...),
    profile: str = Form("EN 16931"),
    force_rerender: str = Form(""),
    user: User = Depends(require_user),
):
    """Step 2 of the enrich flow: take the (possibly edited) invoice JSON +
    cached original PDF and run the conversion pipeline.
    """
    cached = _source_cache.pop(src_id, None)
    if cached is None:
        return _render(
            request,
            "partials/result.html",
            success=False,
            errors=["Quell-PDF abgelaufen oder nicht gefunden — bitte neu hochladen."],
        )
    pdf_bytes, _filename, _ts = cached

    try:
        invoice = Invoice.model_validate_json(invoice_json)
    except Exception as e:
        return _render(
            request,
            "partials/result.html",
            success=False,
            errors=[f"Ungültige Rechnungsdaten: {e}"],
        )

    invoice.output_format = OutputFormat.ZUGFERD_PDF
    try:
        invoice.profile = ZUGFeRDProfile(profile)
    except ValueError:
        invoice.profile = ZUGFeRDProfile.EN16931

    force = force_rerender == "on"
    result = _pipeline.convert(
        invoice,
        source_pdf_bytes=None if force else pdf_bytes,
        force_rerender=force,
    )
    await _persist_record(
        invoice,
        str(user.tenant_id),
        status="completed" if result.success else "failed",
        error_message="; ".join(result.errors) if result.errors else None,
    )
    return _render_enrich_result(request, invoice, result)


def _render_enrich_result(
    request: Request, invoice: Invoice, result: ConversionResult
) -> HTMLResponse:
    """Render the final result partial after an enrich conversion ran."""
    if not result.success or not result.pdf_bytes:
        return _render(
            request,
            "partials/result.html",
            success=False,
            errors=list(result.errors),
            warnings=list(result.warnings),
        )

    dl_id = uuid.uuid4().hex[:12]
    safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
    _download_cache[dl_id] = (
        result.pdf_bytes,
        f"{safe_name}_zugferd.pdf",
        "application/pdf",
    )

    msg = (
        f"ZUGFeRD-PDF für {invoice.invoice_number} erzeugt "
        f"(Quelle: {'Original' if result.pdf_source == 'original' else 'Visual-Rerender'})."
    )
    return _render(
        request,
        "partials/result.html",
        success=True,
        message=msg,
        warnings=list(result.warnings),
        download_url=f"/ui/download/{dl_id}",
    )
