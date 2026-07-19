# Architecture Research

**Domain:** Personal financial data tracking system (multi-source ingestion → normalized store → derived analytics → JSON API → Next.js dashboard)
**Researched:** 2026-07-19
**Confidence:** MEDIUM (established software patterns cross-checked across multiple sources; project-specific sizing/tradeoffs are original analysis, not sourced claims)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                         SCHEDULED INGESTION                            │
│                  (Coolify cron → python -m app.jobs.refresh)           │
├───────────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐   ┌────────────────┐   ┌─────────────────────┐   │
│  │ Taxonomy Loader│   │ PriceProvider   │   │ FundamentalsProvider │   │
│  │ (sectors.yaml) │   │ (yfinance→FMP)  │   │ (SEC EDGAR, fixed)   │   │
│  └───────┬────────┘   └───────┬────────┘   └──────────┬───────────┘   │
│          │                    │                        │              │
│          └──────────► Refresh Orchestrator ◄────────────┘              │
│                       (per-ticker isolation,                           │
│                        retry/backoff, run log)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                                │ upsert (idempotent)
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          DATA STORE (SQLite→Postgres)                  │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ tickers   │  │ daily_prices │  │ fundamentals │  │ refresh_runs │ │
│  │           │  │ (ticker,date)│  │ (ticker,     │  │ (audit log)  │ │
│  │           │  │  PK          │  │  period,     │  │              │ │
│  │           │  │              │  │  as_of_date) │  │              │ │
│  └───────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
└──────────────────────────────┬──────────────────────────────────────┘
                                │ read (compute-on-read)
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       FASTAPI SERVICE LAYER                            │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Repository│──│ Analytics /  │──│ Screens      │  taxonomy.yaml     │
│  │ (SQL      │  │ ratios       │  │ registry     │◄─── loaded once,   │
│  │  queries) │  │ (P/E, EV/    │  │ (hand-written│     in-process     │
│  │           │  │  EBITDA, YTD)│  │  rules)      │                   │
│  └───────────┘  └──────────────┘  └──────────────┘                   │
├───────────────────────────────────────────────────────────────────────┤
│      Routers: GET /sectors  GET /companies  GET /companies/{ticker}   │
│               GET /screens                                            │
└──────────────────────────────┬──────────────────────────────────────┘
                                │ JSON over HTTP
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    NEXT.JS APP ROUTER (frontend)                      │
│  ┌────────────────────┐   ┌────────────────────┐                     │
│  │ Server Components   │   │ Client Components   │                     │
│  │ (page shells, fetch │   │ (sortable table leaf,│                    │
│  │  from FastAPI)      │   │  chart, heatmap grid)│                    │
│  └────────────────────┘   └────────────────────┘                     │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|-----------------|-------------------------|
| Taxonomy loader | Single source of truth for ticker → sub-sector → sector; resolves grouping for both ingestion (universe) and API (labeling) | `sectors.yaml` parsed into a Pydantic model at process startup, cached in memory for process lifetime |
| PriceProvider | Fetches daily OHLC/close for a ticker from whichever price backend is configured; normalizes to internal shape; the swappable part | Python `Protocol`/ABC with `YFinanceProvider` and (later) `FMPProvider` implementations, selected by a `PRICE_PROVIDER` env var |
| FundamentalsProvider | Fetches quarterly/annual fundamentals from SEC EDGAR; permanent source of record, not swapped | Single `EdgarProvider` implementation behind its own interface — deliberately **not** unified with `PriceProvider` |
| Refresh orchestrator | Iterates the ticker universe, isolates per-ticker failures, retries transient errors, upserts results, writes a run-log row | A plain Python script/module invoked by Coolify's scheduled task, not a queue/worker system |
| Data store | Durable, normalized storage for raw prices and point-in-time fundamentals; no derived/computed columns | SQLite file (MVP) → Postgres (via `DATABASE_URL`), same SQLAlchemy models either way |
| Analytics/ratios | Pure functions computing P/E, EV/EBITDA, growth, momentum, composite score from stored raw data | Plain Python module (`analytics.py`) called by services, not a scheduled job |
| Screens registry | Named, hand-written relative-value queries (cheapest P/E in sub-sector, fastest growth, etc.) | A small dict/enum mapping screen name → function, not a generic filter DSL |
| FastAPI routers | Thin HTTP layer: request → repository/analytics call → response model | `/sectors`, `/companies`, `/companies/{ticker}`, `/screens` |
| Next.js frontend | Renders dashboard from the API; owns zero business logic (no ratio math in TypeScript) | Server Components fetch, Client Components handle sort/interaction |

