"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import api_router
from app.api.ui_routes import router as ui_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown events."""
    # Startup: ensure storage directory exists
    settings.storage_base_path.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown: cleanup if needed


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
