# ============================================================
# InvoiceForge – Multi-Stage Docker Build
# ============================================================

# --- Stage 1: Build dependencies ---
FROM python:3.12-slim AS builder

RUN rm -rf /var/lib/apt/lists/* && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY app/__init__.py ./app/
RUN pip install --no-cache-dir --prefix=/install ".[ocr]"


# --- Stage 2: Runtime image ---
FROM python:3.12-slim AS runtime

# System dependencies (runtime only – no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    libxml2 \
    libxslt1.1 \
    tesseract-ocr \
    tesseract-ocr-deu \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY app/ ./app/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY pyproject.toml README.md alembic.ini docker-entrypoint.sh ./

# Install the app package itself (dependencies already installed from builder).
#
# This MUST be an editable install. A regular install copies app/ into
# site-packages, giving the image two copies of the code: uvicorn runs with
# cwd=/app and imports /app/app, while the `invoiceforge` console script has no
# cwd on sys.path and imports the site-packages copy. They agree on a fresh
# build and drift apart the moment anything touches one of them.
# Editable keeps /app/app as the single source — alembic.ini's
# `script_location = app/db/migrations` depends on that path existing anyway.
# Build isolation stays on so pip provides hatchling and its `editables`
# helper; --no-deps keeps it from touching the runtime deps already staged
# from the builder image.
RUN pip install --no-cache-dir --no-deps -e .

# Create directories
RUN mkdir -p /app/data/storage /app/data/schemas && \
    chmod +x /app/docker-entrypoint.sh /app/scripts/download_schemas.sh

EXPOSE 8000 8501

# Healthchecks are defined per-service in docker-compose.yml.

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
