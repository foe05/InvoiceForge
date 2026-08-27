#!/bin/bash
set -e

# Run database migrations if DATABASE_URL is set and we're the API service.
# Postgres readiness is guaranteed by `depends_on: service_healthy` in
# docker-compose.yml, so a migration failure is a real bug — let it crash the
# container instead of silently continuing with a broken schema.
if [ -n "$DATABASE_URL" ] && echo "$@" | grep -q "uvicorn"; then
    echo "Running Alembic migrations..."
    python -m alembic upgrade head
fi

exec "$@"