## Recommended Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, router registration
│   ├── config.py                # env vars: DATABASE_URL, PRICE_PROVIDER, FMP_API_KEY
│   ├── taxonomy.py              # loads sectors.yaml → in-memory model, resolves ticker→sub-sector
│   ├── models/                  # SQLAlchemy models: Ticker, DailyPrice, Fundamental, RefreshRun
│   ├── schemas/                 # Pydantic response models (API contracts)
│   ├── providers/
│   │   ├── base.py              # PriceProvider Protocol, FundamentalsProvider Protocol, normalized dataclasses, error taxonomy
│   │   ├── yfinance_provider.py
│   │   ├── fmp_provider.py      # added later, same interface
│   │   └── edgar_provider.py
│   ├── repositories/            # SQL query layer (get_prices, get_latest_fundamentals, ...)
│   ├── analytics/               # ratios.py, growth.py, composite_score.py — pure functions over repo output
│   ├── screens/                 # registry.py + one module per named screen
│   ├── routers/                 # sectors.py, companies.py, screens.py
│   └── jobs/
│       └── refresh.py           # orchestrator entrypoint: `python -m app.jobs.refresh`
├── sectors.yaml                  # the taxonomy — edited directly, deployed via git push
├── alembic/                       # migrations (SQLite-and-Postgres-safe types only)
└── tests/

frontend/
├── app/
│   ├── page.tsx                  # dashboard: Server Component, fetches /companies + /sectors
│   ├── companies/[ticker]/page.tsx   # detail: Server Component + client chart leaf
│   ├── screens/page.tsx          # Server Component, fetches /screens
│   └── components/
│       ├── SortableTable.tsx     # 'use client' — holds sort/filter state for the ~55-row dataset
│       ├── PriceChart.tsx        # 'use client' — recharts, isolated leaf
│       └── SectorHeatmap.tsx     # 'use client' — interactive grid
└── lib/api.ts                    # typed fetch wrappers matching the FastAPI response schemas
```

### Structure Rationale

- **`providers/base.py` as the seam:** the whole point of the provider-abstraction requirement is that adding `fmp_provider.py` later touches zero files outside `providers/`. Keep the Protocol narrow (2-3 methods) so new implementations are cheap to write.
- **`analytics/` separate from `providers/` and `repositories/`:** analytics is pure computation over already-stored data — no I/O, no network calls, trivially unit-testable with fixture rows, and reusable from both the API and (later) a notebook/script without spinning up FastAPI.
- **`jobs/refresh.py` as a script, not a service:** matches the "Coolify scheduled tasks over GitHub Actions" decision — no persistent worker/queue process needed at 55 tickers/daily cadence.
- **`sectors.yaml` at the repo root, not in a DB table:** it changes by git commit, reviewed like code, and needs no admin UI for a single-user tool (see Pattern 3 below).

## Architectural Patterns

### Pattern 1: Provider abstraction via Protocol + normalized DTOs

**What:** Define the *shape callers depend on* as a `Protocol` (structural typing, no inheritance required) plus small, normalized dataclasses/Pydantic models. Every concrete provider — `yfinance` today, FMP later — implements the Protocol and returns the same normalized shape, regardless of what its underlying library returns.

**When to use:** Any external data dependency you expect to swap, or that is unofficial/fragile (yfinance is an unofficial scraper with no SLA) and needs an eventual replacement without touching call sites.

**Trade-offs:** Small upfront cost (defining the interface before you strictly need it) buys a swap that's a config change + one new file, not a rewrite. Keep the interface to the minimum both providers can support — don't leak yfinance-specific fields (e.g. its multi-index DataFrame quirks) into the interface.

**Example:**
```python
# app/providers/base.py
from typing import Protocol
from datetime import date
from pydantic import BaseModel

class PriceBar(BaseModel):
    ticker: str
    price_date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float          # split/dividend-adjusted, kept alongside raw close
    volume: int
    source: str                # provenance: 'yfinance' | 'fmp'

