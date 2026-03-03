"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.api.ui_routes import router as ui_router
from app.config import settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown events."""
    setup_logging()
    logger.info("InvoiceForge %s starting (env=%s)", __version__, settings.app_env.value)

    # Startup: ensure storage directory exists
    settings.storage_base_path.mkdir(parents=True, exist_ok=True)
    yield
    logger.info("InvoiceForge shutting down")


app = FastAPI(
    title="InvoiceForge",
    description="German E-Rechnung converter – ZUGFeRD & XRechnung from multiple inputs",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# API routes
app.include_router(api_router, prefix="/api/v1")

# UI routes (HTMX)
app.include_router(ui_router)

# Static files for UI
_static_dir = Path(__file__).resolve().parent.parent / "ui" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
