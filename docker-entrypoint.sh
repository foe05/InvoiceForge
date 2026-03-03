#!/bin/bash
set -e

# Run database migrations if DATABASE_URL is set and we're the API service
if [ -n "$DATABASE_URL" ] && echo "$@" | grep -q "uvicorn"; then
    echo "Running Alembic migrations..."
    python -m alembic upgrade head || echo "Warning: Migrations failed (DB may not be ready yet)"
fi

exec "$@"
