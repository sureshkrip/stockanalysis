# Stack Research

**Domain:** Personal financial data ingestion + screening/dashboard web app (self-hosted)
**Researched:** 2026-07-19
**Confidence:** MEDIUM-HIGH (versions verified directly against PyPI/npm/official docs; architectural recommendations are opinionated synthesis, flagged per-item)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 or 3.13 | Backend runtime | FastAPI requires 3.10+; OpenBB/FinanceToolkit cap at <3.16/<3.15 respectively — 3.12/3.13 is the safe middle that satisfies every dependency's floor and ceiling simultaneously. Avoid 3.14+ until OpenBB/FinanceToolkit confirm support. |
| FastAPI | 0.139.x (latest verified: 0.139.2, released 2026-07-16) | Backend API framework | Standard choice for a typed Python API with automatic OpenAPI docs; pairs natively with Pydantic v2 for the response models a screener needs (ratios, rankings). Confirmed current via PyPI. |
| SQLAlchemy | 2.0.x (latest verified: 2.0.51, released 2026-06-15) | ORM / database toolkit | 2.0 is the stable, mature line — do **not** wait for or adopt 2.1 (still pre-release churn as of writing); 2.0's `select()`-style query API and `Mapped[]` typed models are the current idiom. Confirmed current via PyPI. |
| Alembic | 1.18.x (latest verified: 1.18.5, released 2026-06-25) | Schema migrations | De facto standard migration tool for SQLAlchemy; only credible choice in this ecosystem. Confirmed current via PyPI. |
| Next.js | 16.x (App Router; latest verified: 16.2.7, major stable since 2025-10-21) | Frontend framework | Turbopack is now the default bundler (stable, 2-5x faster builds), React Compiler support is stable, and this is the current major — building on 15 today would mean an immediate forced upgrade. Requires Node.js 20.9+ and TypeScript 5.1+. |
| TypeScript | 5.1+ (use latest 5.x) | Frontend language | Next.js 16 hard-requires 5.1 minimum; no reason to pin lower. |
| Recharts | 3.x (current major) | Charting (price charts, heatmaps) | See dedicated comparison below — recommended over alternatives for this project's scale. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uv` | latest (Astral) | Python dependency/venv/interpreter management | Use from day one — see dedicated section below. Replaces pip + venv + pip-tools/poetry in one binary. |
| `psycopg` (v3) or `asyncpg` | latest | Postgres driver | `asyncpg` if you go fully async end-to-end; `psycopg[binary]` v3 if you want one driver that also works reasonably in sync contexts. Only needed once you upgrade from SQLite. |
| `httpx` | latest | HTTP client for SEC EDGAR / yfinance-adjacent calls | Async-native, drop-in replacement for `requests`; needed regardless of whether routes are async, for calling out to EDGAR with proper timeout/retry control. |
| `pydantic` | v2.x (ships with FastAPI) | Data validation / response schemas | Use for both API response models and for validating scraped/ingested data before it hits SQLAlchemy — catches malformed EDGAR/yfinance payloads early. |
| `apscheduler` or Coolify's built-in scheduled-task runner | latest | Daily ingest scheduling | Per PROJECT.md constraint, prefer Coolify's native scheduled tasks over an in-process scheduler — one less moving part inside the container, no need to keep a long-running process alive just for cron. Use `apscheduler` only if you need sub-daily/intraday scheduling logic that Coolify's cron can't express. |
| `financetoolkit` | 2.1.4 (latest, MIT) | Ratio/valuation math | See dedicated section below. |
| `sec-edgar-api` (or hand-rolled `httpx` client) | latest | SEC EDGAR wrapper | Optional thin convenience wrapper; the raw API is simple enough (3 endpoints: submissions, companyfacts, companyconcept) that a ~50-line hand-rolled client is arguably less risk than a third dependency for something this small. See EDGAR section. |
| `yfinance` | latest | Prototyping-only price data | Explicitly prototyping-scope per PROJECT.md — do not build the production ingest path's error handling around its quirks; treat it as disposable. |
| `pandas` | latest 2.x | DataFrame handling | Required transitively by FinanceToolkit and yfinance; also the natural shape for ratio/screen computations before they get written back via SQLAlchemy. |
| `python-dotenv` (or Pydantic Settings) | latest | Env config incl. `DATABASE_URL` | Pydantic's `BaseSettings` (via `pydantic-settings` package) is the more idiomatic FastAPI-native choice — gives you typed, validated config including the SQLite/Postgres `DATABASE_URL` switch in one place. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | dependency install, lockfile, Python version pinning | `uv init`, `uv add fastapi sqlalchemy alembic`, `uv run` — see dependency management section. |
| `ruff` | Python lint + format | Also from Astral (same team as uv); replaces flake8+black+isort in one fast tool — natural pairing with uv, no reason to reach for anything else in 2026. |
| Docker Compose | container orchestration | Coolify's native deployment target — see docker-compose section below. |
| `pytest` + `pytest-asyncio` | testing | Needed regardless of async/sync choice; `pytest-asyncio` only if async routes/tests are used. |

