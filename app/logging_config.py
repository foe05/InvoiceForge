"""Structured logging configuration for InvoiceForge.

Configures JSON-formatted logging for production and human-readable
format for development. Uses stdlib logging with structured extras.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import settings


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields (job_id, tenant_id, etc.)
        for key in ("job_id", "tenant_id", "invoice_number", "method", "path", "status_code"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, ensure_ascii=False)


class DevFormatter(logging.Formatter):
    """Human-readable log formatter for development."""

    FORMATS = {
        logging.DEBUG: "\033[36m%(levelname)-5s\033[0m %(name)s: %(message)s",
        logging.INFO: "\033[32m%(levelname)-5s\033[0m %(name)s: %(message)s",
        logging.WARNING: "\033[33m%(levelname)-5s\033[0m %(name)s: %(message)s",
        logging.ERROR: "\033[31m%(levelname)-5s\033[0m %(name)s: %(message)s",
        logging.CRITICAL: "\033[1;31m%(levelname)-5s\033[0m %(name)s: %(message)s",
    }

    def format(self, record: logging.LogRecord) -> str:
        fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(fmt)
        return formatter.format(record)


def setup_logging() -> None:
    """Configure application-wide logging.

    - Development: colored, human-readable output to stderr
    - Production/Staging: JSON-formatted structured logs to stderr
    """
    root_logger = logging.getLogger()

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)

    if settings.is_development:
        handler.setFormatter(DevFormatter())
        log_level = logging.DEBUG if settings.app_debug else logging.INFO
    else:
        handler.setFormatter(JSONFormatter())
        log_level = logging.INFO

    handler.setLevel(log_level)
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers.
    # fontTools/weasyprint/factur-x emit dozens of INFO lines per PDF render;
    # they're only useful when actively debugging font/PDF issues.
    for name in (
        "httpx",
        "httpcore",
        "asyncio",
        "urllib3",
        "sqlalchemy.engine",
        "fontTools",
        "fontTools.subset",
        "fontTools.ttLib",
        "weasyprint",
        "factur-x",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Drop healthcheck spam from uvicorn's access log (15s interval × 1440 min/day
    # = ~5760 lines/day per service). Errors on /health still surface via the
    # error logger and via Docker's healthcheck status.
    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())

    logging.getLogger("app").setLevel(log_level)


class _HealthCheckFilter(logging.Filter):
    """Suppress access-log lines for the /health endpoint."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/health" not in message and "/healthz" not in message