class ProviderError(Exception): ...
class ProviderRateLimited(ProviderError): ...
class ProviderDataUnavailable(ProviderError): ...

class PriceProvider(Protocol):
    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[PriceBar]: ...

class FundamentalsProvider(Protocol):
    def get_fundamentals(self, ticker: str, since: date | None = None) -> list["FundamentalSnapshot"]: ...
```

Each concrete adapter (`YFinanceProvider`, later `FMPProvider`) catches its library's own exceptions and re-raises the normalized `ProviderError` subclasses, so the refresh orchestrator's retry logic never imports yfinance-specific or FMP-specific exception types.

**Deliberate separation:** `PriceProvider` and `FundamentalsProvider` are two different interfaces, not one. SEC EDGAR is fixed as the permanent fundamentals source of record (per project constraints); only the *price* feed swaps. Unifying them behind one interface would falsely imply fundamentals are swappable too.

### Pattern 2: Point-in-time fundamentals (as-of date, not overwrite-in-place)

**What:** Every fundamentals data point is inserted as a new row keyed by `(ticker, fiscal_period, as_of_date)` rather than updated in place. `period_end_date` (or `fiscal_period`) is *valid time* — what period the number describes. `as_of_date` is effectively transaction time — when that number became known (SEC filing date). When SEC issues a restatement (10-K/A, or a 10-K that restates prior-year comparatives), it lands as an additional row with a later `as_of_date`, never overwriting the original.

**When to use:** Any metric that gets revised after first publication — which is every fundamentals metric, since restatements are common (over 1,700 US public-company restatements 2010-2020). Prices don't need this — a daily close is final once the trading day ends (splits are handled separately, see below), so `daily_prices` uses a simple upsert-on-natural-key, not point-in-time rows.

**Trade-offs:** Slightly more storage (a handful of extra rows per ticker over the years, not per day) and one extra query pattern ("latest known as of this date") versus a naive overwrite table. In return: a trend chart of revenue growth never silently jumps because a later restatement overwrote what an earlier chart render already showed, and a screen never mixes pre- and post-restatement numbers across peers. Full bitemporal modeling (tracking corrections-to-corrections with independent valid/transaction time ranges) is overkill here — this project explicitly excludes a backtesting engine — so the practical simplification (one row per known-value, ordered by `as_of_date`) is sufficient; don't build a general bitemporal query engine for a personal dashboard.

**Example:**
```sql
-- one row per (ticker, fiscal_period) per time it was reported/restated
CREATE TABLE fundamentals (
  id             INTEGER PRIMARY KEY,
  ticker         TEXT NOT NULL REFERENCES tickers(ticker),
  fiscal_period  TEXT NOT NULL,     -- '2025-Q4', '2025-FY'
  period_end_date DATE NOT NULL,
  as_of_date     DATE NOT NULL,     -- SEC filing/accepted date
  filed_form     TEXT NOT NULL,     -- '10-Q','10-K','10-K/A'
  revenue        NUMERIC,
  net_income     NUMERIC,
  eps_diluted    NUMERIC,
  shares_outstanding NUMERIC,
  total_assets   NUMERIC,
  total_debt     NUMERIC,
  cash_and_equivalents NUMERIC,
  source         TEXT NOT NULL DEFAULT 'sec_edgar',
  source_accession TEXT,             -- SEC accession number, for audit/debug
  UNIQUE (ticker, fiscal_period, as_of_date)
);

-- "current" view used by 95% of the dashboard: latest known value per period
CREATE VIEW latest_fundamentals AS
SELECT f.*
FROM fundamentals f
JOIN (
  SELECT ticker, fiscal_period, MAX(as_of_date) AS max_as_of
  FROM fundamentals GROUP BY ticker, fiscal_period
) latest ON f.ticker = latest.ticker
        AND f.fiscal_period = latest.fiscal_period
        AND f.as_of_date = latest.max_as_of;