## Installation

```bash
# Python backend (via uv)
uv init backend && cd backend
uv add fastapi "uvicorn[standard]" sqlalchemy alembic pydantic-settings httpx \
  financetoolkit yfinance pandas
uv add --dev ruff pytest pytest-asyncio
# Add asyncpg or psycopg[binary] only when you actually turn on Postgres:
uv add asyncpg   # or: uv add "psycopg[binary]"

# Frontend
npx create-next-app@latest frontend --typescript --app --tailwind
cd frontend
npm install recharts
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Recharts | Lightweight Charts (TradingView) | If the price-chart page needs true candlestick/OHLC rendering with volume histograms — Lightweight Charts is purpose-built for that and nothing else does it as cleanly. You'd then run two charting libraries (Recharts for heatmap/bar/composite views, Lightweight Charts for the single-company price page), which is a reasonable split for this project since price charts and sector heatmaps have genuinely different rendering needs. |
| Recharts | Nivo | If the heatmap specifically needs polish beyond what you can get from a Recharts custom-cell grid (Nivo ships an actual `ResponsiveHeatMap` component with 30+ chart types total). Heavier dependency and less "just React props" than Recharts for line/bar/area, so only reach for it if you specifically want its heatmap or treemap components. |
| Recharts | visx | If you want full D3-level control over rendering (custom scales, exotic interactions) and don't mind writing more code per chart. Wrong choice for someone trying to ship a dashboard quickly — visx is a toolkit for building your own chart library, not a chart library. |
| Direct yfinance + hand-rolled EDGAR client | OpenBB Platform | If the project later needs many additional data providers (macro, options, crypto, alt-data) simultaneously, or if multiple people/projects will reuse the same data-access layer — OpenBB's value is provider abstraction at scale, which a single-user ~55-ticker tool doesn't need yet. Revisit if the ticker universe or provider count grows substantially. |
| uv | Poetry | If this project ever needs to be published as an installable PyPI library (it won't — it's an app, not a library) — Poetry's `poetry publish` workflow is more polished for that specific case. Not relevant here. |
| SQLite → Postgres via `DATABASE_URL` | Postgres from day one | If you already know you'll exceed SQLite's concurrent-writer limits early (unlikely for a single-user daily-batch tool) or want to test Postgres-specific features (e.g. `JSONB`, extensions) from day one. For this project's actual load (one writer, one reader, daily batch), SQLite-first is correct and the migration path is well-trodden (see Alembic section). |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| OpenBB Platform as the default data layer for this project's current scale | AGPL-3.0 dependency pulling in a large, actively-evolving provider abstraction (Python 3.10-3.14 only, 8GB+ RAM recommended) for a 55-ticker personal tool is disproportionate weight versus 2-3 direct HTTP clients you fully control and can debug in 5 minutes. It also adds a license constraint (AGPL triggers source-disclosure obligations if you ever modify-and-distribute or SaaS-host it for others) that a direct-client approach avoids entirely. | Direct `yfinance` (prototyping) + a small hand-rolled `httpx`-based SEC EDGAR client (production fundamentals) + Financial Modeling Prep's Starter plan once budget is justified (per PROJECT.md). Revisit OpenBB only if provider count/complexity grows well past what a personal tool needs. |
| Building the batch ingest path as fully async top-to-bottom by default | Async buys nothing for a scheduled, single-process daily batch job that's mostly waiting on 3 external HTTP APIs sequentially/rate-limited anyway (EDGAR's 10 req/sec cap makes concurrency gains marginal and risks tripping the rate limiter). Async correctness overhead (session lifecycle, event loop plumbing) is real cost for no real benefit here. | Sync FastAPI routes + sync SQLAlchemy for the CRUD/API surface (FastAPI runs `def` routes in a threadpool automatically, so this doesn't block the event loop for concurrent dashboard requests). Use `httpx` with basic concurrency limiting (e.g. a semaphore) *inside* the ingest script only if you need to speed up prototyping-era yfinance pulls — not as an architecture-wide async requirement. |
| `next lint` (removed in Next.js 16) | Next.js 16 removed the bundled `next lint` command entirely; `next build` no longer runs linting as a side effect. | ESLint or Biome configured directly, run in CI/pre-commit — not deferred to the framework. |
| Sync `params`/`searchParams`/`cookies()`/`headers()` access patterns from older Next.js tutorials | Removed in Next.js 16 — these are now async-only (`await params`, `await cookies()`); code copied from pre-16 tutorials will silently misbehave or throw. | Always `await` these APIs; if following an older guide, check it against the [Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16) first. |
| pip + requirements.txt (no lockfile) or bare `pip-tools` for this greenfield project | Slower installs, no cross-platform lockfile guarantee, more manual venv management — none of that buys anything for a 2026 greenfield project with no legacy constraint forcing it. | `uv` — see dependency management section. |
| Treating FinanceToolkit's default (FMP-API-key) mode as required | The library's primary data path assumes a Financial Modeling Prep subscription; without a key it falls back to yfinance automatically (since v2.0.3), but that reintroduces yfinance's reliability caveats into ratio computation if not handled carefully. | Feed FinanceToolkit your own already-ingested SEC EDGAR + price data directly via its DataFrame-input constructor args instead of letting it re-fetch from FMP/yfinance — keeps the SEC EDGAR "source of record" decision from PROJECT.md intact and avoids double-fetching. |

## Stack Patterns by Variant

**If the batch ingest script needs to survive per-ticker failures (an explicit PROJECT.md requirement):**
- Wrap each ticker's fetch+parse+write in its own try/except, log and continue rather than aborting the whole run
- Because a single malformed EDGAR filing or a transient yfinance 429 for one of 55 tickers should never block updating the other 54

**If deploying via Coolify docker-compose (this project's deployment target from Phase 0):**
- Structure as 3 services: `backend` (FastAPI + Uvicorn), `frontend` (Next.js), `db` (Postgres, or omit entirely and mount a SQLite file via a named volume on `backend` for the MVP)
- Because Coolify auto-creates a shared Docker network per compose stack (no explicit `networks:` block needed) and only exposes services you attach a domain/port to — the `db` service should have no exposed port, reachable only by `backend` over the internal network

**If still on SQLite (MVP phase):**
- Skip the `db` service entirely; mount a Coolify persistent volume at the path your SQLAlchemy `DATABASE_URL` (e.g. `sqlite:////data/app.db`) points to
- Because adding a Postgres container before you need one is exactly the kind of premature complexity PROJECT.md's "SQLite first" decision was meant to avoid — the migration path (below) means this costs nothing to defer

