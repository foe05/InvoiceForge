# InvoiceForge

German E-Rechnung converter – create ZUGFeRD & XRechnung from multiple inputs as a processing tool in a chain.

## Features (planned)

- **Input:** PDF, scanned images, CSV, JSON, XML
- **Extraction:** pdfplumber + Tesseract OCR + LLM-based field mapping
- **Output:** ZUGFeRD PDF/A-3 (all profiles), XRechnung CII, XRechnung UBL
- **Validation:** XSD (inline) + KoSIT Validator (Schematron, Docker sidecar)
- **API:** FastAPI REST with auto-generated OpenAPI docs
- **CLI:** `invoiceforge convert`, `invoiceforge validate`, `invoiceforge serve`
- **Multi-tenant:** Schema-based isolation in PostgreSQL

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| ZUGFeRD XML | drafthorse (CII) |
| PDF/A-3 | factur-x |
| PDF rendering | WeasyPrint + Jinja2 |
| OCR | pdfplumber + Tesseract |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Background jobs | ARQ (Redis) |
| Validation | lxml (XSD) + KoSIT Validator (Schematron) |
| UI | HTMX + Jinja2 |

## Quick Start

```bash
# Clone
git clone https://github.com/foe05/InvoiceForge.git
cd InvoiceForge

# Docker Compose
docker compose up -d

# API docs
open http://localhost:8000/api/docs
```

### Local Development

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev,ocr]"

# Run API server
invoiceforge serve --reload

# Run tests
pytest
```

## Project Structure

```
InvoiceForge/
├── app/
│   ├── api/v1/          # FastAPI endpoints
│   ├── cli/             # CLI commands
│   ├── core/
│   │   ├── extraction/  # PDF/image data extraction
│   │   ├── generation/  # CII/UBL XML + ZUGFeRD PDF generation
│   │   ├── validation/  # XSD + KoSIT Schematron validation
│   │   └── storage/     # File storage (local, WebDAV)
│   ├── db/              # SQLAlchemy models + Alembic migrations
│   ├── models/          # Pydantic data models (EN 16931)
│   ├── config.py        # Settings (pydantic-settings)
│   └── main.py          # FastAPI app entry point
├── tests/               # pytest test suite
├── ui/                  # HTMX templates (planned)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Standards

- **EN 16931** – European e-invoicing norm (semantic data model)
- **XRechnung 3.0.2** – German CIUS (B2G mandatory, B2B compatible)
- **ZUGFeRD 2.4 / Factur-X 1.08** – Hybrid PDF/A-3 + CII-XML
- **PEPPOL BIS Billing 3.0** – Pan-European invoicing network

## License

GPL-3.0-or-later – see [LICENSE](LICENSE).
