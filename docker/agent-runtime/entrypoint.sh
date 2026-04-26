#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
# asyncpg connect attempt is cheap and gives us the same auth path the app uses,
# so failures here are meaningful (not just TCP-level liveness).
until python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect('${DATABASE_URL}'))" 2>/dev/null; do
    sleep 2
done
echo "PostgreSQL ready."

echo "Running database migrations..."
cd /app
alembic upgrade head

echo "Starting agent-runtime..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