**If/when upgrading SQLite → Postgres:**
- Point `DATABASE_URL` at the new Postgres service, run `alembic upgrade head` against it, backfill data with a one-off script (or a tool like `pgloader`) — no application code changes required if models were written database-agnostically (avoid SQLite-only types, avoid raw SQL with SQLite-specific syntax)
- Because this was the entire point of the `DATABASE_URL`-driven config decision in PROJECT.md; validate it works by testing the Postgres path in CI/locally periodically during MVP development, don't wait until the actual cutover to discover an incompatibility

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `fastapi` 0.139.x | Python >=3.10 | Confirmed via PyPI; use 3.12/3.13 for this project (see Python row above). |
| `openbb` 4.7.2 (if adopted later) | Python >=3.10, <4 (practically <3.15) | Narrower ceiling than FastAPI/SQLAlchemy — if OpenBB is ever added, it becomes the binding constraint on your Python version, not FastAPI. |
| `financetoolkit` 2.1.4 | Python >=3.10, <3.16 | Slightly wider ceiling than OpenBB; not a binding constraint if OpenBB is out of the stack. |
| `next` 16.x | Node.js >=20.9.0, TypeScript >=5.1.0 | Node 18 is explicitly no longer supported — check the Coolify VPS's Node version/base image before deploying. |
| `alembic` 1.18.x | `sqlalchemy` 2.0.x | Alembic's SQLite "batch mode" (`render_as_batch=True` in `env.py`) is required specifically because SQLite doesn't support most `ALTER TABLE` variants — set this from the first migration, not retroactively, so the SQLite and Postgres migration histories stay consistent. |

