# Walking Skeleton — Data Center Stocks

**Phase:** 1
**Generated:** 2026-07-19

## Capability Proven End-to-End

The owner edits a ticker in a YAML file, runs one command, and sees that change reflected as a live company count on an HTTPS page served by the deployed stack — with the underlying prices and SEC fundamentals stored and traceable to their source filings.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI 0.139.x on Python 3.12/3.13, sync routes | Locked in CLAUDE.md. Sync routes plus sync SQLAlchemy: the ingest is a once-daily single-process batch mostly waiting on rate-limited HTTP, so async buys nothing and costs event-loop plumbing. FastAPI runs `def` routes in a threadpool, so concurrent dashboard reads are unaffected. |
| Frontend framework | Next.js 16 App Router, TypeScript, Server Components | Locked in CLAUDE.md. Node 20.9+ required (local has 22.16.0). `next lint` no longer exists in 16 and dynamic APIs are async-only — both are live constraints on every later phase. |
| ORM / migrations | SQLAlchemy 2.0.x typed `Mapped[]` models + Alembic 1.18.x with `render_as_batch=True` | 2.0 `select()` idiom exclusively, never 1.x `Query`. Batch mode is set from the first migration so SQLite and Postgres migration histories stay consistent — retrofitting it later breaks the second migration on SQLite only. |
| Data layer | SQLite via `DATABASE_URL`, Postgres-ready | One writer, one reader, once-daily batch — SQLite is correctly sized. Models avoid engine-specific constructs so the swap is a config change. No `db` container in compose until Postgres is actually needed. |
| Fundamentals source | Hand-rolled `httpx` SEC EDGAR client | Locked in CLAUDE.md over `sec-edgar-api` and OpenBB. Three simple endpoints; a hand-rolled client keeps the filer-type branching — this phase's core risk — visible and testable rather than hidden inside a wrapper. |
| Price source | `yfinance`, prototyping-scope | Explicitly disposable per CLAUDE.md. Do not build production error handling around its quirks; per-ticker failure isolation is the design response. FMP replaces it in v2 (DATA-01). |
| Fundamentals storage shape | Point-in-time, unique on `(ticker, fiscal_year, fiscal_period, accession_number)`, insert-or-ignore | The single most expensive-to-retrofit decision in the system. A coarser key silently discards filing history on every re-run; restatements arrive under new accession numbers and must insert alongside originals, not overwrite them. |
| Resilience model | Per-ticker try/except isolation, `tenacity` bounded retry with jitter, failures accumulated to `refresh_log` | STORE-02 is violated the moment one ticker's failure ends the run. Every network call inside the per-ticker loop is caught, never propagated. |
| Config | `pydantic-settings` `Settings` class, single source of truth | No scattered `os.environ` access. Carries `DATABASE_URL` and `EDGAR_USER_AGENT`. |
| Auth | None — no application-level authentication | Locked out of v1 by REQUIREMENTS.md (single personal user). Access control in practice is that the backend has no exposed domain; only the frontend does. Revisit only if the tool is shared. |
| Deployment target | docker-compose on Coolify VPS, git-push-to-deploy, 2 services, SQLite on a persistent volume | Locked in PROJECT.md. No `db` container, no cron sidecar — Coolify's native scheduled task `docker exec`s into the running backend. |
| Scheduling | Coolify scheduled task, `0 2 * * *` UTC | Fixed UTC rather than literal 9pm ET: Coolify exposes no timezone override and five-field cron cannot express DST-aware local time. 02:00 UTC is 9pm EST / 10pm EDT — after close under both. |
| Directory layout | `backend/app/{api,ingest}` + `frontend/app`, compose at repo root | Ingest modules are one-concern files (`taxonomy`, `cik_resolver`, `edgar_client`, `prices`, `fundamentals`, `refresh`); `models.py` is single-file at this scale. Pydantic response schemas stay separate from SQLAlchemy models so provenance columns are not forced into every response shape. |

## Stack Touched in Phase 1

- [x] Project scaffold — `uv` backend with pytest/ruff, `create-next-app` frontend, Dockerfiles for both (plan 01)
- [x] Routing — `GET /health` and `GET /companies` on the backend; the frontend status page route (plan 01)
- [x] Database — real write (taxonomy sync, prices, fundamentals) and real read (`GET /companies`), under Alembic migration (plans 01-04)
- [x] UI — the status page fetches the backend server-side and renders live count, empty, and error states (plan 01)
- [x] Deployment — deployed to the Coolify VPS by git push, plus `docker compose up --build` as the documented local full-stack command (plans 01, 05)

## Out of Scope (Deferred to Later Slices)

- Any real UI beyond the status page — no tables, sorting, charts, or interactive controls (D-12; Phase 2 builds the first real page from scratch)
- Component library / shadcn init — deliberately deferred to Phase 2, where real components are first needed (01-UI-SPEC.md)
- Computed valuation ratios, percentile ranks, screens, composite scores (Phase 4, ANALYSIS-01..04)
- Company detail pages, price charts, sector heatmap (Phase 3)
- CSV export, watchlist (Phase 5)
- Trust indicators as UI — freshness and source are stored and returned by the API in Phase 1, but rendered in Phase 2 (TRUST-01/02)
- Endpoint splitting — Phase 1 has exactly one data endpoint by D-08; purpose-built endpoints wait until the API design settles
- Sub-sub-sector nesting and dual sub-sector membership (declined for v1, D-03)
- Automated ticker-liveness checking; delisted tickers are never auto-removed (declined for v1, D-02/D-02a)
- Postgres container, multi-sector generalization, FMP data feed, filings watcher (v2)
- Multi-user auth (out of scope for v1 entirely)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering the architectural decisions above:

- **Phase 2:** Owner browses all companies in a sortable sub-sector-grouped table with freshness and source visible — consumes the same `GET /companies` data, adds purpose-built endpoints and the first real component library.
- **Phase 3:** Owner drills into a single company's valuation detail with a price chart, and sees a sector heatmap.
- **Phase 4:** Owner compares companies against their true peer group via percentile ranks, scoped screens, and a transparent composite score — computed from the raw data this skeleton stores, via FinanceToolkit fed by DataFrame rather than its auto-fetch mode.
- **Phase 5:** Owner exports any view to CSV and maintains a persistent starred watchlist.
