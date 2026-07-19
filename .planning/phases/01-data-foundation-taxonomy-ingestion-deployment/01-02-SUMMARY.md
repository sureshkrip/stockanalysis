---
phase: 01-data-foundation-taxonomy-ingestion-deployment
plan: 02
subsystem: infra
tags: [yfinance, tenacity, sqlalchemy, fastapi, ingestion]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Ticker/Price/RefreshLog models, taxonomy sync, GET /companies scaffold"
provides:
  - "app.ingest.prices — fetch_prices/fetch_price/write_price (INGEST-01), bounded 3-attempt jittered retry, single-vs-multi normalization"
  - "app.ingest.refresh — run_refresh orchestrator with per-ticker failure isolation and RefreshLog (STORE-02), python -m app.ingest.refresh CLI entrypoint"
  - "GET /companies price block populated via a single bounded join query, no N+1"
affects: ["01-03", "01-04", "01-05"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-ticker isolation: fetch_price (tenacity-retried) wrapped in the orchestrator's own try/except that records a TickerFailure and continues; commit per ticker so an interrupted run leaves completed tickers durably persisted"
    - "yf.download() called with multi_level_index=False — the flag that actually produces the flat-column (single ticker) vs MultiIndex-column (multi ticker) shape split on the installed yfinance 1.5.1, superseding the plan's untested assumption that the default already did this"
    - "Insert-or-update on (ticker, as_of) for prices (correctly update-on-conflict) vs insert-or-ignore for fundamentals (plan 04) — different conflict policies for different provenance semantics"
    - "GET /companies price join: max(as_of)-per-ticker subquery outer-joined back onto Price in one statement, never a per-ticker query"

key-files:
  created:
    - backend/app/ingest/prices.py
    - backend/app/ingest/refresh.py
    - backend/tests/test_prices.py
    - backend/tests/test_refresh.py
  modified:
    - backend/app/api/companies.py
    - backend/tests/test_companies_endpoint.py

key-decisions:
  - "yf.download() needs multi_level_index=False to reproduce the single-vs-multi shape difference the plan's action text assumed; the library default (multi_level_index=True) returns MultiIndex columns even for a 1-item ticker list on the installed 1.5.1 line — verified live, not just against training-data assumptions about yfinance's API"
  - "fetch_price(ticker) is a thin retry-wrapped delegate over fetch_prices([ticker]) rather than a separate implementation, so both the batch and per-ticker paths share one normalization code path"
  - "run_refresh's _main() accepts an optional taxonomy_path positional CLI arg (defaulting to backend/sectors.yaml) so it can run against a fixture/scratch taxonomy for verification and testing without touching the owner's real sectors.yaml"

patterns-established:
  - "STORE-02 per-ticker isolation: broad except Exception + continue inside the orchestrator loop, never letting one ticker's failure propagate; a genuine BaseException (e.g. an external interrupt) still propagates but prior tickers' commits are already durable"
  - "RefreshLog is written unconditionally at the end of every run, including a fully clean one"

requirements-completed: [INGEST-01, STORE-02]

coverage:
  - id: D1
    description: "fetch_prices/fetch_price return a normalized PriceRow (ticker, close, as_of, source='yfinance') for both single- and multi-ticker requests, using yfinance.download() batched over the ticker list rather than a per-symbol metadata loop"
    requirement: "INGEST-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_prices.py::test_fetch_prices_multi_ticker_returns_one_row_per_ticker"
        status: pass
      - kind: unit
        ref: "backend/tests/test_prices.py::test_fetch_prices_single_ticker_matches_multi_shape"
        status: pass
      - kind: unit
        ref: "backend/tests/test_prices.py::test_fetch_price_success"
        status: pass
    human_judgment: false
  - id: D2
    description: "fetch_price retries transient failures with jittered exponential backoff bounded at 3 attempts, reraising the underlying error past the retry budget"
    requirement: "INGEST-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_prices.py::test_fetch_price_retries_transient_failure_then_succeeds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_prices.py::test_fetch_price_exhausts_retry_budget_bounded_at_3"
        status: pass
    human_judgment: false
  - id: D3
    description: "write_price upserts on (ticker, as_of) — same-day rewrite updates in place, different dates create separate rows — and preserves full Decimal precision through the Numeric column round-trip"
    requirement: "STORE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_prices.py::test_write_price_upsert_same_ticker_date_leaves_one_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_prices.py::test_write_price_different_dates_leaves_two_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_prices.py::test_write_price_preserves_decimal_precision"
        status: pass
    human_judgment: false
  - id: D4
    description: "run_refresh survives arbitrary per-ticker failures (a middle ticker, all tickers, an empty taxonomy) without raising, and never merges or dedupes same-stage failures, preserving taxonomy iteration order"
    requirement: "STORE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_partial_failure_continues"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_all_tickers_fail_still_completes"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_duplicate_stage_failures_not_merged"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_failure_order_matches_taxonomy_order"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every run writes exactly one RefreshLog row, including a fully clean run (failure_count=0) and an empty taxonomy (tickers_attempted=0); the CLI entrypoint exits 0 even with per-ticker failures"
    requirement: "STORE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_all_succeed_writes_clean_refresh_log"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_empty_taxonomy_completes_with_zero_attempted"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_module_entrypoint_exits_0_with_partial_failures"
        status: pass
      - kind: integration
        ref: "manual command: DATABASE_URL=sqlite:///verify_full_refresh.db uv run python -m app.ingest.refresh (real 54-ticker sectors.yaml, live network) -> attempted=54 succeeded=54 failed=0, exit 0"
        status: pass
    human_judgment: false
  - id: D6
    description: "A commit-per-ticker design leaves already-processed tickers durably persisted even when a later ticker raises a BaseException that propagates out of run_refresh"
    requirement: "STORE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_interrupted_run_persists_completed_tickers"
        status: pass
    human_judgment: false
  - id: D7
    description: "GET /companies returns a populated price block (value/source/as_of, the later of two dated rows) for a ticker with price history, and null for a ticker with none, via a single bounded join query (no N+1) across the full 54-ticker taxonomy"
    requirement: "INGEST-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_companies_endpoint.py::test_companies_returns_later_price_when_two_rows_exist"
        status: pass
      - kind: integration
        ref: "backend/tests/test_companies_endpoint.py::test_companies_price_null_when_no_price_row_taxonomy_still_populated"
        status: pass
      - kind: integration
        ref: "backend/tests/test_companies_endpoint.py::test_companies_endpoint_query_count_is_bounded"
        status: pass
      - kind: integration
        ref: "manual command: GET /companies against verify_full_refresh.db -> 54/54 tickers priced"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-19
status: complete
---

# Phase 1 Plan 2: Price Ingestion Summary

**yfinance-backed daily close ingestion (`prices.py`) feeding a per-ticker-isolated refresh orchestrator (`refresh.py`) that populates `GET /companies`' price block end to end — live-verified against all 54 real tickers.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-19T15:05:00-04:00 (approx.)
- **Completed:** 2026-07-19T15:20:00-04:00 (approx.)
- **Tasks:** 3
- **Files modified:** 6 (2 created app modules, 2 created test files, 2 modified: `app/api/companies.py`, `tests/test_companies_endpoint.py`)

## Accomplishments

- `fetch_prices`/`fetch_price` (`backend/app/ingest/prices.py`) batch `yfinance.download()` over the ticker list, normalize the library's flat-vs-MultiIndex column shapes into one `PriceRow` type, and bound retries at 3 attempts with jittered exponential backoff (T-01-06/T-01-07)
- `write_price` upserts on the `(ticker, as_of)` unique key — same-day reruns update in place, new days create new rows — and preserves full source Decimal precision through the round trip
- `run_refresh` (`backend/app/ingest/refresh.py`) iterates the full taxonomy, isolates every per-ticker price failure in its own try/except (never aborting the batch), commits per ticker for interrupt durability, and writes exactly one `RefreshLog` row every run including fully clean ones
- `python -m app.ingest.refresh [taxonomy_path]` CLI entrypoint always exits 0 on a completed run, reserving non-zero for genuine orchestration failures
- `GET /companies` now joins each ticker's latest `Price` via a single bounded (max-as_of-subquery) join — proven with a query-count assertion, no N+1
- Live end-to-end verification: `python -m app.ingest.refresh` against the real 54-ticker `sectors.yaml` completed with `attempted=54 succeeded=54 failed=0`, and the subsequent `GET /companies` call returned all 54 tickers priced

## Task Commits

Each task followed a compressed TDD flow (tests committed first, implementation second):

1. **Task 1: Price fetcher** - `2ee953b` (test, RED) / `1f75d4a` (feat, GREEN) / `82d1d22` (fix — `multi_level_index=False` correction, found during Task 2's live smoke test)
2. **Task 2: Refresh orchestrator** - `0504b04` (test, RED) / `965f087` (feat, GREEN)
3. **Task 3: GET /companies price join** - `85f735a` (feat)

**Plan metadata:** commit pending (this SUMMARY + STATE.md/ROADMAP.md update)

## Files Created/Modified

- `backend/app/ingest/prices.py` - `PriceRow`, `NoPriceDataError`, `fetch_prices`, `fetch_price` (tenacity-retried), `write_price` (upsert on `uq_price_ticker_date`)
- `backend/app/ingest/refresh.py` - `TickerFailure`, `RefreshResult`, `record_failure`, `persist_refresh_log`, `run_refresh`, `_main` CLI entrypoint
- `backend/app/api/companies.py` - `list_companies` now joins latest `Price` per ticker via a `select()` + subquery, no `session.query()` legacy style
- `backend/tests/test_prices.py` - 10 tests, all mocked (no live network)
- `backend/tests/test_refresh.py` - 10 tests, `fetch_price` mocked at the refresh module's import site
- `backend/tests/test_companies_endpoint.py` - original plan-01 test left unmodified; 3 new tests for later-price selection, null-price completeness, and bounded query count

## Decisions Made

- **`multi_level_index=False` required for the documented shape split:** Verified live against the installed yfinance 1.5.1 that the library's default (`multi_level_index=True`) returns MultiIndex columns even for a 1-item ticker list — the plan's action text assumed the default already produced flat columns for a single ticker. Passing `multi_level_index=False` explicitly is what makes the dual-branch normalization in `_extract_row` exercise both real shapes in production. Documented as a deviation below.
- **`fetch_price` delegates to `fetch_prices([ticker])`:** rather than a separate implementation, so the batch and per-ticker code paths share one normalization function and one set of column-shape assumptions.
- **CLI accepts an optional taxonomy path override:** `python -m app.ingest.refresh [taxonomy_path]` defaults to `backend/sectors.yaml` (Coolify's real invocation) but accepts an override for scratch/fixture verification — used to live-test the unresolvable-ticker exit-0 contract without touching the real taxonomy file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `yf.download()` needs `multi_level_index=False` to actually produce the single-vs-multi shape split**
- **Found during:** Task 2 (live smoke-testing `fetch_prices`/`fetch_price` against real yfinance before wiring the orchestrator)
- **Issue:** The plan's action text states yfinance.download() "returns a differently-shaped DataFrame for a single ticker (flat columns) than for multiple tickers (MultiIndex columns)" without specifying a parameter. Verified live against the installed yfinance 1.5.1 that this is only true with `multi_level_index=False`; the library's own default (`multi_level_index=True`) returns MultiIndex columns for a 1-item ticker list too, which would have made the flat-column branch in `_extract_row` unreachable dead code in production despite being covered by mocked unit tests.
- **Fix:** Added `multi_level_index=False` to the `yf.download()` call in `fetch_prices`.
- **Files modified:** `backend/app/ingest/prices.py`
- **Verification:** Live call `fetch_prices(['NVDA','TSM'])` and `fetch_price('NVDA')` both return correctly normalized `PriceRow`s against real network data; unit tests unaffected (they mock `yf.download`'s return value directly, independent of the parameter).
- **Committed in:** `82d1d22`

---

**Total deviations:** 1 auto-fixed (1 bug, discovered via live verification against real yfinance behavior rather than assumed from the plan's prose)
**Impact on plan:** Necessary for the single-vs-multi normalization design (an explicit `<behavior>` bullet in Task 1) to actually hold against the real installed dependency version, not just against unit test mocks. No scope creep.

## Issues Encountered

None beyond the yfinance shape-parameter deviation documented above.

## User Setup Required

None - no new external service configuration required. `EDGAR_USER_AGENT` remains the only owner-supplied env var, already documented in `.env.example` per plan 01.

## Next Phase Readiness

- `GET /companies`'s price block is real and live-verified against all 54 tickers; the response contract shape is unchanged from plan 01 (D-07/D-08 held).
- The per-ticker failure-isolation pattern in `run_refresh` (broad except + continue + commit-per-ticker + always-write-RefreshLog) is the template plan 04's fundamentals ingestion reuses per the plan's own stated purpose.
- `python -m app.ingest.refresh` is the real orchestrator Coolify's scheduled task (plan 05) will invoke via `docker exec backend python -m app.ingest.refresh` — it supersedes plan 01's container-startup taxonomy-only seed stand-in (still present in the Dockerfile CMD; not yet wired to also call the price refresh — that wiring is plan 05's concern per the roadmap).
- No blockers.

---
*Phase: 01-data-foundation-taxonomy-ingestion-deployment*
*Completed: 2026-07-19*
