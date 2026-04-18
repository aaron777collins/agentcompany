FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── builder: install deps into a virtual environment ──────────────────────────
FROM base AS builder
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
# uv creates a venv at /app/.venv
RUN uv venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# ── runtime: copy only what the service needs ─────────────────────────────────
FROM base AS runtime
COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Single worker: asyncio handles concurrency; horizontal scale via replicas.
# See agent-runtime.md § Deployment for the rationale.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
