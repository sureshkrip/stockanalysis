# Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 24 (new; 0 modified — greenfield repo)
**Analogs found:** 0 / 24 (no existing source code in repository)

## Repository State (verified)

This is a **greenfield repository**. A directory listing at the repo root confirms only the following exist prior to Phase 1:

```
.claude/CLAUDE.md
.planning/  (planning docs only — CONTEXT.md, RESEARCH.md, PROJECT.md, ROADMAP.md, REQUIREMENTS.md, STATE.md)
data-center-value-chain-tickers.md
```

There is no `backend/`, no `frontend/`, no `docker-compose.yml`, no Python or TypeScript source anywhere in the tree. Consequently **no in-repo analog exists for any file this phase creates.** Every file below is classified by role/data-flow only, with the analog column pointing to RESEARCH.md's Architecture Patterns / Code Examples sections (the only available reference material) instead of a codebase file. The planner should treat RESEARCH.md Patterns 1-6 and the Code Examples block as the authoritative "pattern source" for this phase, not a prior implementation.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|-----------------|----------------|
| `backend/app/main.py` | config/entrypoint | request-response | RESEARCH.md Code Examples: FastAPI `GET /companies` block | no-analog (research-only) |
| `backend/app/config.py` | config | — | RESEARCH.md Standard Stack: `pydantic-settings` row | no-analog (research-only) |
| `backend/app/db.py` | config | — | RESEARCH.md Pattern 6 (Alembic `render_as_batch`) | no-analog (research-only) |
| `backend/app/models.py` | model | CRUD | RESEARCH.md Pattern 4 (point-in-time `Fundamental` model) | no-analog (research-only) |
| `backend/app/api/companies.py` | controller/route | request-response | RESEARCH.md Code Examples: `GET /companies` nested response | no-analog (research-only) |
| `backend/app/ingest/taxonomy.py` | service (config loader) | file-I/O | RESEARCH.md Anti-Patterns (`yaml.safe_load` requirement) | no-analog (research-only) |
| `backend/app/ingest/cik_resolver.py` | service | request-response + file-I/O (cache) | RESEARCH.md Pattern 5 (CIK resolution & caching) | no-analog (research-only) |
| `backend/app/ingest/prices.py` | service | batch/CRUD | RESEARCH.md Pitfall 4 + Common Pitfalls (yfinance batch download) | no-analog (research-only) |
| `backend/app/ingest/fundamentals.py` | service | batch/CRUD | RESEARCH.md Pattern 2 (filer-type branching) + Pattern 3 (market cap) + Code Examples (EDGAR client) | no-analog (research-only) |
| `backend/app/ingest/refresh.py` | service (orchestrator) | batch/event-driven | RESEARCH.md Pattern 1 (per-ticker failure isolation) | no-analog (research-only) |
| `backend/alembic/env.py` | migration config | — | RESEARCH.md Pattern 6 (batch mode) | no-analog (research-only) |
| `backend/alembic/versions/0001_initial.py` | migration | — | RESEARCH.md Pattern 4 (schema fields) | no-analog (research-only) |
| `backend/sectors.yaml` | config (data) | file-I/O | `data-center-value-chain-tickers.md` (existing seed list — see below) | partial (source data exists, YAML shape does not) |
| `backend/tests/conftest.py` | test fixture | — | RESEARCH.md Standard Stack (`pytest-mock`/`respx`) | no-analog (research-only) |
| `backend/tests/test_taxonomy.py` | test | — | none | no-analog |
| `backend/tests/test_cik_resolver.py` | test | — | none | no-analog |
| `backend/tests/test_fundamentals.py` | test | — | none | no-analog |
| `backend/tests/test_prices.py` | test | — | none | no-analog |
| `backend/tests/test_refresh.py` | test | — | RESEARCH.md Pattern 1 (STORE-02 partial-failure) | no-analog (research-only) |
| `backend/Dockerfile` | config | — | RESEARCH.md docker-compose skeleton | no-analog (research-only) |
| `frontend/app/page.tsx` | component (Server Component) | request-response | RESEARCH.md Architectural Responsibility Map (frontend status page row) | no-analog (research-only) |
| `frontend/Dockerfile` | config | — | RESEARCH.md docker-compose skeleton | no-analog (research-only) |
| `docker-compose.yml` | config | — | RESEARCH.md Code Examples: docker-compose.yml skeleton | no-analog (research-only, but skeleton given verbatim) |
| `.env.example` | config | — | RESEARCH.md docker-compose skeleton (`DATABASE_URL`, `EDGAR_USER_AGENT`) | no-analog (research-only) |

## Pattern Assignments

Since no in-repo analogs exist, each assignment below cites the RESEARCH.md section/pattern number to copy from verbatim, rather than a codebase file+line range.

### `backend/app/ingest/refresh.py` (service, batch/event-driven orchestrator)

**Source pattern:** RESEARCH.md "Pattern 1: Per-ticker failure isolation (STORE-02)" (RESEARCH.md lines ~258-291)

