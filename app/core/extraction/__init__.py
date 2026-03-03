"""Data extraction from input documents (PDF, image, CSV, XML)."""

from app.core.extraction.pdf_extractor import PDFExtractor
from app.core.extraction.xml_extractor import XMLExtractor

__all__ = ["PDFExtractor", "XMLExtractor"]

# Optional extractors – import lazily to avoid hard dependencies
# from app.core.extraction.invoice2data_extractor import Invoice2DataExtractor
# from app.core.extraction.llm_extractor import LLMExtractor
# from app.core.extraction.ocr_extractor import OCRExtractor
