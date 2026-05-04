#!/bin/sh
set -e

echo "Waiting database..."
python /app/scripts/wait_for_db.py

echo "Running migrations..."
alembic upgrade head

echo "Starting Clonexa API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload