"""InvoiceForge Streamlit Web-UI.

Seitenstruktur:
  - Konvertieren: Datei-Upload (lokal) ODER Nextcloud-Pfad → Format wählen → Konvertieren
  - Validieren: Fertige E-Rechnung prüfen, Ergebnis anzeigen
  - Mandanten: CRUD für Mandanten-Stammdaten
  - Jobhistorie: Letzte Konvertierungen mit Status

Start: streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    InvoiceTypeCode,
    OutputFormat,
    PaymentTerms,
    TaxBreakdown,
    ZUGFeRDProfile,
)

st.set_page_config(
    page_title="InvoiceForge",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _confidence_color(score: float) -> str:
    """Return CSS color based on confidence score."""
    if score >= 0.9:
        return "green"
    elif score >= 0.7:
        return "orange"
    return "red"


def _confidence_badge(score: float) -> str:
    """Return a colored badge for confidence score."""
    color = _confidence_color(score)
    pct = int(score * 100)
    return f":{color}[{pct}%]"


# --- Sidebar Navigation ---
st.sidebar.title("InvoiceForge")
st.sidebar.markdown("Deutscher E-Rechnungs-Konverter")
page = st.sidebar.radio(
    "Navigation",
    ["Konvertieren", "Validieren", "Mandanten", "Jobhistorie"],
    index=0,
)


# =====================================================================
# PAGE: KONVERTIEREN
# =====================================================================
if page == "Konvertieren":
    st.title("Rechnung konvertieren")
    st.markdown("Laden Sie eine Rechnung hoch oder geben Sie einen Nextcloud-Pfad an.")

    # Input source
    input_source = st.radio(
        "Eingabequelle",
        ["Datei-Upload", "Nextcloud-Pfad"],
        horizontal=True,
    )

    uploaded_file = None
    nc_path = ""

    if input_source == "Datei-Upload":
        uploaded_file = st.file_uploader(
            "Rechnung hochladen",
            type=["pdf", "xml", "json"],
            help="PDF, XML (XRechnung/ZUGFeRD) oder JSON",
        )
    else:
        nc_path = st.text_input(
            "Nextcloud-Pfad",
            placeholder="/Rechnungen/Eingang/rechnung.pdf",
            help="Pfad zur Datei auf Ihrem Nextcloud-Server",
        )

    # Output settings
    col1, col2 = st.columns(2)

    with col1:
        output_format = st.selectbox(
            "Ausgabeformat",
            options=[
                ("ZUGFeRD PDF", "zugferd_pdf"),
                ("XRechnung (CII-XML)", "xrechnung_cii"),
                ("XRechnung (UBL-XML)", "xrechnung_ubl"),
            ],
            format_func=lambda x: x[0],
        )

    with col2:
        profile = st.selectbox(
            "ZUGFeRD-Profil",
            options=[p.value for p in ZUGFeRDProfile],
            index=3,  # EN 16931
        )

    validate_output = st.checkbox("Ausgabe validieren", value=True)

    # Output path
    output_path = st.text_input(
        "Ausgabepfad (optional)",
        placeholder="Leer = neben Eingabedatei speichern / nextcloud://...",
        help="Lokaler Pfad oder nextcloud:// URI. Wird automatisch aus dem Eingabepfad abgeleitet.",
    )

    if st.button("Konvertieren", type="primary"):
        if not uploaded_file and not nc_path:
            st.error("Bitte laden Sie eine Datei hoch oder geben Sie einen Nextcloud-Pfad an.")
        else:
            with st.spinner("Konvertierung läuft..."):
                try:
                    # Get input data
                    if uploaded_file:
                        file_data = uploaded_file.read()
                        file_name = uploaded_file.name
                        suffix = Path(file_name).suffix
                    else:
                        from app.core.storage.webdav_storage import WebDAVStorage
                        from app.config import settings

                        storage = WebDAVStorage(
                            url=settings.effective_webdav_url,
                            username=settings.effective_webdav_username,
                            password=settings.effective_webdav_password,
                        )
                        import asyncio

                        file_data = asyncio.run(storage.download_file(nc_path))
                        file_name = Path(nc_path).name
                        suffix = Path(nc_path).suffix

                    # Extract invoice data
                    from app.core.extraction.xml_extractor import XMLExtractor

                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(file_data)
                        tmp.flush()
                        tmp_path = Path(tmp.name)

                    extractor = XMLExtractor()
                    invoice = None
                    extraction_method = ""

                    try:
                        invoice = extractor.extract_from_file(tmp_path)
                        extraction_method = "Strukturiert (CII-XML)"
                    except Exception:
                        if suffix.lower() == ".json":
                            invoice = Invoice.model_validate_json(file_data.decode())
                            extraction_method = "JSON"

                    if invoice is None:
                        st.error(
                            "Rechnungsdaten konnten nicht extrahiert werden. "
                            "Versuchen Sie eine strukturierte XML- oder JSON-Datei."
                        )
                    else:
                        st.info(f"Extraktionsmethode: {extraction_method}")

                        # Apply settings
                        invoice.output_format = OutputFormat(output_format[1])
                        invoice.profile = ZUGFeRDProfile(profile)

                        # Show extracted fields for review
                        with st.expander("Extrahierte Felder (bearbeitbar)", expanded=False):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.text_input("Rechnungsnummer", value=invoice.invoice_number, key="inv_nr", disabled=True)
                                st.text_input("Verkäufer", value=invoice.seller.name, key="seller", disabled=True)
                            with c2:
                                st.text_input("Rechnungsdatum", value=str(invoice.invoice_date), key="inv_date", disabled=True)
                                st.text_input("Käufer", value=invoice.buyer.name, key="buyer", disabled=True)
                            st.text_input("Bruttobetrag", value=f"{invoice.totals.gross_amount} {invoice.currency_code.value}", key="total", disabled=True)

                        # Run conversion
                        from app.core.pipeline import ConversionPipeline

                        pipeline = ConversionPipeline(validate=validate_output)
                        result = pipeline.convert(invoice)

                        if result.success:
                            st.success(f"Konvertierung erfolgreich: {invoice.invoice_number}")

                            # Show validation status
                            if result.validation:
                                v = result.validation
                                if v.level.value == "valid":
                                    st.markdown(f":green[✓ {v.summary_de}]")
                                elif v.level.value == "warnings":
                                    st.markdown(f":orange[⚠ {v.summary_de}]")
                                    for w in v.warnings:
                                        st.warning(f"[{w.source}] {w.message}")
                                else:
                                    st.markdown(f":red[✗ {v.summary_de}]")
                                    for e in v.errors:
                                        st.error(f"[{e.source}] {e.message}")

                            # Download button
                            if result.pdf_bytes:
                                safe_name = invoice.invoice_number.replace("/", "_")
                                st.download_button(
                                    "PDF herunterladen",
                                    data=result.pdf_bytes,
                                    file_name=f"{safe_name}.pdf",
                                    mime="application/pdf",
                                )
                            elif result.xml_bytes:
                                safe_name = invoice.invoice_number.replace("/", "_")
                                st.download_button(
                                    "XML herunterladen",
                                    data=result.xml_bytes,
                                    file_name=f"{safe_name}.xml",
                                    mime="application/xml",
                                )

                            # Upload to Nextcloud if output path specified
                            if output_path and output_path.startswith("nextcloud://"):
                                nc_out = output_path[len("nextcloud://"):]
                                out_data = result.pdf_bytes or result.xml_bytes
                                try:
                                    import asyncio
                                    from app.core.storage.webdav_storage import WebDAVStorage
                                    from app.config import settings

                                    storage = WebDAVStorage(
                                        url=settings.effective_webdav_url,
                                        username=settings.effective_webdav_username,
                                        password=settings.effective_webdav_password,
                                    )
                                    asyncio.run(storage.upload_file(out_data, nc_out))
                                    st.success(f"Hochgeladen nach Nextcloud: {nc_out}")
                                except Exception as e:
                                    st.error(f"Nextcloud-Upload fehlgeschlagen: {e}")
                        else:
                            st.error("Konvertierung fehlgeschlagen:")
                            for err in result.errors:
                                st.error(err)

                except Exception as e:
                    st.error(f"Fehler: {e}")


# =====================================================================
# PAGE: VALIDIEREN
# =====================================================================
elif page == "Validieren":
    st.title("E-Rechnung validieren")
    st.markdown("Laden Sie eine fertige E-Rechnung (XML) zur Prüfung hoch.")

    uploaded_xml = st.file_uploader(
        "E-Rechnung hochladen",
        type=["xml"],
        help="CII-XML (ZUGFeRD/XRechnung) oder UBL-XML",
    )

    if uploaded_xml and st.button("Validieren", type="primary"):
        with st.spinner("Validierung läuft..."):
            try:
                xml_bytes = uploaded_xml.read()

                from app.core.validation.validator import InvoiceValidator

                validator = InvoiceValidator()
                result = validator.validate(xml_bytes)

                # Status display (green/yellow/red)
                if result.level.value == "valid":
                    st.markdown(
                        f"### :green[✓ GÜLTIG]\n{result.summary_de}"
                    )
                elif result.level.value == "warnings":
                    st.markdown(
                        f"### :orange[⚠ GÜLTIG MIT WARNUNGEN]\n{result.summary_de}"
                    )
                else:
                    st.markdown(
                        f"### :red[✗ UNGÜLTIG]\n{result.summary_de}"
                    )

                # Details
                if result.schemas_used:
                    st.info(f"Verwendete Schemas: {', '.join(result.schemas_used)}")

                # XSD status
                if result.xsd_valid is not None:
                    if result.xsd_valid:
                        st.markdown(":green[✓] XSD-Validierung bestanden")
                    else:
                        st.markdown(":red[✗] XSD-Validierung fehlgeschlagen")

                # Schematron status
                if result.schematron_valid is not None:
                    if result.schematron_valid:
                        st.markdown(":green[✓] Schematron-Validierung bestanden")
                    else:
                        st.markdown(":red[✗] Schematron-Validierung fehlgeschlagen")

                # Errors
                if result.errors:
                    st.subheader("Fehler")
                    for err in result.errors:
                        st.error(f"**[{err.source}]** {err.message}")

                # Warnings
                if result.warnings:
                    st.subheader("Warnungen")
                    for warn in result.warnings:
                        st.warning(f"**[{warn.source}]** {warn.message}")

            except Exception as e:
                st.error(f"Validierungsfehler: {e}")


# =====================================================================
# PAGE: MANDANTEN
# =====================================================================
elif page == "Mandanten":
    st.title("Mandanten verwalten")

    tab_list, tab_create = st.tabs(["Übersicht", "Neuen Mandanten anlegen"])

    with tab_list:
        st.subheader("Mandantenübersicht")
        try:
            import asyncio
            from app.db.session import async_session_factory
            from app.db.service import TenantService

            async def _load_tenants():
                async with async_session_factory() as session:
                    svc = TenantService(session)
                    return await svc.list_tenants(active_only=False)

            tenants = asyncio.run(_load_tenants())

            if not tenants:
                st.info("Keine Mandanten vorhanden. Legen Sie einen neuen Mandanten an.")
            else:
                for t in tenants:
                    config = TenantService.get_tenant_config(t)
                    company = config.get("company", {})

                    with st.expander(
                        f"{'✓' if t.is_active else '✗'} {t.name} ({t.slug})"
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**ID:** `{t.id}`")
                            st.markdown(f"**Slug:** `{t.slug}`")
                            st.markdown(f"**Aktiv:** {'Ja' if t.is_active else 'Nein'}")
                        with c2:
                            if company:
                                st.markdown(f"**Firma:** {company.get('name', '-')}")
                                st.markdown(f"**USt-IdNr.:** {company.get('vat_id', '-')}")
                                st.markdown(f"**IBAN:** {company.get('iban', '-')}")

                        defaults = config.get("defaults", {})
                        if defaults:
                            st.markdown(
                                f"**Standard-Format:** {defaults.get('output_format', '-')} | "
                                f"**Profil:** {defaults.get('zugferd_profile', '-')}"
                            )

                        nc = config.get("nextcloud", {})
                        if nc:
                            st.markdown(f"**Nextcloud:** {nc.get('url', '-')}")

        except Exception as e:
            st.warning(f"Datenbank nicht verfügbar: {e}")
            st.info("Starten Sie die Datenbank oder verwenden Sie die CLI: `invoiceforge tenant list`")

    with tab_create:
        st.subheader("Neuen Mandanten anlegen")

        with st.form("create_tenant"):
            name = st.text_input("Firmenname *", placeholder="Muster GmbH")
            slug = st.text_input(
                "Slug *",
                placeholder="muster-gmbh",
                help="URL-sicherer Bezeichner (nur Kleinbuchstaben, Zahlen, Bindestriche)",
            )

            st.markdown("**Firmenstammdaten**")
            c1, c2 = st.columns(2)
            with c1:
                street = st.text_input("Straße", placeholder="Musterstr. 1")
                city = st.text_input("Stadt", placeholder="Berlin")
                vat_id = st.text_input("USt-IdNr.", placeholder="DE123456789")
                iban = st.text_input("IBAN", placeholder="DE89370400440532013000")
            with c2:
                postal_code = st.text_input("PLZ", placeholder="10115")
                country = st.text_input("Land", value="DE")
                tax_number = st.text_input("Steuernummer", placeholder="30/123/45678")
                email = st.text_input("E-Mail", placeholder="rechnung@firma.de")

            st.markdown("**Standard-Einstellungen**")
            c3, c4 = st.columns(2)
            with c3:
                def_format = st.selectbox(
                    "Standard-Format",
                    ["zugferd_pdf", "xrechnung_cii", "xrechnung_ubl"],
                )
            with c4:
                def_profile = st.selectbox(
                    "Standard-Profil",
                    [p.value for p in ZUGFeRDProfile],
                    index=3,
                )

            st.markdown("**Nextcloud (optional)**")
            nc_url = st.text_input("Nextcloud URL", placeholder="https://cloud.example.com/remote.php/dav/files/user/")
            nc_user = st.text_input("Nextcloud Benutzer")
            nc_pass = st.text_input("Nextcloud Passwort", type="password")

            submitted = st.form_submit_button("Mandant anlegen", type="primary")

        if submitted:
            if not name or not slug:
                st.error("Name und Slug sind Pflichtfelder.")
            else:
                config = {
                    "company": {
                        k: v
                        for k, v in {
                            "name": name,
                            "street": street,
                            "city": city,
                            "postal_code": postal_code,
                            "country_code": country,
                            "vat_id": vat_id,
                            "tax_number": tax_number,
                            "iban": iban,
                            "email": email,
                        }.items()
                        if v
                    },
                    "defaults": {
                        "output_format": def_format,
                        "zugferd_profile": def_profile,
                    },
                }

                if nc_url:
                    config["nextcloud"] = {
                        k: v
                        for k, v in {
                            "url": nc_url,
                            "username": nc_user,
                            "password": nc_pass,
                        }.items()
                        if v
                    }

                try:
                    import asyncio
                    from app.db.session import async_session_factory
                    from app.db.service import TenantService

                    async def _create():
                        async with async_session_factory() as session:
                            svc = TenantService(session)
                            tenant, api_key = await svc.create_tenant(
                                name=name, slug=slug, config=config
                            )
                            await session.commit()
                            return tenant, api_key

                    tenant, api_key = asyncio.run(_create())
                    st.success(f"Mandant '{name}' wurde erstellt!")
                    st.code(f"API-Key: {api_key}", language=None)
                    st.warning("API-Key sicher aufbewahren – wird nur einmal angezeigt!")
                except Exception as e:
                    st.error(f"Fehler: {e}")


# =====================================================================
# PAGE: JOBHISTORIE
# =====================================================================
elif page == "Jobhistorie":
    st.title("Konvertierungshistorie")

    try:
        import asyncio
        from app.db.session import async_session_factory
        from app.db.service import InvoiceService

        async def _load_records():
            async with async_session_factory() as session:
                svc = InvoiceService(session)
                return await svc.list_records("default", limit=100)

        records = asyncio.run(_load_records())

        if not records:
            st.info("Keine Konvertierungen vorhanden.")
        else:
            # Summary table
            data = []
            for r in records:
                status_icon = {
                    "completed": "✓",
                    "failed": "✗",
                    "pending": "⏳",
                    "extracting": "🔄",
                    "generating": "🔄",
                    "validating": "🔄",
                }.get(r.status, "?")

                valid_icon = ""
                if r.is_valid is True:
                    valid_icon = "✓"
                elif r.is_valid is False:
                    valid_icon = "✗"

                data.append({
                    "Status": f"{status_icon} {r.status}",
                    "Rechnungsnummer": r.invoice_number,
                    "Verkäufer": r.seller_name,
                    "Käufer": r.buyer_name,
                    "Betrag": f"{r.gross_amount:.2f} {r.currency}",
                    "Format": r.output_format,
                    "Gültig": valid_icon,
                    "Erstellt": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
                })

            st.dataframe(data, use_container_width=True)

    except Exception as e:
        st.warning(f"Datenbank nicht verfügbar: {e}")
        st.info("Starten Sie die Datenbank für die Jobhistorie.")
