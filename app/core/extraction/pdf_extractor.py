"""PDF text and table extraction using pdfplumber."""

from __future__ import annotations

from pathlib import Path

import pdfplumber


class PDFExtractor:
    """Extract text and tables from digital PDF invoices."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def extract_text(self) -> str:
        """Extract all text from the PDF."""
        pages: list[str] = []
        with pdfplumber.open(self.file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)

    def extract_tables(self) -> list[list[list[str | None]]]:
        """Extract all tables from the PDF.

        Returns a list of tables, where each table is a list of rows,
        and each row is a list of cell values.
        """
        all_tables: list[list[list[str | None]]] = []
        with pdfplumber.open(self.file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)
        return all_tables

    def extract_all(self) -> dict:
        """Extract text and tables in one pass."""
        return {
            "text": self.extract_text(),
            "tables": self.extract_tables(),
        }
