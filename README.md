# Data Center Stocks

A personal research and tracking tool for public-company sector "value
chains" — starting with the ~54-company data center value chain (chips,
memory, networking, power, cooling, colocation REITs, hyperscalers,
construction/materials). It pulls daily prices and SEC EDGAR fundamentals,
groups every company by sub-sector, and (in later phases) runs
relative-value screens so one company can be judged against its actual
peers rather than against the whole market.

Built for one user (the owner), for personal investing decisions — not
investment advice, and not a multi-user product.

## Stack

- **Backend:** Python 3.12/3.13, FastAPI, SQLAlchemy 2.0, Alembic, `uv`
- **Frontend:** Next.js 16 (App Router, TypeScript)
- **Storage:** SQLite for local dev and the MVP, `DATABASE_URL`-driven
  Postgres upgrade path (see `docs/deployment.md`)
- **Deployment:** docker-compose stack on Coolify, git-push-to-deploy

## Local development

### Backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.ingest.taxonomy   # seeds sectors.yaml into the DB
uv run uvicorn app.main:app --reload
```

The API serves at `http://localhost:8000`; `GET /health` and
`GET /companies` are the two routes.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The status page serves at `http://localhost:3000` and fetches
`GET /companies` from the backend server-side (`BACKEND_URL` env var,
defaults to `http://backend:8000` inside Docker or
`http://localhost:8000` for local `npm run dev` against a locally-running
backend).

### Full-stack local run (Docker)

```bash
docker compose up --build
```

Brings up both services on Docker's internal network. Note that neither
service publishes a host port in the committed `docker-compose.yml`
(that's intentional — see the comment at the top of the file and
`docs/deployment.md`), so from the host you won't be able to
`curl localhost:8000` directly. To check the containers are healthy:

```bash
docker compose exec backend curl -f http://localhost:8000/health
docker compose exec frontend wget -qO- http://localhost:3000
```

For day-to-day development, running the backend and frontend directly on
the host (above) is faster than rebuilding containers on every change;
`docker compose up --build` is mainly there to prove the production
container images work end to end before deploying.

### Running the tests

```bash
cd backend && uv run pytest
```

(If `uv` isn't on your `PATH`, run the already-synced venv's Python
directly: `.venv/Scripts/python.exe -m pytest -q` on Windows, or
`.venv/bin/python -m pytest -q` on macOS/Linux.)

### Editing the ticker taxonomy

`backend/sectors.yaml` is the owner-editable source of truth for which
tickers are tracked and which sub-sector each belongs to. Edit it, then
either re-run `uv run python -m app.ingest.taxonomy` locally or push to
the tracked branch to have Coolify redeploy and re-sync it in production
— see `docs/deployment.md`.

## Deployment

See [`docs/deployment.md`](docs/deployment.md) for the full Coolify
deploy and operations runbook: initial setup, required environment
variables, domain assignment, the persistent volume for SQLite, the daily
scheduled refresh task (and why its cron time is a deliberate fixed-UTC
choice rather than a literal "9pm ET"), day-to-day operations, and the
Postgres upgrade path.
