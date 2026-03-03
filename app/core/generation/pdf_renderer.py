"""Render a visual PDF from an Invoice model using WeasyPrint + Jinja2.

This PDF serves as the human-readable part of a ZUGFeRD hybrid invoice.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.models.invoice import Invoice

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ui" / "templates"


class PDFRenderer:
    """Render an Invoice to a visual PDF using an HTML template."""

    def __init__(self, template_dir: Path | None = None) -> None:
        tpl_dir = template_dir or _TEMPLATE_DIR
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            autoescape=True,
        )

    def render_html(self, invoice: Invoice) -> str:
        """Render invoice data to an HTML string."""
        template = self.jinja_env.get_template("invoice.html")
        return template.render(invoice=invoice)

    def render_pdf(self, invoice: Invoice) -> bytes:
        """Render invoice to PDF bytes."""
        html_str = self.render_html(invoice)
        pdf_bytes = BytesIO()
        HTML(string=html_str).write_pdf(pdf_bytes)
        return pdf_bytes.getvalue()

    def render_pdf_to_file(self, invoice: Invoice, output_path: Path) -> Path:
        """Render invoice to a PDF file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_bytes = self.render_pdf(invoice)
        output_path.write_bytes(pdf_bytes)
        return output_path
