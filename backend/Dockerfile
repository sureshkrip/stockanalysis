FROM python:3.13-slim

# Install uv (single static binary, no pip bootstrap needed at runtime).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first so `uv sync` is cached across rebuilds that
# only change application source.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the rest of the application source.
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# --no-sync: the frozen, no-dev environment was already synced at build
# time; without this flag `uv run` re-syncs (incl. dev deps) on every
# container start, adding needless network dependency and startup latency.
# Self-migrate on startup so a fresh volume gets the current schema, sync
# sectors.yaml into the tickers table (TAXO-01 proof surface, superseded by
# the full app.ingest.refresh orchestrator in plan 02), then serve the API.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync python -m app.ingest.taxonomy && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
