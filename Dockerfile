# NaijaStay API — two-stage build.
#
# Stage 1 (builder): resolve + install locked deps with uv into /app/.venv.
# Stage 2 (runtime): slim Python, non-root user, venv + source only.
#   Prod deps only (`uv sync --locked --no-dev`); tests/pytest stay out.
#   Wiring (ports, DATABASE_URL/REDIS_URL, migration) lives in compose.yaml.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependency layer first for build-cache reuse.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- runtime ----
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Non-root user owns the app tree.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Source (migrations + seed + entrypoint included; .dockerignore drops the rest).
COPY --chown=appuser:appuser alembic.ini ./alembic.ini
COPY --chown=appuser:appuser migrations/ ./migrations/
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser scripts/seed.py ./scripts/seed.py
COPY --chown=appuser:appuser mock_payment_provider.py ./mock_payment_provider.py
COPY --chown=appuser:appuser scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
