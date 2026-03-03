"""OCR extraction for scanned PDF invoices using Tesseract.

Falls back gracefully if Tesseract is not installed (returns empty text).
For digital PDFs, use PDFExtractor (pdfplumber) instead – it's faster and
more accurate.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract text from scanned PDFs/images via Tesseract OCR."""

    def __init__(self, lang: str = "deu+eng") -> None:
        self.lang = lang

    def extract_from_image(self, image_path: Path) -> str:
        """Run Tesseract OCR on a single image file."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning("pytesseract/Pillow not installed. Install with: pip install invoiceforge[ocr]")
            return ""

        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        try:
            img = Image.open(image_path)
            return pytesseract.image_to_string(img, lang=self.lang)
        except Exception as e:
            logger.error("OCR failed for %s: %s", image_path, e)
            return ""

    def extract_from_pdf(self, pdf_path: Path) -> str:
        """Convert PDF pages to images and OCR them.

        Uses pdf2image (poppler) for page rendering.
        Falls back to pdfplumber text extraction if pdf2image is unavailable.
        """
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning("pytesseract/Pillow not installed.")
            return ""

        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

        # Try pdfplumber first for digital PDFs (faster + more accurate)
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:
                        text_parts.append(text)

            if text_parts:
                return "\n\n".join(text_parts)
        except Exception:
            pass

        # Fallback: render PDF pages to images and OCR
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path, dpi=300)
            pages = []
            for img in images:
                text = pytesseract.image_to_string(img, lang=self.lang)
                if text.strip():
                    pages.append(text)
            return "\n\n".join(pages)
        except ImportError:
            logger.warning("pdf2image not installed. Cannot OCR PDF pages.")
            return ""
        except Exception as e:
            logger.error("PDF OCR failed: %s", e)
            return ""