```python
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
        continue
    try:
        facts = fetch_fundamentals(t.cik)
        write_fundamentals(t.ticker, facts)
    except Exception as exc:
        failures.append({"ticker": t.ticker, "stage": "fundamentals", "error": str(exc)})
        continue

persist_refresh_log(run_id, failures)  # never raises past this point
```

**Rule:** every network call inside this loop must be wrapped individually — never let one ticker's exception propagate out of the loop (STORE-02 hard requirement).

---

### `backend/app/ingest/fundamentals.py` (service, batch)

**Source patterns:** RESEARCH.md "Pattern 2: Filer-type branching" + "Pattern 3: Market cap is derived, not fetched" + Code Examples "EDGAR client with required headers + timeout" (RESEARCH.md lines ~293-343, ~471-487)

Key excerpts to copy:

```python
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

```python
CONCEPT_MAP = {
    "us-gaap": {
        "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
        "net_income": ["NetIncomeLoss"],
        "shares_outstanding": ["CommonStockSharesOutstanding"],
    },
    "ifrs-full": {
        "revenue": ["Revenue"],
        "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
        "shares_outstanding": [],
    },
}

def pick_taxonomy(facts: dict) -> str:
    if "us-gaap" in facts:
        return "us-gaap"
    if "ifrs-full" in facts:
        return "ifrs-full"
    raise ValueError(f"no known taxonomy in companyfacts response: {list(facts.keys())}")
```

**Critical note (verified live against TSM/NVDA 2026-07-19):** TSM's `Revenue` concept reports in both `TWD` and `USD` units — always filter `unit == "USD"` explicitly. Market cap must be computed (`shares_outstanding × nearest closing price`), never read from a `MarketCap` or `EntityPublicFloat` concept — see Pattern 3 for `compute_market_cap()`.

---

### `backend/app/models.py` (model, CRUD)

**Source pattern:** RESEARCH.md "Pattern 4: Point-in-time fundamentals schema (D-09, STORE-01)" (RESEARCH.md lines ~345-374)

```python
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
    fiscal_period: Mapped[str]
    form: Mapped[str]
    accession_number: Mapped[str]
    filed_date: Mapped["date"] = mapped_column(Date)
    period_end: Mapped["date"] = mapped_column(Date)
    revenue: Mapped[float | None] = mapped_column(Numeric)
    net_income: Mapped[float | None] = mapped_column(Numeric)
    market_cap: Mapped[float | None] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(default="SEC EDGAR")
    taxonomy: Mapped[str]
```

**Rule:** unique key is the 4-tuple `(ticker, fiscal_year, fiscal_period, accession_number)` — never upsert by `ticker` alone (would silently discard prior filing history, violating D-09). Use insert-or-ignore semantics so re-running the refresh is idempotent per filing.

Other models implied by RESEARCH.md's Recommended Project Structure but not detailed in a pattern block — planner/executor should design consistent with the `Fundamental` model's typed `Mapped[]` idiom: `Ticker` (taxonomy row: ticker, name, sub_sector), `Price` (ticker, close, source, as_of), `TickerCik` (ticker, cik cache), `RefreshLog` (run_id, ticker, stage, error, timestamp).

---

### `backend/app/ingest/cik_resolver.py` (service, request-response + file-I/O cache)

**Source pattern:** RESEARCH.md "Pattern 5: CIK resolution & caching (D-06)" (RESEARCH.md lines ~376-393)

```python
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

**Critical pitfall (RESEARCH.md Pitfall 1):** `company_tickers.json`'s `cik_str` is a plain integer — always `str(cik).zfill(10)` before building the `CIK<n>.json` URL path, or requests 404 (verified against AAPL: `320193` → `0000320193`).

---

### `backend/app/api/companies.py` (controller, request-response)

**Source pattern:** RESEARCH.md Code Examples "FastAPI `GET /companies` nested response (D-08)" (RESEARCH.md lines ~489-522)

```python
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

This shape is a **locked user decision (D-08)** — do not deviate from the nested `taxonomy`/`price`/`fundamentals` structure or split into per-resource endpoints in this phase.

---

### `backend/sectors.yaml` (config data, file-I/O)

**Source data (exists in repo):** `data-center-value-chain-tickers.md` — the verified ~56-ticker seed list across 10 sub-sectors (D-01), current as of 2026-07-19, including the newly added CBRS (Cerebras) entry. This is the only file in the pre-Phase-1 repo that should be directly consulted for content when building `sectors.yaml`.

**Shape constraints (D-03 through D-06, no code analog — schema-only):**
- Flat sub-sector tagging, one primary sub-sector per ticker (D-03)
- 10 sub-sectors including "Emerging / picks-and-shovels" as a plain 10th sub-sector, no `watchlist:` flag (D-04)
- Single file, not split per sub-sector (D-05)
- Per-ticker fields: `ticker`, `company name`, `sub_sector` only — no CIK, no notes/alias (D-06; CIK is resolved/cached by the pipeline per Pattern 5, never hand-entered)

**Loader pattern (RESEARCH.md Anti-Patterns + Don't Hand-Roll):** parse with `yaml.safe_load()` (never `yaml.load()`), validate the parsed structure with a pydantic schema so a malformed edit fails loudly with a clear error rather than a deep `KeyError` during ingestion.

---

### `docker-compose.yml` (config)

**Source pattern:** RESEARCH.md Code Examples "docker-compose.yml skeleton (2-service SQLite MVP shape)" (RESEARCH.md lines ~524-545) — reproduced here as the direct copy target:

```yaml
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
  frontend:
    build: ./frontend
    environment:
      - BACKEND_URL=http://backend:8000
