"""Command-line interface for InvoiceForge using Typer.

Usage:
    invoiceforge convert --input rechnung.pdf --format zugferd --output out/
    invoiceforge convert --input nextcloud://Rechnungen/Eingang/rechnung.pdf --format xrechnung
    invoiceforge validate --file rechnung.xml
    invoiceforge extract --input rechnung.pdf --llm
    invoiceforge tenant create --name "Mein Unternehmen" --config tenant.json
    invoiceforge tenant list
    invoiceforge serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from app.models.invoice import OutputFormat, ZUGFeRDProfile

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="invoiceforge",
    help="InvoiceForge – Deutscher E-Rechnungs-Konverter (ZUGFeRD & XRechnung)",
    no_args_is_help=True,
)

tenant_app = typer.Typer(help="Mandanten verwalten (CRUD)")
app.add_typer(tenant_app, name="tenant")

# --- nextcloud:// URI support ---

NEXTCLOUD_SCHEME = "nextcloud://"


def _is_nextcloud_path(path: str) -> bool:
    """Prüfe ob der Pfad ein nextcloud:// URI ist."""
    return path.startswith(NEXTCLOUD_SCHEME)


def _parse_nextcloud_path(uri: str) -> str:
    """Extrahiere den Pfad aus einem nextcloud:// URI."""
    return uri[len(NEXTCLOUD_SCHEME):]


def _resolve_nextcloud_input(nc_path: str, tenant_slug: str | None = None) -> bytes:
    """Lade eine Datei von Nextcloud herunter."""
    from app.config import settings
    from app.core.storage.webdav_storage import WebDAVStorage

    # Build WebDAV storage (optionally tenant-scoped)
    url = settings.effective_webdav_url
    username = settings.effective_webdav_username
    password = settings.effective_webdav_password

    if tenant_slug:
        try:
            config = _load_tenant_config_sync(tenant_slug)
            nc_config = config.get("nextcloud", {})
            url = nc_config.get("url", url)
            username = nc_config.get("username", username)
            password = nc_config.get("password", password)
        except Exception:
            pass

    storage = WebDAVStorage(url=url, username=username, password=password)
    return asyncio.run(storage.download_file(nc_path))


def _upload_nextcloud_output(
    data: bytes, nc_path: str, tenant_slug: str | None = None
) -> None:
    """Lade eine Datei auf Nextcloud hoch."""
    from app.config import settings
    from app.core.storage.webdav_storage import WebDAVStorage

    url = settings.effective_webdav_url
    username = settings.effective_webdav_username
    password = settings.effective_webdav_password

    if tenant_slug:
        try:
            config = _load_tenant_config_sync(tenant_slug)
            nc_config = config.get("nextcloud", {})
            url = nc_config.get("url", url)
            username = nc_config.get("username", username)
            password = nc_config.get("password", password)
        except Exception:
            pass

    content_type = "application/pdf" if nc_path.endswith(".pdf") else "application/xml"
    storage = WebDAVStorage(url=url, username=username, password=password)
    asyncio.run(storage.upload_file(data, nc_path, content_type=content_type))


def _load_tenant_config_sync(slug: str) -> dict:
    """Lade die Mandanten-Konfiguration (synchron, für CLI)."""
    from app.db.service import TenantService

    try:
        from app.db.session import async_session_factory

        async def _load() -> dict:
            async with async_session_factory() as session:
                svc = TenantService(session)
                tenant = await svc.get_tenant_by_slug(slug)
                if tenant is None:
                    return {}
                return TenantService.get_tenant_config(tenant)

        return asyncio.run(_load())
    except Exception:
        return {}


# --- Commands ---


