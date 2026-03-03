# InvoiceForge

German E-Rechnung converter – create ZUGFeRD & XRechnung from multiple inputs as a processing tool in a chain.

## Features

### Input & Extraction

- **PDF** – digital text extraction (pdfplumber) and scanned-image OCR (Tesseract)
- **XML** – structured parsing of ZUGFeRD/Factur-X CII, XRechnung CII & UBL
- **JSON** – direct EN 16931 invoice data
- **CSV** – tabular import (planned)
- **Multi-method extraction pipeline** with automatic fallback:
  structured XML → invoice2data template matching → LLM-based extraction (Claude / Ollama) → OCR

### Output Formats

- **ZUGFeRD 2.4 / Factur-X 1.08** – hybrid PDF/A-3 with embedded CII-XML, all profiles (Minimum, Basic WL, Basic, EN 16931, Extended, XRechnung)
- **XRechnung 3.0.2 CII** – Cross Industry Invoice XML
- **XRechnung 3.0.2 UBL** – Universal Business Language XML
- **Visual PDF** – rendered invoice via WeasyPrint + Jinja2 templates

### Validation

- **XSD schema validation** – offline, via drafthorse/lxml
- **Schematron rules** – CEN EN 16931 + XRechnung business rules
- **KoSIT Validator** – Docker sidecar integration for official German government validation
- Detailed reports with error/warning categorisation, rule IDs and line locations

### API (FastAPI)

- `POST /api/v1/invoices/convert` – Invoice JSON → XML/PDF (base64 or direct download)
- `POST /api/v1/invoices/extract` – PDF/XML upload → structured Invoice JSON
- `POST /api/v1/invoices/validate` – XML upload → validation report
- `GET  /api/v1/invoices/records` – paginated processing history
- `GET  /api/v1/invoices/formats` – available output formats & profiles
- Auto-generated OpenAPI/Swagger docs at `/api/docs`

### CLI

- `invoiceforge convert` – convert PDF/XML/JSON to E-Rechnung (supports `nextcloud://` URIs)
- `invoiceforge extract` – extract invoice data to JSON (with `--llm` flag for LLM mode)
- `invoiceforge validate` – validate E-Rechnung XML with coloured output
- `invoiceforge serve` – start FastAPI server (`--host`, `--port`, `--reload`)
- `invoiceforge worker` – start ARQ background job worker
- `invoiceforge tenant create|list` – multi-tenant management

### Web UI

- **Streamlit Dashboard** – interactive pages for conversion, validation, tenant management and job history
- **HTMX + Jinja2** – server-rendered UI with partial page updates

### Multi-Tenant & Storage

- **Schema-based tenant isolation** in PostgreSQL with per-tenant config (company data, credentials, defaults)
- **API-key authentication** per tenant
- **Local filesystem** and **WebDAV/Nextcloud** storage backends
- **Background jobs** via ARQ + Redis for async conversion, extraction and validation

### Data Model (EN 16931)

- Full Pydantic model covering all semantic fields: parties, addresses, line items, tax breakdowns, totals, payment terms, IBAN/BIC, Leitweg-ID (B2G), currency codes and more

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| ZUGFeRD XML | drafthorse (CII) |
| UBL XML | lxml |
| PDF/A-3 | factur-x |
| PDF rendering | WeasyPrint + Jinja2 |
| PDF extraction | pdfplumber |
| OCR | pytesseract (optional) |
| LLM extraction | Anthropic Claude / Ollama (optional) |
| Template matching | invoice2data (optional) |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) + asyncpg |
| Migrations | Alembic |
| Background jobs | ARQ (Redis) |
| Validation | lxml (XSD) + KoSIT Validator (Schematron) |
| CLI | Typer |
| Web UI | Streamlit + HTMX + Jinja2 |
| Testing | pytest + pytest-asyncio + pytest-cov |
| Code quality | ruff + mypy + pre-commit |

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
├── ui/                  # Streamlit app + HTMX templates
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
