# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

InvoiceForge is a German E-Rechnung (e-invoice) converter. It converts arbitrary inputs (PDF, XML, JSON) into ZUGFeRD 2.4/Factur-X PDFs and XRechnung 3.0.2 (CII or UBL) XML, and validates them against EN 16931. Python 3.12, FastAPI, async SQLAlchemy, HTMX-based web UI. Multi-user with cookie sessions; one tenant per user, strict data isolation in queries. All conversion is synchronous in the request handler — no background worker. (ARQ + Redis were removed; the codepath is recoverable if async ingestion is needed later.)

## Commands

### Local development (no Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ocr]"          # add ,llm  ,invoice2data as needed
invoiceforge serve --reload          # FastAPI on :8000, docs at /api/docs
```

The CLI lives at `app.cli.main:cli` and exposes `convert`, `extract`, `validate`, `serve`, `tenant create|list`, and `user create|list`. Inputs accept `nextcloud://path/to/file.pdf` URIs in addition to local paths.

### User onboarding

Users (and their 1:1 tenants) are created exclusively by an admin via the CLI:

```bash
docker exec invoiceforge-api invoiceforge user create \
    --email new.user@example.com --company "Firma GmbH" [--admin]
```

The command prints an initial password and the tenant's API key. The user must change the initial password on first login (`must_change_password=True` is enforced in `app/auth/dependencies.py`). The API key is for `/api/v1/*` calls via `X-API-Key` header — alternative to cookie auth.

### Docker

```bash
docker compose up -d                                       # prod stack (Postgres + API)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up   # dev: hot-reload + SQLite, no Postgres
docker compose --profile full up                           # adds KoSIT validator sidecar (downloads on first run)
```

The `backend` network is `internal: true` — Postgres has **no host ports**; reach it only from inside the Compose network. The API entrypoint runs `alembic upgrade head` automatically when started under uvicorn (see `docker-entrypoint.sh`).

### Tests / lint / types

```bash
pytest                                       # asyncio_mode=auto (set in pyproject.toml)
pytest tests/test_pipeline.py -k convert     # single test or pattern
pytest --cov=app                             # with coverage
ruff check app tests                         # lint
mypy app                                     # strict mode + pydantic plugin
```

### Database migrations

```bash
alembic upgrade head
alembic revision --autogenerate -m "..."
```

`alembic.ini` leaves `sqlalchemy.url` empty on purpose — `app/db/migrations/env.py` builds the engine from `app.config.settings` and uses **asyncpg** directly (do not switch back to psycopg2; that broke the build before — see commit `64368ff`).

### Validation schemas

`./scripts/download_schemas.sh data/schemas` fetches XRechnung Schematron, EN 16931 rules, and CII/UBL XSDs into `SCHEMA_DIR`. Required for offline Schematron validation. The KoSIT validator (Docker `--profile full`) is the official German government validator and runs as an HTTP sidecar at `KOSIT_VALIDATOR_URL`.

## Architecture

### The Invoice model is the pivot

`app/models/invoice.py` defines the EN 16931 semantic invoice as a Pydantic model. Every field is annotated with its EN 16931 Business Term ID (`BT-xx` / `BG-xx`) — preserve those references when adding fields, they are how the generators map data into ZUGFeRD/UBL/CII XML elements. All extractors converge on this model; all generators consume it. If you change `Invoice`, expect to update extractors, generators, and the SQLAlchemy `InvoiceRecord` mirror in `app/db/models.py`.

### Conversion pipeline (`app/core/pipeline.py`)

`ConversionPipeline.convert(invoice)` is the single orchestration point and always runs the same three steps:

1. **Generate XML** — branches on `invoice.output_format`:
   - `XRECHNUNG_UBL` → `UBLGenerator` (lxml-based)
   - `XRECHNUNG_CII` and `ZUGFERD_PDF` → `CIIGenerator` (drafthorse)
2. **Validate** — `InvoiceValidator` runs XSD + offline Schematron + (if reachable) KoSIT, returning a unified `FullValidationResult`.
3. **PDF embed** (only for `ZUGFERD_PDF`) — `PDFRenderer` (WeasyPrint + Jinja2 template) produces a visual PDF, then `ZUGFeRDGenerator` (factur-x) embeds the CII XML into PDF/A-3.

Each step appends to `errors`/`warnings` rather than raising; the result has `.success` and `.is_valid` properties. When adding a new output format, add an enum variant to `OutputFormat`, branch in step 1, and ensure the validator knows the schema.

### Multi-method extraction with fallback

`app/core/extraction/` contains four extractors that are meant to be tried in order, falling back when confidence is low:

