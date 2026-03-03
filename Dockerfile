# ============================================================
# InvoiceForge – Multi-Stage Docker Build
# ============================================================

# --- Stage 1: Build dependencies ---
FROM python:3.12-slim AS builder

RUN rm -rf /var/lib/apt/lists/* && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml ./
COPY app/__init__.py ./app/
RUN pip install --no-cache-dir --prefix=/install ".[ocr,ui]"


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
COPY pyproject.toml alembic.ini docker-entrypoint.sh ./

# Install the app package itself (dependencies already installed from builder)
RUN pip install --no-cache-dir --no-deps .

# Create directories
RUN mkdir -p /app/data/storage /app/data/schemas && \
    chmod +x /app/docker-entrypoint.sh /app/scripts/download_schemas.sh

EXPOSE 8000 8501

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
