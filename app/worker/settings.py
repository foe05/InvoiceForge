"""ARQ worker settings.

Start the worker with:
    arq app.worker.settings.WorkerSettings
"""

from __future__ import annotations

from arq.connections import RedisSettings

from app.config import settings
from app.worker.tasks import convert_invoice, extract_invoice, validate_invoice


def parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into ARQ RedisSettings."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or "0"),
        password=parsed.password,
    )


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [convert_invoice, extract_invoice, validate_invoice]
    redis_settings = parse_redis_url(settings.redis_url)
    max_jobs = 10
    job_timeout = 300  # 5 minutes
    keep_result = 3600  # Keep results for 1 hour
    health_check_interval = 30
