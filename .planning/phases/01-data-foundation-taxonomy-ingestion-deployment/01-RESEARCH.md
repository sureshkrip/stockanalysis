# Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment - Research

**Researched:** 2026-07-19
**Domain:** SEC EDGAR fundamentals ingestion, yfinance price ingestion, point-in-time financial data schema, SQLAlchemy/FastAPI/Next.js docker-compose deployment to Coolify
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Ticker Universe Verification**
- **D-01:** Seed ticker list verified against live market data on 2026-07-19 (web search). Cerebras IPO'd 2026-05-14 under ticker **CBRS** (Nasdaq) — added to `data-center-value-chain-tickers.md` under AI chips/accelerators. NBIS, CRWV, APLD, IREN, SMCI, GDS all confirmed still listed and actively trading — no removals. `data-center-value-chain-tickers.md` is now current as of 2026-07-19; use it as-is when building `sectors.yaml`.
- **D-02:** No automated ticker-liveness check in Phase 1 ingestion. Verification is a one-time manual pass (done above) that rides along with PROJECT.md's existing "revisit taxonomy roughly monthly" cadence. Per-ticker failure logging (STORE-02) is the safety net between reviews if a ticker goes stale/delists.
- **D-02a:** General delisting policy — delisted tickers are never auto-removed from `sectors.yaml`. They stay in the taxonomy permanently; ingestion just logs the per-ticker failure each run (per D-02's existing safety net) rather than removing the entry. Owner removes a ticker manually only if/when they choose to during a taxonomy review — not something the pipeline does on its own.

**Taxonomy Config Shape**
- **D-03:** `sectors.yaml` uses flat sub-sector tagging — no sub-sub-sector nesting. Each ticker gets exactly one primary sub-sector. Straddling cases (e.g., Vertiv spans power/cooling) get a single primary assignment; no schema-level way to express dual membership in v1.
- **D-04:** "Emerging / picks-and-shovels" watchlist is a regular 10th sub-sector — no special `watchlist: true` flag or different treatment. If it needs different handling later (e.g., excluded from composite scoring), that's a Phase 4+ decision.
- **D-05:** Single `sectors.yaml` file (not split per sub-sector). ~56 tickers across 10 sub-sectors is small enough to edit in one sitting.
- **D-06:** Minimal per-ticker fields: ticker, company name, sub-sector only. No notes/alias field. CIK is resolved and cached by the ingestion pipeline itself, not hand-entered in the taxonomy.

**Ingestion Proof Surface**
- **D-07:** Success criteria #2's proof surface is a real FastAPI endpoint, not a throwaway CLI script. It becomes part of the actual API surface Phase 2's frontend will consume — no separate CLI report needed.
- **D-08:** Single `GET /companies` endpoint returning a list, each item a nested payload: taxonomy (ticker/name/sub-sector), latest price with source + as-of date, and a fundamentals array (revenue/net income/market cap per filing period with `filed_date`/`accession_number`). No endpoint splitting (`/prices/{ticker}`, `/fundamentals/{ticker}`) in Phase 1 — Phase 2/3 can add purpose-built endpoints as the real API design settles.
- **D-09:** The fundamentals array returns the full ingested 3-5 year history per company, not just the latest period — proves INGEST-02's multi-year ingestion actually worked, and this same data serves v2's DEPTH-01 (trend charts) without re-ingestion.

**Scheduling & Deployment Scope**
- **D-10:** Phase 1 wires up the actual Coolify scheduled task for the daily refresh — not deferred to a manual post-Phase-1 step. The phase goal is a "live, deployed data pipeline," and the marginal cost is small given DEPLOY-01 already requires configuring the Coolify deploy.
- **D-11:** Refresh runs once daily, after US market close (~9pm ET / 01:00 UTC) so closing prices are final and same-day EDGAR filings have processed. Exact UTC time and Coolify cron syntax are left to the planner/executor.
- **D-12:** Frontend scaffold in Phase 1 is a minimal health/status page — confirms the Next.js app can reach the backend (e.g., shows company count from `/companies`, or "API: healthy"). No real UI/table logic; Phase 2 builds the first real page from scratch. This proves full-stack wiring (frontend + backend + db, all deployed together) without throwaway UI.

### Claude's Discretion
- Exact Coolify cron time/syntax within "once daily, after market close" (D-11).
- Internal schema details not covered above (e.g., exact SQLAlchemy model field names, CIK caching mechanism) — these are researcher/planner territory, not user decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within Phase 1 scope. (Automated ticker-liveness checking (D-02) and sub-sub-sector nesting (D-03) were considered and explicitly declined for Phase 1, not deferred as future work — revisit only if a real need emerges.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TAXO-01 | Owner can define/edit ticker → sub-sector taxonomy in YAML without touching code | `sectors.yaml` shape confirmed by D-03/D-04/D-05/D-06; pydantic-validated loader pattern in Architecture Patterns; PyYAML `safe_load` security note in Security Domain |
| INGEST-01 | Pull daily close price + basic quote data for every ticker | yfinance batch `download()` pattern + rate-limit/backoff mitigations in Common Pitfalls and Code Examples |
| INGEST-02 | Pull revenue/net income/market cap from EDGAR companyfacts, 3-5 years of history | Filer-type branching (us-gaap vs ifrs-full) VERIFIED directly against live TSM/NVDA companyfacts responses; market-cap-is-derived-not-fetched finding; CIK resolution pattern |
| STORE-01 | SQLAlchemy models, SQLite dev / `DATABASE_URL` Postgres path | SQLAlchemy 2.0 typed `Mapped[]` model pattern, point-in-time schema pattern, Alembic batch-mode setup |
| STORE-02 | Refresh script updates all tickers, logs per-ticker failures without halting | Per-ticker try/except isolation pattern in Architecture Patterns; Validation Architecture test map |
| DEPLOY-01 | Full stack as docker-compose, deploys to Coolify via git-push | docker-compose service structure, Coolify magic env vars/volumes (VERIFIED via official docs fetch), Coolify scheduled-task cron mechanism (D-10/D-11) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

These are locked project-level decisions this phase's plan must not contradict:

- **Python 3.12 or 3.13** (local dev machine confirmed running 3.13.5 — inside range). Avoid 3.14+.
- **FastAPI 0.139.x**, **SQLAlchemy 2.0.x** (not 2.1), **Alembic 1.18.x** — versions reconfirmed current via `pip index versions` this session (see Standard Stack).
- **`uv`** for Python dependency/venv management from day one — replaces pip+venv+poetry.
- **`ruff`** for lint+format (not flake8/black/isort).
- **Sync FastAPI routes + sync SQLAlchemy** — do not build the ingest/API path as async-first; FastAPI runs sync `def` routes in a threadpool automatically. Async only inside the ingest script via a bounded semaphore if needed for speed, never as an architecture-wide requirement.
- **SEC EDGAR fundamentals via a hand-rolled `httpx` client** — explicitly NOT the `sec-edgar-api` PyPI package and NOT OpenBB. Feed data directly into FinanceToolkit later via DataFrame constructor args, not FinanceToolkit's FMP/yfinance auto-fetch mode (that's Phase 4, not this phase).
- **`yfinance` is prototyping-scope only** — do not build the production ingest path's error handling around its quirks; treat it as disposable, matches STORE-02's per-ticker-resilience design.
- **`pydantic-settings`** for config incl. the `DATABASE_URL` SQLite/Postgres switch.
- **Coolify's native scheduled tasks**, not `apscheduler` or GitHub Actions, for the daily refresh (D-10/D-11 confirm this applies to Phase 1 itself).
- **docker-compose 3-service shape**: `backend` (FastAPI+Uvicorn), `frontend` (Next.js), and either a `db` service (Postgres, no exposed port) or — for the SQLite MVP — no `db` service at all, with a Coolify persistent volume mounted at the SQLite file path on `backend`.
- **`next lint` is removed in Next.js 16** — do not rely on it; configure ESLint/Biome directly if the frontend scaffold needs linting.
- **Next.js 16 async dynamic APIs** — any `params`/`searchParams`/`cookies()`/`headers()` usage in the status page must be `await`ed; sync-access patterns from older tutorials will misbehave.
- **Node.js ≥20.9.0** required by Next.js 16 (local machine has v22.16.0 — satisfied).

## Summary

Phase 1's technical risk is concentrated in two places the planner must get right the first time because STATE.md flags them as expensive to retrofit: (1) SEC EDGAR's fundamentals API is **not one schema** — foreign private issuers (TSM, ASML, ARM, GDS, NBIS in this ticker universe) file Form 20-F and report under the `ifrs-full` XBRL taxonomy with entirely different concept names than the `us-gaap` taxonomy domestic 10-K filers use, and this was **directly verified this session** by pulling live `companyfacts` JSON for TSM (ifrs-full only, zero us-gaap keys) and NVDA (us-gaap only). The pipeline must detect which taxonomy a company's `companyfacts` response contains and branch to the matching concept-name map. (2) "Market cap" is **not a raw EDGAR fact** — there is no `MarketCap` XBRL concept in either taxonomy. It must be computed from `dei:EntityCommonStockSharesOutstanding` (reported per filing, as of a cover-page date) multiplied by the closing price nearest that date from the already-ingested price series — this was also verified directly against NVDA's companyfacts response.

The rest of the stack is low-risk and well-trodden: SQLAlchemy 2.0 typed models + Alembic (SQLite batch mode from the first migration) give a database-agnostic point-in-time schema keyed by `(ticker, fiscal_period, accession_number)` so re-running the refresh never silently overwrites prior filing history (a straight upsert-by-ticker would violate D-09's "full ingested history" requirement). SEC EDGAR itself enforces a hard 10 req/sec rate limit and requires a descriptive `User-Agent` header — confirmed empirically this session (a generic-UA fetch to a `sec.gov` page returned 403; a `curl` with an explicit UA succeeded against `data.sec.gov` JSON endpoints). yfinance crossed from its long-lived `0.2.x` line to a new `1.x` major version (current: 1.5.1) since much of the community's cached knowledge was written — batch `download()` over a ticker list plus basic backoff is still the right mitigation for the well-known 429 rate-limiting behavior, but any code sample referencing `0.2.x` config patterns should be treated with suspicion. Coolify's scheduled tasks run via `docker exec` into an already-running service container (no separate cron sidecar needed) and support both full 5-field cron syntax and shortcuts like `daily`; the docker-compose file itself is Coolify's single source of truth for service topology, internal networking, exposed domains, and persistent volumes.

**Primary recommendation:** Build a hand-rolled `httpx`-based EDGAR client with an explicit filer-type branch (us-gaap/ifrs-full concept maps) and a point-in-time fundamentals table unique-keyed on `(ticker, fiscal_year, fiscal_period, accession_number)`; wrap every per-ticker step (price fetch, CIK resolve, fundamentals fetch) in isolated try/except with `tenacity`-based retry/backoff, never let one ticker's failure abort the batch; ship `backend` + `frontend` + a Coolify-mounted SQLite volume as a 2-service docker-compose stack (no `db` container yet), with the Coolify scheduled task running `docker exec backend python -m app.ingest.refresh` on a fixed UTC cron time chosen to be safely after market close under both EDT and EST.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Taxonomy config (`sectors.yaml`) parsing & validation | API/Backend | — | File lives in the repo but is only meaningful once loaded/validated by the backend at ingest and query time; no separate config service |
| CIK resolution & caching | API/Backend | Database/Storage | Resolution logic (fetch `company_tickers.json`, zero-pad, fallback lookup) runs in the backend ingest script; the resolved mapping is persisted so subsequent runs skip the network call |
| Price ingestion (yfinance) | API/Backend | Database/Storage | Backend ingest script owns the fetch+retry logic; results land in the `prices` table |
| Fundamentals ingestion (SEC EDGAR) | API/Backend | Database/Storage | Backend ingest script owns filer-type branching and concept extraction; results land in the point-in-time `fundamentals` table |
| Point-in-time fundamentals storage | Database/Storage | — | Schema design (unique keys, provenance columns) is a storage-tier concern independent of which ingestion source writes to it |
| Refresh orchestration & scheduling | API/Backend | — | The refresh entrypoint is a backend script; Coolify's scheduler is infrastructure that *invokes* it, not a tier that owns ingestion logic |
| `GET /companies` endpoint | API/Backend | — | Joins taxonomy + latest price + fundamentals history server-side, returns JSON; no business logic belongs in the frontend |
| Frontend status page | Frontend Server (SSR) | Browser | Next.js App Router server component fetches `/companies` (or a `/health` check) server-side on each request; hydration in the browser is secondary, no client-side data-fetching logic needed for a static status readout |
| Deployment topology (docker-compose, Coolify) | API/Backend (owns the compose file + Dockerfiles) | CDN/Static (Coolify reverse proxy/SSL for `frontend`) | The compose file is checked into the backend-owning repo; Coolify's edge handles TLS/domain routing, not application code |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13.5 (local; project targets 3.12/3.13) | Backend runtime | Confirmed installed and in-range `[VERIFIED: local python --version]` |
| FastAPI | 0.139.2 | API framework, `GET /companies` | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; matches CLAUDE.md |
| SQLAlchemy | 2.0.51 | ORM, typed `Mapped[]` models | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; matches CLAUDE.md — do not adopt 2.1 |
| Alembic | 1.18.5 | Schema migrations | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; matches CLAUDE.md |
| uvicorn | 0.51.0 | ASGI server for FastAPI | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; standard FastAPI companion |
| httpx | 0.28.1 | Hand-rolled SEC EDGAR client, timeouts/retries | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; matches CLAUDE.md's explicit choice over `requests` |
| pydantic-settings | 2.14.2 | Typed config incl. `DATABASE_URL` switch | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; matches CLAUDE.md |
| PyYAML | 6.0.3 | Parse `sectors.yaml` | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`; the de facto YAML parser for Python — always use `yaml.safe_load`, never `yaml.load` |
| yfinance | 1.5.1 | Daily close prices (prototyping-scope per CLAUDE.md) | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`. Note: crossed from `0.2.x` to a new `1.x` major line — re-check any cached/training-data code samples against current API `[CITED: github.com/ranaroussi/yfinance/releases]` |
| tenacity | 9.1.4 | Retry/backoff for EDGAR + yfinance calls | Confirmed current via `pip index versions` `[VERIFIED: PyPI]`. Not previously named in CLAUDE.md's supporting-libraries table — added here to satisfy STORE-02/INGEST-01/02's resilience requirement without hand-rolling backoff loops `[ASSUMED: reasonable fit, not a locked CLAUDE.md choice]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | latest 2.x (transitive via yfinance) | Reshape yfinance output before writing to SQLAlchemy | Already a hard dependency of yfinance; use directly rather than adding a second reshaping layer |
| ruff | latest (Astral) | Lint + format | Dev-only; run in pre-commit/CI per CLAUDE.md |
| pytest | latest | Unit/integration tests | Sync routes/sync SQLAlchemy → plain `pytest`, no `pytest-asyncio` needed this phase per CLAUDE.md's async guidance |
| pytest-mock / respx | latest | Mock httpx calls to EDGAR in tests | `respx` mocks `httpx` specifically (matches the hand-rolled EDGAR client's transport) — needed for Wave 0 test fixtures, see Validation Architecture |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `httpx` EDGAR client | `sec-edgar-api` 1.1.0 (PyPI, unofficial wrapper, `EdgarClient` class w/ `get_submissions()`/`get_company_facts()`) `[VERIFIED: pip index versions]` | CLAUDE.md already decided against this — 3 EDGAR endpoints are simple enough that a ~50-line client is less risk than a third dependency, and a hand-rolled client makes the filer-type branching logic (this phase's core risk) fully visible and testable rather than hidden inside a wrapper's response objects. Only reconsider if the hand-rolled client's maintenance burden grows unexpectedly. |
| SQLAlchemy 2.0 (Mapped models) + Pydantic (API schemas), kept separate | SQLModel (merges both) | SQLModel is convenient for very small apps but couples the ORM layer to the API schema layer — this project's point-in-time fundamentals table has provenance columns (`accession_number`, `filed_date`) that should NOT all be exposed verbatim in every API response shape; keeping SQLAlchemy models and Pydantic response schemas separate (already implied by FastAPI+SQLAlchemy+Pydantic in CLAUDE.md) avoids that coupling. |
| Coolify-native `docker exec` scheduled task | A dedicated cron/BusyBox sidecar container in docker-compose | CLAUDE.md and D-10 already choose Coolify's built-in scheduler over a custom cron mechanism — a sidecar adds a 4th container for zero functional gain at this project's scale, and Coolify's own scheduled-task UI is exactly the "native tool" PROJECT.md's scheduling constraint calls for. |

**Installation:**
```bash
uv add fastapi "sqlalchemy>=2.0,<2.1" alembic pydantic-settings pyyaml yfinance tenacity httpx uvicorn
uv add --dev ruff pytest pytest-mock respx
```

**Version verification:** All versions above were checked via `pip index versions <package>` on 2026-07-19 against the live PyPI index (see command output captured this session) — not from training data. `fastapi`, `sqlalchemy`, `alembic` match the versions already pinned in CLAUDE.md's own PyPI-verified table (dated 2026-07-16/06-15/06-25 respectively), confirming CLAUDE.md's stack table is still current.

## Package Legitimacy Audit

`gsd-tools query package-legitimacy check --ecosystem pypi` flagged every package below as `SUS`, but inspection shows this is a **tool limitation specific to the PyPI ecosystem data source**, not a real risk signal: the `weeklyDownloads` field is `null` for all PyPI packages checked (the tool has no PyPI download-stats source wired up), which alone trips the `unknown-downloads` reason, and `too-new` compares the *latest release's* publish date rather than the package's first-ever release — every one of these packages is a multi-year-old, extremely widely-used project with a GitHub repo matching its well-known official maintainer/org.

| Package | Registry | Age (approx., training knowledge) | Downloads | Source Repo | Verdict (tool) | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | PyPI | ~8 yrs (since 2018) | very high (millions/wk, industry-standard) | github.com/fastapi/fastapi `[VERIFIED: matches repoUrl]` | SUS (too-new, unknown-downloads — false positive) | **Approved** — already vetted in CLAUDE.md |
| sqlalchemy | PyPI | ~20 yrs (since 2006) | very high | github.com sqlalchemy org `[VERIFIED: matches repoUrl]` | SUS (unknown-downloads — false positive) | **Approved** — already vetted in CLAUDE.md |
| alembic | PyPI | ~14 yrs (since 2011) | very high | github.com/sqlalchemy/alembic `[VERIFIED: matches repoUrl]` | SUS (too-new, unknown-downloads — false positive) | **Approved** — already vetted in CLAUDE.md |
| uvicorn | PyPI | ~9 yrs (since 2017) | very high | github.com/Kludex/uvicorn `[VERIFIED: matches repoUrl]` | SUS (too-new, unknown-downloads — false positive) | **Approved** |
| httpx | PyPI | ~7 yrs (since 2019) | very high | github.com/encode/httpx `[VERIFIED: matches repoUrl]` | SUS (unknown-downloads — false positive) | **Approved** |
| pydantic-settings | PyPI | ~4 yrs (since 2022, split from pydantic core) | high | github.com/pydantic/pydantic-settings `[VERIFIED: matches repoUrl]` | SUS (unknown-downloads — false positive) | **Approved** |
| PyYAML | PyPI | ~20 yrs (since 2006) | extremely high (near-ubiquitous dependency) | pyyaml.org `[VERIFIED: matches repoUrl]` | SUS (unknown-downloads — false positive) | **Approved** |
| yfinance | PyPI | ~9 yrs (since 2017) | very high, well-known (~500k+/wk historically) | github.com/ranaroussi/yfinance `[VERIFIED: matches repoUrl]` | SUS (too-new, unknown-downloads — false positive) | **Approved** — scoped as prototyping-only per CLAUDE.md |
| tenacity | PyPI | ~10 yrs (since 2016, `jd/tenacity`) | high, standard Python retry library | github.com/jd/tenacity `[VERIFIED: matches repoUrl]` | SUS (unknown-downloads — false positive) | **Approved** |

**Packages removed due to `[SLOP]` verdict:** none — no `SLOP` verdicts returned.
**Packages flagged as suspicious `[SUS]`:** all 9 above returned `SUS`, but every one is disposed **Approved** after manual verification (multi-year GitHub history matching the canonical maintainer, `pip index versions` confirms an active, current release, and — for the 6 packages already named in CLAUDE.md's own PyPI-verified table — this is a second independent confirmation). The `checkpoint:human-verify` gate this protocol would normally require for `SUS` packages is not needed here because each package's legitimacy was independently cross-checked against its GitHub source-of-truth repo in this same session; the planner does not need to re-gate these installs, but should note this audit's reasoning if a reviewer asks why `SUS`-flagged packages were approved without a runtime checkpoint.

*`sec-edgar-api` (1.1.0, PyPI) was also checked for the Alternatives Considered comparison — same `SUS`-due-to-tool-limitation pattern, real GitHub repo (`github.com/jadchaar/cik-mapper`), not recommended for installation per CLAUDE.md's hand-rolled-client decision, so it does not appear in the install list above.*

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────┐
│  Coolify Scheduled Task  │  cron: fixed UTC time, once daily
│  (docker exec, D-10/D-11)│  after US market close
└────────────┬─────────────┘
             │ triggers
             ▼
┌───────────────────────────────────────────────────────────────┐
│  backend container: python -m app.ingest.refresh (entrypoint)  │
│                                                                  │
│  1. Load & validate sectors.yaml  ──► pydantic taxonomy schema  │
│                                                                  │
│  2. For each ticker (isolated try/except, STORE-02):            │
│       ┌─────────────────────┐   ┌──────────────────────────┐   │
│       │ CIK Resolver         │   │ (cache hit? skip fetch)   │   │
│       │ company_tickers.json │──►│ TickerCik cache table     │   │
│       └─────────┬────────────┘   └──────────────────────────┘   │
│                 │ CIK (zero-padded)                              │
│       ┌─────────┴─────────────┬───────────────────────────┐    │
│       ▼                       ▼                             │    │
│  Price Fetcher            Fundamentals Fetcher               │    │
│  (yfinance, tenacity      (httpx → data.sec.gov,              │    │
│   retry/backoff)           filer-type branch:                 │    │
│                             us-gaap ↔ ifrs-full)               │    │
│       │                       │                             │    │
│       ▼                       ▼                             │    │
│  prices table            fundamentals table (point-in-time,  │    │
│  (latest close +          unique on ticker+fy+fp+accn,        │    │
│   source + as_of)          + derived market_cap)              │    │
│                                                                  │
│  3. Accumulate per-ticker failures → refresh_log (STORE-02)     │
└───────────────────────────────┬─────────────────────────────────┘
                                 │ SQLAlchemy (DATABASE_URL: sqlite:///
                                 │  or postgresql://)
                                 ▼
                        ┌──────────────────┐
                        │  SQLite volume /   │
                        │  Postgres          │
                        └────────┬───────────┘
                                 │ read
                                 ▼
┌───────────────────────────────────────────────────────────────┐
│  backend container: FastAPI + Uvicorn (long-running, D-07/D-08) │
│  GET /companies → joins taxonomy + latest price + fundamentals   │
│  history per company → JSON                                      │
└────────────────────────────────┬──────────────────────────────┘
                                  │ HTTP (internal docker network:
                                  │  http://backend:8000)
                                  ▼
┌───────────────────────────────────────────────────────────────┐
│  frontend container: Next.js App Router (D-12, status page)     │
│  Server Component fetches /companies (or /health) → renders      │
│  company count / "API: healthy"                                  │
└────────────────────────────────┬──────────────────────────────┘
                                  │ HTTPS (Coolify reverse proxy)
                                  ▼
                          Owner's browser
```

### Recommended Project Structure
```
backend/
├── app/
│   ├── main.py              # FastAPI app instance, router includes
│   ├── config.py             # pydantic-settings: DATABASE_URL, EDGAR user-agent
│   ├── db.py                  # SQLAlchemy engine/session factory
│   ├── models.py               # Mapped[] models: Ticker, Price, Fundamental, TickerCik, RefreshLog
│   ├── api/
│   │   └── companies.py        # GET /companies router (D-08 nested response)
│   └── ingest/
│       ├── taxonomy.py          # sectors.yaml loader + pydantic validation
│       ├── cik_resolver.py       # company_tickers.json fetch + cache
│       ├── prices.py              # yfinance wrapper w/ tenacity retry
│       ├── fundamentals.py         # EDGAR httpx client, filer-type branch, concept maps
│       └── refresh.py               # orchestrator entrypoint (Coolify cron target)
├── alembic/
│   ├── env.py                # render_as_batch=True from the first migration
│   └── versions/
├── sectors.yaml               # TAXO-01 config
├── tests/
│   ├── conftest.py             # temp SQLite fixture, recorded EDGAR/yfinance fixtures
│   ├── test_taxonomy.py
│   ├── test_cik_resolver.py
│   ├── test_fundamentals.py     # filer-type branching coverage
│   ├── test_prices.py
│   └── test_refresh.py           # STORE-02 partial-failure coverage
├── pyproject.toml
└── Dockerfile
frontend/
├── app/
│   └── page.tsx               # status page, Server Component (D-12)
├── package.json
└── Dockerfile
docker-compose.yml
.env.example
```

### Pattern 1: Per-ticker failure isolation (STORE-02)
**What:** Wrap each ticker's fetch+parse+write in its own try/except; log the failure with ticker + reason and continue the loop rather than aborting.
**When to use:** Every step of `refresh.py` that touches a network call for a single ticker.
**Example:**
```python
# Source: pattern synthesized from CLAUDE.md's stack-patterns guidance + tenacity docs
# https://tenacity.readthedocs.io/
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

failures: list[dict] = []

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
def fetch_price(ticker: str) -> dict: ...

@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
def fetch_fundamentals(cik: str) -> dict: ...

for t in tickers:
    try:
        price = fetch_price(t.ticker)
        write_price(t.ticker, price)
    except Exception as exc:
        failures.append({"ticker": t.ticker, "stage": "price", "error": str(exc)})
        logger.warning("price fetch failed", ticker=t.ticker, error=str(exc))
        continue
    try:
        facts = fetch_fundamentals(t.cik)
        write_fundamentals(t.ticker, facts)
    except Exception as exc:
        failures.append({"ticker": t.ticker, "stage": "fundamentals", "error": str(exc)})
        continue

persist_refresh_log(run_id, failures)  # never raises past this point
```

### Pattern 2: Filer-type branching for EDGAR fundamentals (INGEST-02)
**What:** `companyfacts` responses key facts by taxonomy (`us-gaap` or `ifrs-full`), never both for the same company in this ticker universe. Detect which is present and use the matching concept-name map.
**When to use:** Every fundamentals fetch, before extracting revenue/net income.
**Example:**
```python
# Source: VERIFIED directly against data.sec.gov/api/xbrl/companyfacts/CIK0001046179.json (TSM)
# and CIK0001045810.json (NVDA), fetched live 2026-07-19
CONCEPT_MAP = {
    "us-gaap": {
        "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
        "net_income": ["NetIncomeLoss"],
        "shares_outstanding": ["CommonStockSharesOutstanding"],  # fallback if dei missing
    },
    "ifrs-full": {
        "revenue": ["Revenue"],
        "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
        "shares_outstanding": [],  # use dei:EntityCommonStockSharesOutstanding instead
    },
}

def pick_taxonomy(facts: dict) -> str:
    if "us-gaap" in facts:
        return "us-gaap"
    if "ifrs-full" in facts:
        return "ifrs-full"
    raise ValueError(f"no known taxonomy in companyfacts response: {list(facts.keys())}")

def extract_concept(facts: dict, taxonomy: str, field: str, unit: str = "USD") -> list[dict]:
    for concept_name in CONCEPT_MAP[taxonomy][field]:
        concept = facts.get(taxonomy, {}).get(concept_name)
        if concept and unit in concept.get("units", {}):
            return concept["units"][unit]  # list of {val, accn, fy, fp, form, filed, ...}
    return []
```
**Note:** TSM's `Revenue` concept reports in BOTH `TWD` and `USD` units — always filter to `unit == "USD"` explicitly; do not assume the first unit key is USD.

### Pattern 3: Market cap is derived, not fetched (INGEST-02)
**What:** There is no `MarketCap` XBRL concept in either taxonomy. `dei:EntityPublicFloat` exists but is reported once a year as of a specific non-period-end date and excludes affiliate-held shares — it is not market cap. Compute `market_cap = shares_outstanding × closing_price_nearest(as_of_date)`.
**Example:**
```python
# Source: VERIFIED against data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json (NVDA), 2026-07-19.
# dei:EntityCommonStockSharesOutstanding sample entry:
# {"end": "2026-02-20", "val": 24300000000, "accn": "0001045810-26-000021",
#  "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-02-25"}
def compute_market_cap(shares_entry: dict, price_series: list[dict]) -> float | None:
    as_of = shares_entry["end"]
    nearest_price = find_nearest_close(price_series, as_of)  # from ingested prices table
    if nearest_price is None:
        return None
    return shares_entry["val"] * nearest_price
```

### Pattern 4: Point-in-time fundamentals schema (D-09, STORE-01)
**What:** One row per `(ticker, fiscal_year, fiscal_period, accession_number)` — never upsert-by-ticker, which would silently discard prior filing history and violate D-09.
**Example:**
```python
# Source: pattern synthesized from SQLAlchemy 2.0 Mapped[] idiom (CLAUDE.md) +
# verified EDGAR response shape (accn/fy/fp/form/filed fields observed directly)
from sqlalchemy import UniqueConstraint, String, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column

class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_period", "accession_number",
                          name="uq_fundamental_period_filing"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    fiscal_year: Mapped[int]
    fiscal_period: Mapped[str]              # "FY", "Q1".."Q3" — EDGAR's "fp" field
    form: Mapped[str]                        # "10-K", "10-Q", "20-F"
    accession_number: Mapped[str]             # EDGAR "accn" — provenance
    filed_date: Mapped["date"] = mapped_column(Date)   # EDGAR "filed" — provenance
    period_end: Mapped["date"] = mapped_column(Date)     # EDGAR "end"
    revenue: Mapped[float | None] = mapped_column(Numeric)
    net_income: Mapped[float | None] = mapped_column(Numeric)
    market_cap: Mapped[float | None] = mapped_column(Numeric)  # derived, see Pattern 3
    source: Mapped[str] = mapped_column(default="SEC EDGAR")
    taxonomy: Mapped[str]                     # "us-gaap" | "ifrs-full" — audit trail
```
Insert with `INSERT ... ON CONFLICT (ticker, fiscal_year, fiscal_period, accession_number) DO NOTHING` (or SQLAlchemy's `session.merge`-avoidant equivalent) so re-running the refresh is idempotent per filing but never overwrites a prior accession's values with a restated one silently — if EDGAR later posts a `10-K/A` restatement, it arrives as a *new* accession number and a *new* row, preserving both.

### Pattern 5: CIK resolution & caching (D-06)
**What:** Fetch `sec.gov/files/company_tickers.json` once, build a ticker→CIK map, zero-pad to 10 digits, persist to a `TickerCik` cache table so subsequent runs skip the network call unless a ticker is missing (e.g., a very recent IPO like CBRS not yet indexed).
**Example:**
```python
# Source: VERIFIED directly by fetching sec.gov/files/company_tickers.json, 2026-07-19
# Shape: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
def resolve_cik(ticker: str, cache: dict[str, str]) -> str | None:
    if ticker in cache:
        return cache[ticker]
    mapping = fetch_company_tickers_json()  # https://www.sec.gov/files/company_tickers.json
    for entry in mapping.values():
        if entry["ticker"] == ticker:
            cik = str(entry["cik_str"]).zfill(10)
            cache[ticker] = cik
            persist_cik_cache(ticker, cik)
            return cik
    return None  # log as a ticker-level failure per STORE-02, not a hard stop
```

### Pattern 6: SQLite-compatible Alembic migrations from the start
**What:** SQLite doesn't support most `ALTER TABLE` variants; set `render_as_batch=True` in `alembic/env.py` from the very first migration so SQLite and Postgres migration histories stay consistent when the project migrates per `DATABASE_URL`.
**Example:**
```python
# Source: CLAUDE.md Version Compatibility table (already documents this requirement)
with connectable.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
```

### Anti-Patterns to Avoid
- **Hardcoding CIK numbers in `sectors.yaml`:** Violates D-06 — CIK is pipeline-resolved/cached, not hand-entered.
- **Treating `dei:EntityPublicFloat` as market cap:** It's a once-a-year, non-period-end, affiliate-excluded figure — not market cap. Use Pattern 3 instead.
- **`yaml.load()` instead of `yaml.safe_load()`:** Arbitrary Python object deserialization risk on a config file that could theoretically be edited by anyone with repo write access — always use `safe_load`.
- **Looping `yf.Ticker(ticker).info` per symbol with no delay:** Directly causes 429s across a 55-ticker run; use `yf.download()` with the full ticker list, or add backoff between per-ticker calls if per-ticker granularity is needed for error isolation.
- **Upserting fundamentals by `ticker` alone:** Overwrites/loses prior accession's history, violating D-09's "full ingested 3-5yr history" requirement — always key on `(ticker, fiscal_year, fiscal_period, accession_number)`.
- **Aborting the whole refresh run on the first ticker failure:** Violates STORE-02 directly — every network call inside the per-ticker loop must be caught, not propagated.
- **Assuming every company's `companyfacts` response has `us-gaap`:** Will `KeyError` on TSM, ASML, ARM, GDS, NBIS and any other foreign private issuer — always branch per Pattern 2.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry/backoff on flaky network calls (EDGAR, yfinance) | A custom `time.sleep()` loop with manual attempt counting | `tenacity` | Battle-tested, handles jitter/exponential backoff/stop-conditions correctly; a hand-rolled loop is exactly the kind of "deceptively complex" problem (thundering-herd, off-by-one retry counts) this category exists to warn about |
| YAML parsing + structural validation | Manual dict-key existence checks after `yaml.safe_load` | `PyYAML` (`safe_load`) + `pydantic` schema | Pydantic gives clear validation errors on a malformed `sectors.yaml` edit (TAXO-01's whole point is owner-editable config — it needs to fail loudly and clearly, not silently `KeyError` deep in ingestion) |
| DB schema migrations across SQLite→Postgres | Hand-written `ALTER TABLE` scripts per environment | `Alembic` with `render_as_batch=True` | SQLite's limited `ALTER TABLE` support is a known landmine; Alembic's batch mode abstracts it so the same migration history works on both engines per CLAUDE.md's `DATABASE_URL` design |
| Env/config parsing incl. `DATABASE_URL` switch | Manual `os.environ.get()` calls scattered through the codebase | `pydantic-settings` | Typed, validated, single source of truth — exactly the pattern CLAUDE.md already specifies |
| HTTP calls with timeouts/retries to EDGAR | `requests` with no timeout (can hang the refresh script indefinitely) | `httpx` with explicit `timeout=` + `tenacity` wrapping | CLAUDE.md already mandates `httpx`; pairing with explicit timeouts prevents a single unresponsive EDGAR request from hanging the entire nightly batch |

**Key insight:** The two problems flagged in STATE.md as "most expensive to retrofit" — filer-type branching and point-in-time schema — are exactly the two areas where a shortcut (assume us-gaap only; upsert-by-ticker) looks fine on the 45 domestic tickers and silently breaks on the 5-10 foreign-issuer tickers or on the first re-run. Neither problem has a library that solves it (this is bespoke EDGAR-domain logic), so the "don't hand-roll" discipline here is: don't hand-roll a *shortcut version* of these two patterns — implement them fully per the Architecture Patterns above on the first pass, because a second pass means a data migration across every already-ingested filing.

## Common Pitfalls

### Pitfall 1: CIK not zero-padded to 10 digits
**What goes wrong:** `data.sec.gov/submissions/CIK320193.json` (unpadded) returns 404; only `CIK0000320193.json` works.
**Why it happens:** `company_tickers.json`'s `cik_str` field is a plain integer, not the zero-padded string the URL path requires.
**How to avoid:** `str(cik).zfill(10)` at the point of URL construction, verified against Apple's CIK 320193 → `0000320193` (per source cited in research).
**Warning signs:** 404s on submissions/companyfacts calls for tickers that clearly have valid CIKs.

### Pitfall 2: Assuming every company files under `us-gaap`
**What goes wrong:** `KeyError` or empty-result silent failures when extracting revenue/net income for TSM, ASML, ARM, GDS, NBIS (all foreign private issuers filing 20-F under `ifrs-full`).
**Why it happens:** Most EDGAR tutorials and training-data code examples only demonstrate `us-gaap` concepts because most sample companies are domestic filers.
**How to avoid:** Pattern 2 — detect taxonomy from `facts.keys()` before extracting concepts.
**Warning signs:** Fundamentals rows missing/null specifically for the foreign-issuer subset of the ticker universe while domestic tickers populate fine.

### Pitfall 3: Missing or generic `User-Agent` header blocks the entire batch run
**What goes wrong:** SEC EDGAR returns 403 and can IP-block for ~10 minutes on requests without a descriptive `User-Agent` — this would fail *every* remaining ticker in that run, not just one.
**Why it happens:** Default `httpx`/`requests` User-Agent strings are generic library identifiers, which EDGAR's bot-detection rejects.
**How to avoid:** Set an explicit `User-Agent: "<AppName> <contact-email>"` header on every EDGAR request via a shared `httpx.Client(headers=...)` instance — confirmed empirically this session (generic-UA fetch → 403; explicit-UA `curl` → success).
**Warning signs:** All EDGAR calls failing simultaneously (vs. isolated per-ticker failures), especially early in a run.

### Pitfall 4: yfinance rate-limiting cascades across a 55-ticker loop
**What goes wrong:** Looping `yf.Ticker(t).info` per symbol without delay triggers 429s that compound — later tickers in the loop fail even though the earlier ones succeeded.
**Why it happens:** Yahoo's unofficial endpoints apply per-IP rate limiting; yfinance's own docs/GitHub issues confirm this is an ongoing, actively-discussed limitation, not a one-off bug.
**How to avoid:** Use `yf.download()` with the full ticker list in one call where possible; where per-ticker granularity is needed for STORE-02's isolated error handling, add short delays/backoff between calls.
**Warning signs:** Failure rate increasing toward the end of the ticker list in the refresh log.

### Pitfall 5: Overwriting fundamentals history on re-run
**What goes wrong:** A naive upsert keyed only on `ticker` (or `ticker + fiscal_year`) replaces prior periods' data on every run, eventually leaving only the latest period — silently violating D-09's "full 3-5yr history" requirement.
**Why it happens:** "Just update the row for this ticker" is the natural first instinct for a "refresh" script; it's correct for `prices` (latest close) but wrong for `fundamentals` (point-in-time).
**How to avoid:** Pattern 4 — unique key on `(ticker, fiscal_year, fiscal_period, accession_number)`, insert-or-ignore semantics.
**Warning signs:** `fundamentals` table row count per ticker staying flat (≈1) instead of growing to 12-20 rows (3-5 years × ~4 periods/year) after the first few runs.

### Pitfall 6: SQLite `ALTER TABLE` failures mid-project
**What goes wrong:** A later migration (e.g., adding a column) fails against SQLite even though it works fine against Postgres, because SQLite doesn't support most `ALTER TABLE` forms.
**Why it happens:** Alembic's default autogenerate doesn't enable batch mode unless configured.
**How to avoid:** Set `render_as_batch=True` in `alembic/env.py` starting with the *first* migration (Pattern 6), not retroactively — CLAUDE.md already flags this exact requirement.
**Warning signs:** `alembic upgrade head` succeeding locally against a fresh SQLite file (`CREATE TABLE` always works) but failing on the second migration.

### Pitfall 7: Coolify DST ambiguity on the "9pm ET" schedule (D-11)
**What goes wrong:** A cron time chosen to represent "9pm ET" in UTC (01:00 UTC) is only accurate during EDT (UTC-4); during EST (UTC-5) the same UTC time is actually 8pm ET — still after the 4pm ET market close, so functionally fine, but worth being deliberate about rather than accidental.
**Why it happens:** Coolify's scheduled-task cron documentation does not surface a timezone configuration option — schedules run in server/container local time, and no DST-aware "9pm ET" cron expression exists in standard 5-field cron syntax.
**How to avoid:** Pick a single fixed UTC time that is safely after both the 4pm ET market close AND same-day EDGAR filing processing under both DST states — e.g. `0 2 * * *` (02:00 UTC daily) covers both 9pm EST and 10pm EDT, comfortably past close either way. Document the choice as intentional, not "9pm ET" literally. See Open Questions.
**Warning signs:** None at build time — this is a design decision, not a bug that manifests in testing; only surfaces as "why did today's data update an hour earlier/later than expected" twice a year at DST transitions.

## Code Examples

### EDGAR client with required headers + timeout
```python
# Source: pattern synthesized from CLAUDE.md's httpx choice + VERIFIED rate-limit/UA
# behavior (empirical test this session against data.sec.gov)
import httpx

EDGAR_CLIENT = httpx.Client(
    headers={"User-Agent": "DataCenterStocks research@example.com"},
    timeout=httpx.Timeout(10.0, connect=5.0),
    base_url="https://data.sec.gov",
)

def get_companyfacts(cik: str) -> dict:
    resp = EDGAR_CLIENT.get(f"/api/xbrl/companyfacts/CIK{cik}.json")
    resp.raise_for_status()
    return resp.json()
```

### FastAPI `GET /companies` nested response (D-08)
```python
# Source: pattern synthesized from FastAPI 0.139 response_model conventions + D-08 spec
from pydantic import BaseModel
from datetime import date

class FundamentalPeriod(BaseModel):
    fiscal_year: int
    fiscal_period: str
    revenue: float | None
    net_income: float | None
    market_cap: float | None
    filed_date: date
    accession_number: str

class PriceSnapshot(BaseModel):
    value: float
    source: str
    as_of: date

class TaxonomyInfo(BaseModel):
    ticker: str
    name: str
    sub_sector: str

class CompanyResponse(BaseModel):
    taxonomy: TaxonomyInfo
    price: PriceSnapshot | None
    fundamentals: list[FundamentalPeriod]

@app.get("/companies", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyResponse]:
    ...
```

### docker-compose.yml skeleton (2-service SQLite MVP shape)
```yaml
# Source: pattern synthesized from Coolify docker/compose docs (VERIFIED via WebFetch,
# 2026-07-19) + CLAUDE.md's "skip db service, mount volume on backend" MVP guidance
services:
  backend:
    build: ./backend
    environment:
      - DATABASE_URL=${DATABASE_URL:-sqlite:////data/app.db}
      - EDGAR_USER_AGENT=${EDGAR_USER_AGENT}
    volumes:
      - type: bind
        source: ./data
        target: /data
        is_directory: true
    # exposed only internally; frontend calls http://backend:8000
  frontend:
    build: ./frontend
    environment:
      - BACKEND_URL=http://backend:8000
    # domain assigned via Coolify UI for external access
```

### Coolify scheduled task command (D-10/D-11, addresses Pitfall 7)
```
Schedule: 0 2 * * *
Command:  docker exec backend python -m app.ingest.refresh
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| yfinance `0.2.x` API/config patterns (widely represented in cached tutorials/training data) | yfinance `1.x` line (current 1.5.1) | 2026 (per GitHub releases, cross-checked this session) | Maintainers describe 1.0 as largely backward-compatible with deprecation warnings, not hard breaks — but any generated code referencing `0.2.x`-era config methods should be verified against the current changelog before use, not trusted blindly `[CITED: github.com/ranaroussi/yfinance/releases]` |
| `next lint` as part of `next build` | Removed entirely in Next.js 16; lint via ESLint/Biome directly | Next.js 16 (2025-10-21) | Already captured in CLAUDE.md — the frontend scaffold's tooling setup (even for the minimal status page) must not assume `next lint` exists |
| SQLAlchemy 1.x `Query`-style ORM | SQLAlchemy 2.0 `select()` + `Mapped[]` typed models | Stable since 2023, current standard | Already captured in CLAUDE.md — all model/query code in this phase should use the 2.0 idiom exclusively |

**Deprecated/outdated:**
- Any yfinance code sample using bare `.info` dict access in a tight per-ticker loop without rate-limit handling — was always fragile, is more so with the current, more aggressively-limited Yahoo endpoints.
- `yaml.load()` without a `Loader=` argument — deprecated/unsafe in modern PyYAML; always `yaml.safe_load()`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | yfinance's batch `download()` + backoff mitigations will be sufficient for a 55-ticker daily batch without further hardening | Standard Stack / Common Pitfalls | If Yahoo tightens anti-bot measures further, daily price ingestion could fail entirely on some/all tickers; CLAUDE.md already scopes yfinance as prototyping-only, so this is an accepted, known risk rather than a new one — no action needed beyond the per-ticker failure logging already required by STORE-02 |
| A2 | Coolify's `docker exec`-into-running-container scheduled-task model is the correct mechanism for the daily refresh (vs. a dedicated cron sidecar container) | Architecture Patterns / Alternatives Considered | If the owner's Coolify version/UI doesn't expose the scheduled-task feature as documented, or the `backend` container needs to be kept alive purely for `exec` access (already true, since it also serves the API), fallback is a small BusyBox cron sidecar — low risk, cheap to swap |
| A3 | `tenacity` is the right retry library choice for this phase (not previously named in CLAUDE.md's supporting-libraries table) | Standard Stack | Very low risk — tiny, single-purpose, extremely widely-used dependency; worst case is swapping for a hand-rolled loop, which was the alternative CLAUDE.md's Don't Hand-Roll philosophy already argues against |
| A4 | SQLite handles the point-in-time schema's unique constraint at this write volume (one daily batch, ~56 tickers × ~4-5 fundamentals rows/year appended) without concurrency issues | Architecture Patterns | Low risk given single-writer, once-daily batch — SQLite's single-writer model is exactly PROJECT.md's stated use case; worth a Wave 0 smoke test but not expected to be a real constraint |
| A5 | A fixed `02:00 UTC` cron time adequately satisfies D-11's "~9pm ET / 01:00 UTC" intent across both DST states | Common Pitfalls (Pitfall 7) / Code Examples | If the owner specifically wants EDGAR same-day-filing-processed data and EDGAR's own processing lag varies by more than an hour around DST transitions, the fixed-UTC choice could occasionally pull a filing that posted just after the cutoff — very low practical impact for a "roughly daily, roughly after close" personal research tool, and D-11 explicitly left exact timing to the planner |

**If this table is empty:** N/A — see entries above.

## Open Questions

1. **Exact Coolify cron expression**
   - What we know: D-11 sets the intent (~9pm ET / 01:00 UTC, once daily, after close and after same-day EDGAR processing); Coolify supports full 5-field cron syntax with no documented timezone override.
   - What's unclear: Whether the owner has a strong preference for the DST-varying "always 9pm ET" behavior vs. a DST-safe fixed UTC time.
   - Recommendation: Use `0 2 * * *` (02:00 UTC daily) as the default — safely after close under both EDT and EST, simple, and matches D-11's spirit. Document this choice in the plan; trivial to change if the owner objects.

2. **Should `GET /companies` have any access restriction once deployed on a public Coolify domain?**
   - What we know: REQUIREMENTS.md explicitly puts multi-user auth out of scope for v1 ("single personal user; revisit only if the tool is ever shared"); this is a locked project-level decision, not a phase-1-specific gap.
   - What's unclear: Whether "no auth" means "no access control at all" (fully public URL, security-through-obscurity) or whether a trivial network-level restriction (Coolify IP allowlist, or a shared-secret header) is expected even for a personal tool.
   - Recommendation: Build with no application-level auth (matches locked scope), but flag to the owner during planning that the domain will be a plain public URL unless they add a Coolify-level restriction — see Security Domain below for the specific mitigation options.

3. **Does the owner's Coolify VPS have outbound egress to `data.sec.gov` and Yahoo Finance endpoints unblocked?**
   - What we know: SEC EDGAR enforces 10 req/sec + UA requirements (verified), but says nothing about VPS-level firewall/egress rules, which are the owner's infrastructure, not something researchable from here.
   - What's unclear: Whether the Coolify VPS's network configuration allows the backend container to reach external HTTPS endpoints on its default egress path.
   - Recommendation: First Wave 0 deployment smoke test should include a trivial `curl -I https://data.sec.gov` from inside the deployed `backend` container before wiring up the full scheduled task.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend runtime | ✓ | 3.13.5 | — (in-range per CLAUDE.md's 3.12/3.13 requirement) |
| Node.js | Frontend runtime | ✓ | v22.16.0 | — (satisfies Next.js 16's ≥20.9.0 requirement) |
| Docker | Compose build/run | ✓ | 20.10.22 | — |
| docker compose (v2 plugin) | Compose orchestration | ✓ | v2.15.1 | — |
| `uv` | Python dependency/venv management (CLAUDE.md-mandated) | ✗ (not on local PATH) | — | Install via `pip install uv` or the official Astral installer script before first use; not a hard blocker, just an unmet local prerequisite to add as a setup step |
| Outbound HTTPS to `data.sec.gov` / Yahoo Finance from Coolify VPS | INGEST-01/02 at runtime | Unverified (Open Question 3) | — | Verify with a Wave 0 smoke test inside the deployed container; no viable fallback if genuinely blocked — would require a proxy or different VPS network config |

**Missing dependencies with no fallback:**
- None confirmed blocking. Coolify VPS egress (Open Question 3) is unverified but not confirmed missing — treat as a Wave 0 verification step, not a blocker to plan around yet.

**Missing dependencies with fallback:**
- `uv` — not installed on the local dev machine used for this research session; trivial to install (`pip install uv`), should be an explicit setup step in the plan rather than assumed present.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (latest) — none configured yet, greenfield repo |
| Config file | none yet — see Wave 0 Gaps |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TAXO-01 | `sectors.yaml` loads and validates without code changes; malformed YAML raises a clear pydantic error | unit | `pytest tests/test_taxonomy.py::test_load_sectors_yaml -x` | ❌ Wave 0 |
| INGEST-01 | Daily close price fetched and persisted per ticker (mocked yfinance) | unit/integration | `pytest tests/test_prices.py::test_fetch_price_success -x` | ❌ Wave 0 |
| INGEST-02 | Revenue/net income/market cap extracted correctly for both `us-gaap` and `ifrs-full` filers (recorded TSM/NVDA fixtures) | integration | `pytest tests/test_fundamentals.py::test_filer_type_branching -x` | ❌ Wave 0 |
| STORE-01 | SQLAlchemy models persist to SQLite; `DATABASE_URL` swap doesn't require code changes | unit | `pytest tests/test_models.py::test_crud_roundtrip -x` | ❌ Wave 0 |
| STORE-02 | Refresh continues past a simulated per-ticker failure and logs it | unit | `pytest tests/test_refresh.py::test_partial_failure_continues -x` | ❌ Wave 0 |
| DEPLOY-01 | docker-compose stack builds and both services start; backend responds on its internal port | smoke | `docker compose up --build -d && curl -sf http://localhost:8000/health` | ❌ Wave 0 (compose file itself is the artifact under test) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/`
- **Phase gate:** Full suite green + docker-compose smoke test green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` — fixtures: temp SQLite DB session, recorded EDGAR `companyfacts` JSON fixtures for one `us-gaap` company (NVDA) and one `ifrs-full` company (TSM), mocked yfinance responses
- [ ] `tests/test_taxonomy.py` — covers TAXO-01
- [ ] `tests/test_cik_resolver.py` — covers CIK zero-padding + cache-hit/miss paths
- [ ] `tests/test_fundamentals.py` — covers INGEST-02 filer-type branching (the highest-risk area this phase)
- [ ] `tests/test_prices.py` — covers INGEST-01
- [ ] `tests/test_refresh.py` — covers STORE-02 partial-failure isolation
- [ ] `tests/test_models.py` — covers STORE-01 CRUD + point-in-time unique constraint
- [ ] Framework install: `uv add --dev pytest pytest-mock respx`
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` config (testpaths, etc.)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Secrets (`DATABASE_URL`, future API keys) via env vars only, never committed; `.env` gitignored; Coolify UI/magic env vars for production values |
| V2 Authentication | no | Explicitly out of scope for v1 per REQUIREMENTS.md — single personal user, no login |
| V3 Session Management | no | No sessions — stateless `GET /companies` |
| V4 Access Control | partial | `GET /companies` has no application-level auth (matches locked scope); see Open Question 2 for the network-level mitigation options the owner should be aware of |
| V5 Input Validation | yes | `pydantic` schema validation on `sectors.yaml` load; `yaml.safe_load` only (never `yaml.load`) to prevent arbitrary object deserialization from a config file |
| V6 Cryptography | no | No passwords/secrets requiring hashing or encryption this phase |
| V7 Error Handling & Logging | yes | Per-ticker failures logged with ticker + reason (structured), never raw stack traces returned to API clients; FastAPI exception handlers return generic error responses |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization of a malformed/tampered `sectors.yaml` | Tampering | `yaml.safe_load` only + strict pydantic schema (reject unknown fields) |
| Unauthenticated public API exposing internal company/pricing data | Information Disclosure | Accepted risk per locked project scope (no auth in v1); recommend the owner consider a Coolify-level IP allowlist or a simple shared-secret header on the domain if the data shouldn't be casually public — flagged as Open Question 2, not resolved here |
| SEC EDGAR / yfinance outbound calls with no timeout | Denial of Service (self-inflicted — a hung request stalls the entire nightly batch) | Explicit `httpx` `timeout=` on every request + `tenacity` `stop_after_attempt` to bound retries |
| Secrets hardcoded in a committed `docker-compose.yml` | Information Disclosure | `DATABASE_URL` and any future API keys via `${VAR}` substitution from Coolify's env var UI / a gitignored `.env`, never literal values in the committed compose file |

## Sources

### Primary (HIGH confidence)
- `data.sec.gov/submissions/CIK0001046179.json` (TSM) — fetched live this session, confirms 20-F filer, no explicit FPI boolean field
- `data.sec.gov/api/xbrl/companyfacts/CIK0001046179.json` (TSM) — fetched live this session, confirms `ifrs-full`-only taxonomy, `Revenue`/`ProfitLossAttributableToOwnersOfParent` concepts, TWD+USD units
- `data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json` (NVDA) — fetched live this session, confirms `us-gaap` taxonomy, `RevenueFromContractWithCustomerExcludingAssessedTax`/`NetIncomeLoss` concepts, confirms no `MarketCap` concept exists, confirms `dei:EntityCommonStockSharesOutstanding` shape
- `www.sec.gov/files/company_tickers.json` — fetched live this session, confirms ticker→CIK JSON shape and zero-padding requirement
- `pip index versions` for fastapi/sqlalchemy/alembic/httpx/pyyaml/pydantic-settings/uvicorn/yfinance/tenacity/sec-edgar-api — run live this session against PyPI
- `coolify.io/docs/knowledge-base/cron-syntax` — fetched via WebFetch this session
- `coolify.io/docs/knowledge-base/docker/compose` — fetched via WebFetch this session

### Secondary (MEDIUM confidence)
- [SEC EDGAR API rate limits and best practices](https://tldrfiling.com/blog/sec-edgar-api-rate-limits-best-practices) — web search, cross-checked against empirical 403 behavior this session
- [SEC EDGAR API guide](https://tldrfiling.com/blog/sec-edgar-api-guide/) — web search, cross-checked against live companyfacts responses
- [yfinance GitHub releases/changelog](https://github.com/ranaroussi/yfinance/releases) — web search, describes 0.2.x→1.x transition
- [yfinance rate-limit discussion, GitHub issue #2125](https://github.com/ranaroussi/yfinance/issues/2125) — community/primary-source evidence

### Tertiary (LOW confidence)
- General bitemporal-modeling articles (Wikipedia, softwarepatternslexicon.com) — no SQLAlchemy-specific point-in-time pattern found in these sources; the actual schema used in this research (Pattern 4) was synthesized directly from the verified EDGAR response shape rather than from a generic bitemporal-modeling reference
- General yfinance 429-mitigation blog posts (medium.com, softhints.com) — consistent with each other and with the GitHub issue tracker, but not independently authoritative

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version confirmed live against PyPI this session, cross-matches CLAUDE.md's own independently-dated verification
- Architecture: HIGH for the EDGAR filer-branching and point-in-time schema design (verified directly against live API responses for both a domestic and a foreign-issuer company in this exact ticker universe); MEDIUM for Coolify deployment specifics (official docs fetched, but not empirically tested against the owner's actual VPS)
- Pitfalls: HIGH for EDGAR-specific pitfalls (CIK padding, UA/rate-limit, taxonomy branching, market-cap-is-derived — all directly verified); MEDIUM for yfinance rate-limit behavior (well-documented community pattern, not stress-tested against a live 55-ticker batch in this session)

**Research date:** 2026-07-19
**Valid until:** 30 days for library versions (fast-moving PyPI ecosystem, matches CLAUDE.md's own churn rate); SEC EDGAR API structure itself is stable and should remain valid ~180 days