## Sources

- PyPI (direct fetch, HIGH confidence): fastapi (0.139.2, 2026-07-16), sqlalchemy (2.0.51, 2026-06-15), alembic (1.18.5, 2026-06-25), financetoolkit (2.1.4, 2026-07-14), openbb (4.7.2, 2026-05-26)
- [nextjs.org/blog/next-16](https://nextjs.org/blog/next-16) (direct fetch, HIGH confidence) — Next.js 16 release notes, version requirements, breaking changes
- [SEC EDGAR API rate limits and User-Agent requirements](https://tldrfiling.com/blog/sec-edgar-api-rate-limits-best-practices) and [SEC EDGAR API guide](https://tldrfiling.com/blog/sec-edgar-api-guide) — web search, cross-checked across multiple independent articles, MEDIUM-HIGH confidence
- [Coolify Docker Compose docs](https://coolify.io/docs/knowledge-base/docker/compose) — web search, MEDIUM confidence
- [OpenBB license change announcement](https://openbb.co/blog/license-change-openbb-platform-goes-agpl/) and [OpenBB license FAQ](https://docs.openbb.co/python/faqs/license/) — web search, MEDIUM confidence
- [FinanceToolkit GitHub](https://github.com/JerBouma/FinanceToolkit) and [PyPI page](https://pypi.org/project/financetoolkit/) — web search + direct fetch, MEDIUM confidence (DataFrame-input constructor behavior not independently re-verified against source in this session — flagged as a gap, verify against `toolkit_controller.py` during Phase 0/1 implementation)
- [uv vs Poetry vs pip-tools comparison](https://www.danilchenko.dev/posts/uv-vs-pip-vs-poetry/), [Python packaging 2026 overview](https://andrewodendaal.com/python-packaging-2026-uv-poetry-modern-ecosystem/) — web search, cross-checked across multiple independent 2026-dated articles, MEDIUM confidence
- [React chart library comparison (Recharts/Nivo/visx/Lightweight Charts)](https://www.pkgpulse.com/guides/recharts-vs-chartjs-vs-nivo-vs-visx-react-charting-2026) and [LogRocket chart library roundup](https://blog.logrocket.com/best-react-chart-libraries-2026/) — web search, cross-checked across multiple independent 2026-dated articles, MEDIUM confidence
- [yfinance rate limiting discussion](https://github.com/ranaroussi/yfinance/discussions/2431) and [yfinance issue #2128](https://github.com/ranaroussi/yfinance/issues/2128) — GitHub issue tracker (primary-source community evidence), MEDIUM-HIGH confidence

---
*Stack research for: Personal financial data ingestion + screening dashboard (self-hosted, FastAPI/Next.js/SQLite-Postgres/Coolify)*
*Researched: 2026-07-19*