```

A wide table (one column per known metric) beats an EAV/metric-per-row design here: SEC XBRL exposes a known, fixed set of standard concepts (revenue, net income, shares outstanding, etc.), the metric count is small (~10-15), and a wide row maps directly onto a Pydantic model — no pivot needed on every read. Adding a new tracked metric later is a migration, which is cheap and rare at this scale; EAV's flexibility isn't needed and costs a join/pivot on every query.

**Prices and splits:** store both `close` (raw) and `adj_close` (split/dividend-adjusted) per row. If a split happens after a price row is already stored, re-running the provider fetch for the affected date range and upserting corrects `adj_close` without needing a bitemporal price model — splits are rare and self-correcting via the provider's own adjusted-close field.

### Pattern 3: Config-file taxonomy, loaded at process start (not seeded into DB tables)

**What:** `sectors.yaml` is the single source of truth for the ticker → sub-sector → sector tree. It is parsed once at process startup (API) or at run start (batch job) into an in-memory structure; the database stores no independent copy of the taxonomy — `tickers` rows hold identity/metadata (name, active flag), and sub-sector membership is resolved by looking the ticker up in the loaded YAML at read time.

**When to use:** Taxonomy that changes by human judgment call at a slow cadence (here, roughly monthly) and is edited by the one person who understands the domain — not by end users through a UI. This project is single-user, has git already as the deployment mechanism (Coolify redeploys on push), and has no requirement for a taxonomy-editing UI.

**Trade-offs vs. seeding into DB tables:**

| | YAML (recommended) | DB tables |
|---|---|---|
| Diff/review | Git diff shows exactly what moved, when, why (commit message) | Requires a migration or manual UPDATE; no natural audit trail without extra columns |
| Deploy | Edit → commit → push → Coolify redeploy picks it up on next process start | Needs a migration or an admin write path |
| Editing tool | Any text editor | Needs a script or UI — none planned |
| Freshness | Reloaded on redeploy (which is also how the edit gets shipped) — no separate hot-reload complexity needed | Live-editable without a deploy, but nothing in this project needs that |
| Sync risk | None — single source, read at query time, never duplicated | Two copies (table + any config) can drift if not carefully synced |

Given the change cadence (~monthly) and single-editor workflow, YAML is the clear right answer — this validates the decision already recorded in PROJECT.md rather than overturning it. The one thing to get right: don't *also* denormalize `sub_sector` onto the `tickers` DB row "for convenience" — that creates a second copy that can silently drift from the YAML after an edit. Resolve sub-sector purely from the loaded YAML at request time; at ~55 tickers this lookup is a dict access, not a performance concern.

```yaml
# sectors.yaml
sectors:
  semiconductors:
    display_name: "Semiconductors"
    sub_sectors:
      ai_chips:
        display_name: "AI Chips / Accelerators"
        tickers: [NVDA, AMD, AVGO, MRVL, ARM, INTC]
      memory_storage:
        display_name: "Memory / Storage"
        tickers: [MU, SNDK, WDC, STX]
  power_electrical:
    display_name: "Power / Electrical"
    sub_sectors:
      power:
        display_name: "Power / Electrical"
        tickers: [VRT, ETN, EMR, HUBB, NVT, GEV]
watchlist:
  display_name: "Emerging / Picks-and-Shovels (unverified)"
  tickers: [CRWV, NBIS, APLD, IREN, SMCI, GDS]
```

## Data Flow

### Ingestion Flow (scheduled, one-directional into the store)

```
Coolify cron trigger
    ↓
app.jobs.refresh (orchestrator)
    ↓ load                              ↓ load
sectors.yaml (ticker universe)     DB: existing tickers/rows
    ↓
for each ticker (sequential, isolated try/except):
    PriceProvider.get_daily_bars(ticker, since=last_stored_date)
        ↓ success → normalize → upsert daily_prices (ticker, date) PK
        ↓ transient failure → retry w/ backoff (max N) → still failing → log to refresh_runs, continue
    FundamentalsProvider.get_fundamentals(ticker, since=last_as_of_date)   [lower frequency, e.g. weekly]
        ↓ success → insert NEW row per (ticker, fiscal_period, as_of_date) — never overwrite
        ↓ failure → log, continue
    ↓
write refresh_runs summary row (attempted, succeeded, failed, per-failure reasons)
```

### Read Flow (API request → response, always computed fresh from stored raw data)

```
GET /companies?sub_sector=ai_chips&sort=pe_ratio
    ↓
router → service
    ↓                                    ↓