```

**Scheduled task (D-10/D-11, RESEARCH.md Pitfall 7):** configure in Coolify UI, not in the compose file itself:
```
Schedule: 0 2 * * *
Command:  docker exec backend python -m app.ingest.refresh
```
`02:00 UTC` is the DST-safe fixed time chosen in RESEARCH.md's Open Questions #1 to satisfy D-11's "~9pm ET, after close" intent across both EDT and EST — document this choice as intentional rather than a literal "9pm ET" translation.

---

### `backend/alembic/env.py` (migration config)

**Source pattern:** RESEARCH.md "Pattern 6: SQLite-compatible Alembic migrations from the start" (RESEARCH.md lines ~395-402)

```python
with connectable.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
```

**Rule:** `render_as_batch=True` must be set starting with the **first** migration, not added retroactively — SQLite doesn't support most `ALTER TABLE` variants, and inconsistent batch-mode history breaks the SQLite→Postgres migration path CLAUDE.md's `DATABASE_URL` design depends on.

---

### `frontend/app/page.tsx` (component, request-response, Server Component)

**No RESEARCH.md code excerpt provided** — only architectural guidance exists (Architectural Responsibility Map row: "Frontend Server (SSR)" tier, Next.js App Router Server Component fetches `/companies` or `/health` server-side, no client-side data-fetching logic needed). D-12 constraints apply directly:
- Minimal status page only — company count from `/companies` or "API: healthy"
- No real UI/table logic (deferred to Phase 2)
- Must use Next.js 16 async dynamic APIs correctly if `params`/`searchParams`/`cookies()`/`headers()` are touched (`await` required — CLAUDE.md "What NOT to Use" table)
- No `next lint` reliance (removed in Next.js 16)

## Shared Patterns

### Per-ticker failure isolation (STORE-02)
**Source:** RESEARCH.md Pattern 1
**Apply to:** `backend/app/ingest/refresh.py`, and indirectly to `prices.py`/`fundamentals.py`/`cik_resolver.py` (each must raise cleanly so `refresh.py`'s try/except can catch and log rather than crash).

### EDGAR User-Agent requirement
**Source:** RESEARCH.md Pitfall 3 + Code Examples EDGAR client
**Apply to:** every file making an EDGAR request (`cik_resolver.py`, `fundamentals.py`) — must share one `httpx.Client` instance configured with an explicit descriptive `User-Agent` header, or the entire batch run 403s.

### Point-in-time / never-overwrite semantics
**Source:** RESEARCH.md Pattern 4 + Pitfall 5
**Apply to:** `models.py` (`Fundamental` unique constraint) and `fundamentals.py` (insert-or-ignore write logic) — `prices.py` is the exception (latest-close upsert-by-ticker is correct there).

### `pydantic-settings` for config
**Source:** RESEARCH.md Standard Stack + Don't Hand-Roll table
**Apply to:** `backend/app/config.py` — typed `DATABASE_URL`/`EDGAR_USER_AGENT` config, no scattered `os.environ.get()` calls.

### Sync-only backend (no async-first architecture)
**Source:** CLAUDE.md "What NOT to Use" table + RESEARCH.md Project Constraints
**Apply to:** `main.py`, `api/companies.py`, `db.py`, all SQLAlchemy usage — sync `def` routes, sync sessions. Async only permissible inside `refresh.py`/`prices.py`/`fundamentals.py` via a bounded semaphore if needed for speed, never as a router-wide requirement.

## No Analog Found

Every file in this phase has **no in-repo analog** — the table below is effectively the full file list, restated for the planner's convenience per the required-output format. See "Repository State (verified)" above for why, and "Pattern Assignments" above for the RESEARCH.md section to use instead of a codebase analog for each.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| All 24 files listed in File Classification | (various) | (various) | Greenfield repository — confirmed via root directory listing on 2026-07-19; only `.claude/`, `.planning/`, and `data-center-value-chain-tickers.md` predate this phase. RESEARCH.md's Architecture Patterns (1-6) and Code Examples block are the substitute pattern source for all files. |

## Metadata

**Analog search scope:** Repository root (`C:\Users\sures\dev\repos\stockanalysis`), full tree listing to depth 3, excluding `.git` and `.planning`.
**Files scanned:** 3 (`.claude/CLAUDE.md`, `data-center-value-chain-tickers.md`, plus directory structure) — no source code files exist to scan.
**Pattern extraction date:** 2026-07-19