@app.command()
def convert(
    input: Annotated[str, typer.Option("--input", "-i", help="Eingabedatei (PDF/XML/JSON oder nextcloud://...)")],
    format: Annotated[str, typer.Option("--format", "-f", help="Ausgabeformat: zugferd, xrechnung_cii, xrechnung_ubl")] = "zugferd",
    zugferd_profile: Annotated[str, typer.Option("--zugferd-profile", help="ZUGFeRD-Profil")] = "EN 16931",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Ausgabepfad (Datei oder Verzeichnis, auch nextcloud://...)")] = None,
    tenant: Annotated[Optional[str], typer.Option("--tenant", "-t", help="Mandanten-Slug")] = None,
    validate: Annotated[bool, typer.Option("--validate/--no-validate", help="Validierung durchführen")] = True,
) -> None:
    """Rechnung konvertieren (PDF/XML/JSON → ZUGFeRD/XRechnung)."""
    from app.core.extraction.xml_extractor import XMLExtractor
    from app.core.pipeline import ConversionPipeline
    from app.core.validation.validator import InvoiceValidator
    from app.models.invoice import Invoice

    # Format mapping
    format_map = {
        "zugferd": "zugferd_pdf",
        "zugferd_pdf": "zugferd_pdf",
        "xrechnung": "xrechnung_cii",
        "xrechnung_cii": "xrechnung_cii",
        "xrechnung_ubl": "xrechnung_ubl",
    }
    output_format_str = format_map.get(format.lower(), format.lower())

    # Resolve input
    is_nc_input = _is_nextcloud_path(input)
    if is_nc_input:
        nc_path = _parse_nextcloud_path(input)
        typer.echo(f"Lade von Nextcloud: {nc_path}")
        try:
            file_data = _resolve_nextcloud_input(nc_path, tenant)
        except Exception as e:
            typer.echo(f"Fehler: Nextcloud-Download fehlgeschlagen: {e}", err=True)
            raise typer.Exit(code=1)

        # Write to temp file for processing
        import tempfile
        suffix = Path(nc_path).suffix
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(file_data)
        tmp.flush()
        input_path = Path(tmp.name)
    else:
        input_path = Path(input)
        if not input_path.exists():
            typer.echo(f"Fehler: Datei nicht gefunden: {input_path}", err=True)
            raise typer.Exit(code=1)

    # Load invoice
    suffix = input_path.suffix.lower()
    invoice: Invoice | None = None

    if suffix == ".json":
        invoice = Invoice.model_validate_json(input_path.read_text())
    elif suffix in (".xml", ".pdf"):
        extractor = XMLExtractor()
        try:
            invoice = extractor.extract_from_file(input_path)
        except Exception as e:
            typer.echo(f"Fehler bei Extraktion aus {input_path}: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo(f"Fehler: Nicht unterstütztes Eingabeformat: {suffix}", err=True)
        raise typer.Exit(code=1)

    # Apply output format and profile
    invoice.output_format = OutputFormat(output_format_str)
    try:
        invoice.profile = ZUGFeRDProfile(zugferd_profile)
    except ValueError:
        # Try matching by name
        profile_map = {p.name.lower(): p for p in ZUGFeRDProfile}
        profile_map["en16931"] = ZUGFeRDProfile.EN16931
        if zugferd_profile.lower().replace(" ", "") in profile_map:
            invoice.profile = profile_map[zugferd_profile.lower().replace(" ", "")]
        else:
            invoice.profile = ZUGFeRDProfile.EN16931

    # Run conversion
    pipeline = ConversionPipeline(validate=validate)
    result = pipeline.convert(invoice)

    if not result.success:
        typer.echo("Konvertierung fehlgeschlagen:", err=True)
        for err in result.errors:
            typer.echo(f"  - {err}", err=True)
        raise typer.Exit(code=1)

    # Show validation result
    if result.validation:
        v = result.validation
        if v.is_valid:
            typer.echo(typer.style(f"✓ {v.summary_de}", fg=typer.colors.GREEN))
        elif v.warnings:
            typer.echo(typer.style(f"⚠ {v.summary_de}", fg=typer.colors.YELLOW))
        else:
            typer.echo(typer.style(f"✗ {v.summary_de}", fg=typer.colors.RED))
            for err in v.errors:
                typer.echo(f"  Fehler: {err.message}", err=True)

    # Determine output location
    if output:
        if _is_nextcloud_path(output):
            # Upload to Nextcloud
            nc_out_path = _parse_nextcloud_path(output)
            if nc_out_path.endswith("/"):
                # Directory path → add filename
                safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
                ext = ".pdf" if output_format_str == "zugferd_pdf" else ".xml"
                nc_out_path = f"{nc_out_path}{safe_name}{ext}"

            out_data = result.pdf_bytes if result.pdf_bytes else result.xml_bytes
            try:
                _upload_nextcloud_output(out_data, nc_out_path, tenant)
                typer.echo(f"Hochgeladen nach Nextcloud: {nc_out_path}")
            except Exception as e:
                typer.echo(f"Fehler: Nextcloud-Upload fehlgeschlagen: {e}", err=True)
                raise typer.Exit(code=1)
        else:
            output_path = Path(output)
            if output_path.is_dir() or output.endswith("/"):
                output_path.mkdir(parents=True, exist_ok=True)
                safe_name = invoice.invoice_number.replace("/", "_").replace(" ", "_")
                ext = ".pdf" if output_format_str == "zugferd_pdf" else ".xml"
                output_path = output_path / f"{safe_name}{ext}"

            out_data = result.pdf_bytes if result.pdf_bytes else result.xml_bytes
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(out_data)
            typer.echo(f"Erzeugt: {output_path}")
    else:
        # Default output path logic
        if is_nc_input:
            # Output next to input on Nextcloud
            from app.core.storage.webdav_storage import WebDAVStorage

            nc_path = _parse_nextcloud_path(input)
            suffix_map = {"zugferd_pdf": "_zugferd.pdf", "xrechnung_cii": "_xrechnung.xml", "xrechnung_ubl": "_xrechnung_ubl.xml"}
            out_suffix = suffix_map.get(output_format_str, "_converted.xml")
            nc_out_path = WebDAVStorage.derive_output_path(nc_path, out_suffix.replace(Path(nc_path).suffix, ""))
            out_data = result.pdf_bytes if result.pdf_bytes else result.xml_bytes
            try:
                _upload_nextcloud_output(out_data, nc_out_path, tenant)
                typer.echo(f"Hochgeladen nach Nextcloud: {nc_out_path}")
            except Exception as e:
                typer.echo(f"Fehler: Nextcloud-Upload fehlgeschlagen: {e}", err=True)
                raise typer.Exit(code=1)
        else:
            ext = ".pdf" if output_format_str == "zugferd_pdf" else ".xml"
            output_path = input_path.with_suffix(ext)
            out_data = result.pdf_bytes if result.pdf_bytes else result.xml_bytes
            output_path.write_bytes(out_data)
            typer.echo(f"Erzeugt: {output_path}")

    typer.echo(f"  Format: {invoice.output_format.value}")
    typer.echo(f"  Profil: {invoice.profile.value}")
    typer.echo(f"  Rechnung: {invoice.invoice_number} ({invoice.invoice_date})")
    typer.echo(f"  Betrag: {invoice.totals.gross_amount} {invoice.currency_code.value}")


@app.command()
def validate_cmd(
    file: Annotated[str, typer.Option("--file", "-f", help="XML-Datei zur Validierung")],
) -> None:
    """E-Rechnung validieren (XSD + Schematron)."""
    from app.core.validation.validator import InvoiceValidator

    file_path = Path(file)
    if not file_path.exists():
        typer.echo(f"Fehler: Datei nicht gefunden: {file_path}", err=True)
        raise typer.Exit(code=1)

    xml_bytes = file_path.read_bytes()
    validator = InvoiceValidator()
    result = validator.validate(xml_bytes)

    # Display result with colors
    if result.level.value == "valid":
        typer.echo(typer.style(f"GÜLTIG: {result.summary_de}", fg=typer.colors.GREEN))
    elif result.level.value == "warnings":
        typer.echo(typer.style(f"GÜLTIG MIT WARNUNGEN: {result.summary_de}", fg=typer.colors.YELLOW))
        for warn in result.warnings:
            typer.echo(f"  ⚠ [{warn.source}] {warn.message}")
    else:
        typer.echo(typer.style(f"UNGÜLTIG: {result.summary_de}", fg=typer.colors.RED))
        for err in result.errors:
            typer.echo(f"  ✗ [{err.source}] {err.message}")
        for warn in result.warnings:
            typer.echo(f"  ⚠ [{warn.source}] {warn.message}")

    typer.echo(f"  Verwendete Schemas: {', '.join(result.schemas_used) or 'keine'}")

    if not result.is_valid:
        raise typer.Exit(code=1)


@app.command()
def extract(
    input: Annotated[str, typer.Option("--input", "-i", help="Eingabedatei (PDF oder XML)")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Ausgabe-JSON-Datei (Standard: stdout)")] = None,
    llm: Annotated[bool, typer.Option("--llm/--no-llm", help="LLM-basierte Extraktion für unstrukturierte PDFs")] = False,
) -> None:
    """Rechnungsdaten aus PDF/XML extrahieren und als JSON ausgeben."""
    from app.core.extraction.xml_extractor import XMLExtractor

    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Fehler: Datei nicht gefunden: {input_path}", err=True)
        raise typer.Exit(code=1)

    invoice = None

    # Try structured extraction first
    extractor = XMLExtractor()
    try:
        invoice = extractor.extract_from_file(input_path)
        typer.echo("Extraktionsmethode: strukturiert (CII-XML)", err=True)
    except Exception as e:
        if not llm and input_path.suffix.lower() != ".pdf":
            typer.echo(f"Fehler: {e}", err=True)
            typer.echo("Hinweis: --llm für unstrukturierte PDF-Extraktion verwenden", err=True)
            raise typer.Exit(code=1)

    # Fallback 1: invoice2data template matching for PDFs
    if invoice is None and input_path.suffix.lower() == ".pdf":
        try:
            from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor

            i2d = Invoice2DataExtractor()
            invoice = i2d.extract(input_path)
            typer.echo("Extraktionsmethode: invoice2data (Vorlagenerkennung)", err=True)
        except ImportError:
            pass
        except Exception:
            pass

    # Fallback 2: LLM extraction
    if invoice is None and llm:
        try:
            from app.core.extraction.llm_extractor import LLMExtractor
            from app.core.extraction.pdf_extractor import PDFExtractor

            pdf_ext = PDFExtractor(input_path)
            text = pdf_ext.extract_text()
            tables = pdf_ext.extract_tables()

            llm_ext = LLMExtractor()
            invoice = asyncio.run(llm_ext.extract(text, tables))
            typer.echo("Extraktionsmethode: LLM-basiert", err=True)
        except Exception as e:
            typer.echo(f"LLM-Extraktion fehlgeschlagen: {e}", err=True)
            raise typer.Exit(code=1)

    if invoice is None:
        typer.echo("Fehler: Rechnungsdaten konnten nicht extrahiert werden", err=True)
        raise typer.Exit(code=1)

    json_str = invoice.model_dump_json(indent=2)

    if output:
        Path(output).write_text(json_str)
        typer.echo(f"Extrahiert nach: {output}")
    else:
        typer.echo(json_str)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind-Adresse")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Port")] = 8000,
    reload: Annotated[bool, typer.Option("--reload/--no-reload", help="Auto-Reload aktivieren")] = False,
) -> None:
    """API-Server starten (FastAPI + Uvicorn)."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def worker() -> None:
    """ARQ Background-Worker starten."""
    import subprocess

    subprocess.run([sys.executable, "-m", "arq", "app.worker.settings.WorkerSettings"])


# --- Tenant commands ---


@tenant_app.command("create")
def tenant_create(
    name: Annotated[str, typer.Option("--name", "-n", help="Mandantenname")],
    config: Annotated[Optional[str], typer.Option("--config", "-c", help="Konfigurationsdatei (JSON)")] = None,
    slug: Annotated[Optional[str], typer.Option("--slug", "-s", help="URL-Slug (wird aus Name generiert wenn nicht angegeben)")] = None,
) -> None:
    """Neuen Mandanten anlegen."""
    import re

    # Generate slug from name if not provided
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    # Load config from file if provided
    tenant_config: dict | None = None
    if config:
        config_path = Path(config)
        if not config_path.exists():
            typer.echo(f"Fehler: Konfigurationsdatei nicht gefunden: {config_path}", err=True)
            raise typer.Exit(code=1)
        tenant_config = json.loads(config_path.read_text())

    async def _create() -> None:
        try:
            from app.db.session import async_session_factory
            from app.db.service import TenantService

            async with async_session_factory() as session:
                svc = TenantService(session)
                tenant, api_key = await svc.create_tenant(
                    name=name,
                    slug=slug,
                    config=tenant_config,
                )
                await session.commit()

                typer.echo(typer.style("Mandant erstellt!", fg=typer.colors.GREEN))
                typer.echo(f"  Name: {tenant.name}")
                typer.echo(f"  Slug: {tenant.slug}")
                typer.echo(f"  ID:   {tenant.id}")
                typer.echo(f"  API-Key: {api_key}")
                typer.echo("")
                typer.echo(
                    typer.style(
                        "WICHTIG: API-Key sicher aufbewahren – wird nur einmal angezeigt!",
                        fg=typer.colors.YELLOW,
                        bold=True,
                    )
                )
        except Exception as e:
            typer.echo(f"Fehler: {e}", err=True)
            raise typer.Exit(code=1)

    asyncio.run(_create())


@tenant_app.command("list")
def tenant_list() -> None:
    """Alle Mandanten auflisten."""

    async def _list() -> None:
        try:
            from app.db.session import async_session_factory
            from app.db.service import TenantService

            async with async_session_factory() as session:
                svc = TenantService(session)
                tenants = await svc.list_tenants()

                if not tenants:
                    typer.echo("Keine Mandanten gefunden.")
                    return

                typer.echo(f"{'Slug':<25} {'Name':<30} {'Aktiv':<8} {'Erstellt'}")
                typer.echo("-" * 80)
                for t in tenants:
                    active_str = "✓" if t.is_active else "✗"
                    created = t.created_at.strftime("%Y-%m-%d") if t.created_at else "-"
                    typer.echo(f"{t.slug:<25} {t.name:<30} {active_str:<8} {created}")

        except Exception as e:
            typer.echo(f"Fehler: Datenbank nicht verfügbar ({e})", err=True)
            raise typer.Exit(code=1)

    asyncio.run(_list())


def cli() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    cli()