repository.get_latest_prices(tickers)   repository.get_latest_fundamentals(tickers)
    ↓                                    ↓
    └──────────────► analytics.compute_ratios(prices, fundamentals) ─────► [{ticker, pe_ratio, ev_ebitda, ytd_return, ...}]
                                          ↓
                            taxonomy.resolve(ticker) → sub_sector label attached
                                          ↓
                                    sort/paginate
                                          ↓
                                   JSON response
```

### Key Data Flows

1. **Ingestion is the only writer.** Nothing else in the system writes to `daily_prices` or `fundamentals` — the API is read-only against the store. This keeps the read path simple (no locking/consistency concerns beyond what SQLite/Postgres already give you) and means analytics correctness is entirely a function of what the last refresh run stored.
2. **Analytics are never persisted as their own table row (MVP).** P/E, EV/EBITDA, growth, momentum, composite score are computed in the service layer from raw stored data on every request. There is no `derived_metrics` table to keep in sync, and therefore no staleness bug where a screen shows a ratio computed from yesterday's price after today's refresh already ran.
3. **Taxonomy resolution happens at read time, not ingest time**, and is not persisted per-ticker — see Pattern 3.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|---------------------------|
| ~55 tickers, daily, 1 user (this project) | SQLite, compute-on-read for all ratios/screens, sequential per-ticker fetch loop in the refresh script, single Coolify container/compose stack. This is comfortably within "just do the simple thing" territory. |
| ~500 tickers, daily, 1 user | Still fine for SQLite and compute-on-read (query volume is still tiny). The refresh script's *wall-clock duration* becomes the practical concern — a sequential loop over 500 tickers with backoff on failures can take a while. Move to bounded-concurrency async fetch (`httpx` + `asyncio.Semaphore`) once on FMP, which has documented rate limits (unlike yfinance, where concurrency risks IP bans). |
| Multi-user (explicitly out of scope) | Would need an auth layer, per-user watchlists/screens, and a real task queue (Celery/RQ/APScheduler-as-a-service) instead of a single cron script, since a shared refresh job and a personal-use API today assume one trust boundary and one consumer. Postgres migration (already planned as the upgrade path) becomes necessary rather than optional at this point. |

### Scaling Priorities

1. **First bottleneck (if it ever appears): refresh script wall-clock time**, not query/read performance. At 55 tickers this is a non-issue (a few minutes at most, even sequential with backoff). Fix by adding bounded concurrency only once ticker count or provider count grows enough to matter — don't build it upfront.
2. **Second bottleneck (theoretical, unlikely to be reached): SQLite write contention** if ingestion and API reads ever overlap heavily. At one scheduled run/day and one reader, this won't surface; the `DATABASE_URL` → Postgres upgrade path already planned in the project constraints is the correct escape hatch if it ever does.

## Anti-Patterns

### Anti-Pattern 1: Computing and storing only derived ratios, discarding the inputs

**What people do:** Ingestion computes P/E, growth %, etc. and stores just the computed number, not the raw price/fundamentals it came from.
**Why it's wrong:** Loses the ability to recompute with a corrected formula later (e.g., switching diluted vs. basic EPS, or fixing a bug in growth-rate math) without re-fetching from providers. Also couples the ingestion script to analytics logic, so a bug fix in a ratio formula requires touching the ingestion path instead of a pure function.
**Do this instead:** Ingestion stores only raw, normalized provider output. All ratios/scores are pure functions over that raw data, computed in the service layer on read (see Pattern in Data Flow section).

### Anti-Pattern 2: One giant try/except around the whole ticker loop

**What people do:** Wrap the entire "fetch all 55 tickers" loop in a single try/except, or worse, no error handling at all, so one provider hiccup (rate limit, one delisted ticker, one malformed response) aborts the entire run and no tickers get refreshed that day.
**Why it's wrong:** Directly violates the "one bad ticker must not kill the run" requirement; turns a single flaky data point into a total outage of the day's data.
**Do this instead:** Isolate try/except per ticker inside the loop; retry only the failing ticker with backoff; log the failure and continue; summarize failures in the run log rather than raising past the loop boundary.

### Anti-Pattern 3: Hardcoding sub-sector membership in Python

**What people do:** A `SUB_SECTORS = {"ai_chips": ["NVDA", "AMD", ...]}` dict literal in application code.
**Why it's wrong:** Every monthly taxonomy edit becomes a code change requiring a PR review of application logic, when it's actually just a data edit. Also risks the taxonomy being scattered across multiple files if referenced from both ingestion and API code.
**Do this instead:** `sectors.yaml` as the single source, loaded once at process start (Pattern 3).

### Anti-Pattern 4: One provider interface for both prices and fundamentals

**What people do:** A single `DataProvider` interface with both `get_prices()` and `get_fundamentals()`, implemented by yfinance/FMP for both, treating SEC EDGAR as "just another provider" behind the same swap mechanism.
**Why it's wrong:** Fundamentals are explicitly meant to stay pinned to SEC EDGAR permanently as the source of record — that's a different lifecycle and different reliability contract than the swappable price feed. Unifying them implies fundamentals could be swapped, contradicting the project's own constraint.
**Do this instead:** Two separate interfaces (`PriceProvider`, `FundamentalsProvider`); only `PriceProvider` gets a second implementation later.

### Anti-Pattern 5: Business logic (ratio math) duplicated in the frontend

**What people do:** Send raw price + fundamentals to the frontend and compute P/E, growth, etc. in TypeScript so the API stays "thin."
**Why it's wrong:** Splits the single source of truth for financial formulas across two languages/codebases; a formula fix has to be made twice; the frontend becomes coupled to raw data shapes instead of a stable computed contract.
**Do this instead:** All ratio/score computation lives server-side in Python (`analytics/`); the API returns already-computed values; the frontend only renders and sorts what it's given.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|----------------------|-------|
| yfinance | `YFinanceProvider` implements `PriceProvider`; called synchronously per ticker inside the refresh loop | Unofficial, undocumented, no SLA — wrap every call in the normalized error taxonomy; treat any unexpected exception as `ProviderDataUnavailable` rather than letting a library-internal exception type leak into orchestrator retry logic |
| Financial Modeling Prep (later) | `FMPProvider` implements the same `PriceProvider` Protocol, added without touching callers | Paid tier has documented rate limits — this is where bounded async concurrency becomes worth adding, unlike with yfinance |
| SEC EDGAR | `EdgarProvider` implements `FundamentalsProvider`; fixed, permanent, ~10 req/sec fair-use limit | Respect the rate limit with a small delay/backoff in the adapter itself, not in the orchestrator — keeps the rate-limit knowledge co-located with the provider that has it |
| FRED (macro context) | Separate, lower-priority integration; not part of the per-ticker refresh loop | Used for sector-level or macro context, not per-company data — likely a separate, much-less-frequent job |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|-----------------|-------|
| Refresh orchestrator ↔ Providers | Direct Python function calls against the Protocol interface | No network/queue between them — it's all one process, invoked by cron |
| Providers ↔ Data store | Providers never write to the DB directly; the orchestrator receives normalized DTOs from providers and does the upsert | Keeps providers pure "fetch and normalize," testable without a DB |
| API service layer ↔ Data store | Repository layer only; routers never write raw SQL | Standard repository pattern — swappable storage backend without touching routers/services |
| FastAPI ↔ Next.js | JSON over HTTP, versionless internal API (single consumer) | No auth needed today (single-user, same-network deploy via Coolify); keep the contract stable since the frontend has no fallback data source |
| Taxonomy loader ↔ everything else | In-memory, read-only after load | Both ingestion (universe) and API (labeling) import the same loader module — one parse, two consumers |

## Build Order / Dependency Sequence

The dependency graph, in the order components should be built and validated:

1. **Data model + migrations** (`tickers`, `daily_prices`, `fundamentals`, `refresh_runs`) — everything downstream needs the schema to exist. Use SQLAlchemy models with types that work identically on SQLite and Postgres (plain `NUMERIC`/`DECIMAL`, no SQLite-only features), and Alembic from day one so the later `DATABASE_URL` swap is a config change, not a migration rewrite.
2. **Taxonomy YAML + loader** — cheap to build (Pydantic model + YAML parse), and both ingestion (step 3) and the API (step 6) depend on it for "which tickers exist" and "how are they grouped."
3. **Provider abstraction (interfaces) + concrete adapters**: define `PriceProvider`/`FundamentalsProvider` Protocols first, then `YFinanceProvider` (fast to build, free) and `EdgarProvider`. Build the interface with FMP explicitly in mind even though it isn't implemented yet — that's the entire point of doing this before, not after, the ingestion script exists.
4. **Batch refresh script** — depends on (1)+(2)+(3). This is the component that actually populates real data; build and *run* it against the real ~55-ticker universe before building the API, since there's nothing meaningful to serve until this works end-to-end with real per-ticker failures observed and handled.
5. **Analytics/ratios + screens** — depends on (4)'s output existing in the DB. Pure functions, unit-testable against fixture rows independent of the API layer.
6. **FastAPI routers** (`/sectors`, `/companies`, `/companies/{ticker}`, `/screens`) — depends on (1)(2)(5); a thin HTTP wrapper around repository + analytics calls.
7. **Next.js frontend** — depends entirely on (6)'s contract being stable; last, since it carries the least architectural risk and the most expected visual/UX iteration.
8. **docker-compose / Coolify wiring** — per the project's own "docker-compose from Phase 0" decision, stand this up in parallel with step 1 (not after step 7) so the scheduled-task infrastructure and reverse proxy exist before there's real data to serve — retrofitting deployment structure after the fact is the thing that decision is explicitly meant to avoid.

This build order maps onto roadmap phases roughly as: Phase 0 (scaffold + compose, parallel with schema) → Phase 1 (data model + taxonomy) → Phase 2 (provider abstraction + yfinance + EDGAR ingestion) → Phase 3 (analytics/screens) → Phase 4 (API) → Phase 5 (frontend dashboard) → later phase (FMP provider swap, once a paid feed is justified).

## Sources

- [The Repository Pattern in Python: Write Flexible, Testable Code (With FastAPI Examples)](https://medium.com/@kmuhsinn/the-repository-pattern-in-python-write-flexible-testable-code-with-fastapi-examples-aa0105e40776) — MEDIUM confidence
- [Repository Pattern — cosmicpython.com](https://www.cosmicpython.com/book/chapter_02_repository) — MEDIUM confidence
- [Clean Architecture in FastAPI / repository-as-Protocol pattern (DeepWiki, dev.to summaries)](https://deepwiki.com/jujumilk3/fastapi-clean-architecture/5-repository-pattern) — MEDIUM confidence
- [Bitemporal modeling — Wikipedia](https://en.wikipedia.org/wiki/Bitemporal_modeling) — MEDIUM confidence
- [Financial data must be made point-in-time — validityBase](https://www.vbase.com/blog/financial-data-must-be-made-point-in-time/) — MEDIUM confidence
- [Point-in-Time Data: Critical for Investment Decisions — StarQube](https://starqube.com/point-in-time-data/) — MEDIUM confidence
- [Exploring the architecture behind the OpenBB Platform](https://openbb.co/blog/exploring-the-architecture-behind-the-openbb-platform/) — MEDIUM confidence
- [OpenBB Architecture Overview — official docs](https://docs.openbb.co/odp/python/developer/architecture_overview) — MEDIUM confidence
- [How to Build Batch Retry Strategies](https://oneuptime.com/blog/post/2026-01-30-batch-processing-retry-strategies/view) — MEDIUM confidence
- [Reducing batch failures by standardizing retries, backoff, and idempotency](https://us.fitgap.com/stack-guides/reducing-batch-failures-by-standardizing-retries-backoff-and-idempotency) — MEDIUM confidence
- [Getting Started: Server and Client Components — Next.js official docs](https://nextjs.org/docs/app/getting-started/server-and-client-components) — MEDIUM confidence
- [The Next.js Table Tango: Mastering Dynamic Data Tables with Server-Side Performance & Client-Side Fluidity](https://medium.com/@divyanshsharma0631/the-next-js-table-tango-mastering-dynamic-data-tables-with-server-side-performance-client-side-a71ee0ec2c63) — MEDIUM confidence
- Project context: `.planning/PROJECT.md`, `data-center-value-chain-tickers.md` (project-internal, HIGH confidence as source of requirements)

---
*Architecture research for: personal financial data tracking / analysis dashboard (data-center value-chain sector)*
*Researched: 2026-07-19*
