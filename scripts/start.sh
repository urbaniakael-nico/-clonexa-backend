#!/usr/bin/env sh
set -eu

echo "CLONEXA starting..."
echo "ENVIRONMENT=${ENVIRONMENT:-development}"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "Using HOST=${HOST}"
echo "Using PORT=${PORT}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is required in production/Railway."
  echo "Set DATABASE_URL from Railway PostgreSQL: \${{Postgres.DATABASE_URL}}"
  exit 1
fi

if [ -z "${SECRET_KEY:-}" ] && [ -z "${JWT_SECRET_KEY:-}" ] && [ -z "${CLONEXA_JWT_SECRET:-}" ]; then
  echo "ERROR: SECRET_KEY or JWT_SECRET_KEY is required."
  exit 1
fi

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting uvicorn on ${HOST}:${PORT}"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"