`xml_extractor` (structured ZUGFeRD/UBL/CII) → `invoice2data_extractor` (template matching, optional dep) → `llm_extractor` (Anthropic or any OpenAI-compatible endpoint, e.g. IONOS AI Model Hub) → `ocr_extractor` (Tesseract for scanned PDFs).

`pdf_extractor` is a primitive used by the latter three (text + table extraction via pdfplumber). Optional extractors require their extras (`[llm]`, `[invoice2data]`, `[ocr]`) — code must guard imports and surface a clear error if the extra is missing rather than crashing.

### Validation has three layers, unified

`app/core/validation/validator.py` defines `FullValidationResult` (with `level: VALID | WARNINGS | INVALID`) and aggregates results from `xsd_validator` (lxml), `schematron_validator` (offline, uses downloaded artefacts), and `kosit_client` (HTTP to the KoSIT sidecar). KoSIT is treated as best-effort: if unreachable, validation continues with the offline layers. Any new validation code should plug into this aggregator, not bypass it.

### Multi-tenancy + Authentication

Two tables drive isolation:
- `tenants` (rows with `config` JSON blob — company master data, Nextcloud creds, defaults)
- `users` (login identity, 1:1 with `tenants` via `tenant_id` FK)

Users are created by admins via `invoiceforge user create`. A new user gets a forced-pwd-change marker (`must_change_password=True`) and is redirected to `/account/password` on first login.

Authentication paths (see `app/auth/dependencies.py`):
1. **Cookie session** — primary path, set after `/login` form submit. Signed with `app_secret_key`, HttpOnly, SameSite=Lax. CSRF tokens guard form POSTs.
2. **`X-API-Key` header** — for headless API clients on `/api/v1/*`. Resolves to a `Tenant`, then to its associated `User` for tenant-scoping.

Both routers (`/ui/*` and `/api/v1/*`) declare `dependencies=[Depends(require_user)]` at the router level. Query-level scoping is enforced by passing `str(user.tenant_id)` into the `InvoiceService` calls — never trust client-supplied tenant identifiers. Cross-tenant reads on `/api/v1/invoices/records/{id}` return 404 (not 403) to avoid existence leakage.

Per-tenant Nextcloud creds override the global `WEBDAV_*` / `NEXTCLOUD_*` env vars when resolving `nextcloud://` URIs.

### Storage

`app/core/storage/` has two backends (`LocalStorage`, `WebDAVStorage`) sharing an interface. `nextcloud://` URIs in CLI args route through `WebDAVStorage`. Conversions run synchronously in the request handler — there is no background worker. If async ingestion becomes needed (batch processing, webhooks), reintroduce ARQ + Redis.

### Web UI

HTMX routes mounted directly on the FastAPI app (`app/api/ui_routes.py`) with Jinja2 templates under `ui/templates/`. Server-rendered, partial updates. Auth is enforced by the router-level `Depends(require_user)`. There is no Streamlit UI anymore; it was removed in the auth refactor (it had no native session integration with FastAPI and duplicated the conversion logic).

### Config

All runtime config flows through `app.config.Settings` (pydantic-settings, reads `.env`). Use `settings.is_development` to gate dev-only behavior. Access secrets via `settings`, never via `os.environ` directly. The `database_url` defaults to async (`postgresql+asyncpg://...`); a `database_url_sync` property exists but is **not** used by Alembic anymore — env.py uses asyncpg directly.

## Conventions

- Python 3.12, type hints everywhere (`mypy --strict`), `from __future__ import annotations` at the top of modules.
- Ruff config in `pyproject.toml`: line length 100, rule sets `E,F,I,N,W,UP,B,A,SIM`.
- Mixed-language docstrings/comments (German + English) are the existing norm — match the surrounding file.
- All new I/O is async (FastAPI handlers, DB access, HTTP clients via httpx).
- Money is always `Decimal`, never `float`; dates are `datetime.date`.
- Don't widen the public surface of optional features (LLM, OCR, invoice2data) without guarding imports — they live behind extras.

## File layout (only the parts that aren't obvious)

- `app/core/pipeline.py` — single conversion orchestrator; start here when tracing a request.
- `app/core/generation/` — output writers; one file per format family.
- `app/core/validation/validator.py` — aggregator for all three validation layers.
- `app/db/migrations/env.py` — async Alembic setup; do not "fix" it to use psycopg2.
- `tests/conftest.py` — `sample_invoice` fixture; the canonical valid Invoice for tests.
- `scripts/download_schemas.sh` — fetches validation artefacts; required for full offline validation.

## Standards reference

- EN 16931 — European semantic invoice model (BT-/BG- field IDs)
- XRechnung 3.0.2 — German CIUS, B2G mandatory
- ZUGFeRD 2.4 / Factur-X 1.08 — hybrid PDF/A-3 + CII-XML
- PEPPOL BIS Billing 3.0 — pan-European network
