---
phase: 01-data-foundation-taxonomy-ingestion-deployment
plan: 04
subsystem: infra
tags: [sqlalchemy, sqlite, postgres, decimal, point-in-time, ingestion, api]

# Dependency graph
requires:
  - phase: 01-02
    provides: "Price model rows (the close series market cap is derived against), run_refresh per-ticker loop, TickerFailure/record_failure"
  - phase: 01-03
    provides: "extract_fundamentals/FactRow, resolve_cik/CikNotFoundError, get_companyfacts"
provides:
  - "app.ingest.fundamentals.find_nearest_close / compute_market_cap — Decimal market-cap derivation from shares outstanding and the nearest ingested close, null (never zero) when uncomputable"
  - "app.ingest.fundamentals.write_fundamentals — dialect-agnostic insert-or-ignore on the four-column point-in-time key"
  - "app.ingest.refresh.run_refresh — fundamentals stage inside the same per-ticker loop, failing independently of the price stage, with 'cik' and 'fundamentals' failure stages"
  - "GET /companies — full multi-year fundamentals history with per-filing provenance"
affects: ["01-05", "02", "04"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dialect-selected on-conflict construct (sqlalchemy.dialects.{sqlite,postgresql}.insert) chosen from session.get_bind().dialect.name, so the same persistence code path runs unmodified on both databases — STORE-01's DATABASE_URL-swap premise held in code rather than asserted in prose"
    - "index_elements (not constraint=) as the conflict-target spelling — the one form both the sqlite and postgresql dialects accept identically; sqlite's on_conflict_do_nothing() has no constraint= kwarg at all"
    - "Decimal-only arithmetic for money derived from large integer share counts — no float anywhere in the market-cap path, and no rounding at ingest (rounding is a presentation concern)"
    - "Null-not-zero as the honest representation of an uncomputable derived figure — a zero market cap would make a company look free in every downstream screen"

key-files:
  created: []
  modified:
    - backend/app/ingest/fundamentals.py
    - backend/app/ingest/refresh.py
    - backend/app/api/companies.py
    - backend/tests/test_fundamentals.py
    - backend/tests/test_refresh.py
    - backend/tests/test_companies_endpoint.py

key-decisions:
  - "Insert-or-ignore on (ticker, fiscal_year, fiscal_period, accession_number), never on-conflict-update — a restatement arrives under a new accession number and must insert alongside the original, preserving both figures; on-conflict-update would destroy the very history point-in-time storage exists to keep (T-01-15, T-01-16)"
  - "Market cap computed as shares outstanding x nearest close in Decimal, because no market-cap concept exists in either XBRL taxonomy; dei:EntityPublicFloat is explicitly NOT substituted — it is reported once a year, as of a non-period-end date, and excludes affiliate-held shares, so it is a materially different figure that would skew every Phase 4 valuation comparison"
  - "compute_market_cap returns None rather than 0 when no close is available within the ingested series (T-01-17)"
  - "Fundamentals live in the SAME per-ticker loop as prices, not a second pass — a second pass would double wall-clock time and split the failure log across two conceptual runs"
  - "Price and fundamentals stages fail independently: a ticker whose price fetch failed still gets its fundamentals attempted, and vice versa — coupling them would let one flaky provider silently halve the data collected from the other"
  - "Commit per ticker after both stages, so an interrupted run leaves every already-processed ticker durably persisted and a re-run completes the remainder without duplication (guaranteed by the insert-or-ignore semantics)"

patterns-established:
  - "Point-in-time financial persistence: any table storing filed figures keys on the filing's accession number alongside the period, and writes insert-or-ignore — never update-by-ticker, which flattens history to one row per company"
  - "Derived monetary values use Decimal end to end and persist at full source precision into Numeric columns; no ingest-time rounding"

requirements-completed: [INGEST-02, STORE-01, STORE-02]

coverage:
  - id: D1
    description: "Market cap is derived as shares outstanding times the close nearest the shares figure's as-of date, in exact Decimal arithmetic with no float drift and no ingest-time rounding"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_find_nearest_close_picks_smaller_absolute_distance"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_compute_market_cap_is_exact_decimal_no_float_drift"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_extract_fundamentals_populates_market_cap_end_to_end"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_no_ingest_time_rounding_in_fundamentals_module"
        status: pass
    human_judgment: false
  - id: D2
    description: "A filing whose shares as-of date has no price in the ingested series yields a null market cap rather than a fabricated or zero value, and EntityPublicFloat is never substituted"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_find_nearest_close_returns_none_with_no_price_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_compute_market_cap_null_not_zero_when_no_price"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_no_entity_public_float_substitution_in_fundamentals_module"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fundamentals persist one row per (ticker, fiscal_year, fiscal_period, accession_number); re-runs insert no duplicates, and a restatement under a new accession number inserts as an additional row preserving both figures"
    requirement: "STORE-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_write_fundamentals_twice_with_identical_rows_leaves_count_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_write_fundamentals_restatement_new_accession_inserts_additional_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_write_fundamentals_differing_fiscal_period_inserts_additional_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_refresh_twice_produces_identical_fundamentals_row_count"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_history_grows_beyond_three_rows_for_at_least_one_ticker"
        status: pass
    human_judgment: false
  - id: D4
    description: "Fundamentals failures are isolated per ticker and per stage; price and fundamentals stages fail independently; an unresolvable CIK is logged at stage 'cik' and skips only the fundamentals stage; an interrupted run leaves processed tickers durably committed"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_fundamentals_stage_isolated_middle_ticker_failure"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_price_failure_does_not_block_fundamentals"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_fundamentals_failure_does_not_block_price"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_cik_failure_records_stage_and_skips_only_fundamentals"
        status: pass
      - kind: unit
        ref: "backend/tests/test_refresh.py::test_interrupted_run_persists_completed_tickers_fundamentals"
        status: pass
    human_judgment: false
  - id: D5
    description: "GET /companies returns the full multi-year fundamentals array per company with provenance, empty for uningested tickers, in a stable order disambiguated by filed date then accession number, within a bounded query count"
    requirement: "STORE-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_returns_full_multi_year_fundamentals_history"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_fundamentals_entries_carry_provenance"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_empty_fundamentals_array_when_uningested"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_fundamentals_order_stable_across_requests"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_restatement_disambiguated_in_deterministic_order"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_endpoint_query_count_is_bounded"
        status: pass
      - kind: unit
        ref: "backend/tests/test_companies_endpoint.py::test_companies_endpoint_has_exactly_one_route"
        status: pass
    human_judgment: false

# Metrics
duration: 35min
completed: 2026-07-19
status: complete
---

# Phase 1 Plan 4: Fundamentals Persistence, Market Cap & API History Summary

**Market cap derived in exact Decimal from shares outstanding and the nearest ingested close, fundamentals persisted insert-or-ignore under the four-column point-in-time key, wired into the same resilient per-ticker refresh loop as prices, and the full multi-year history surfaced through `GET /companies`.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-19
- **Tasks:** 3
- **Files modified:** 6 (3 app modules, 3 test files)
- **Test suite:** 57 -> 80 passing

## Accomplishments

- `find_nearest_close(session, ticker, as_of)` selects the `Price` row with the smallest absolute date distance, with the ordering pushed into the query rather than loading the series into Python; returns `None` when the ticker has no price rows at all
- `compute_market_cap(shares_entry, session, ticker)` multiplies the shares figure by that nearest close in `Decimal`, returning `None` — never `0` — when no close is available (T-01-17). No rounding is applied at ingest; the stored value is the full-precision product
- `dei:EntityPublicFloat` is explicitly rejected as a market-cap substitute and verified absent from the module by test
- `write_fundamentals(session, ticker, rows)` persists with on-conflict-do-nothing against the `(ticker, fiscal_year, fiscal_period, accession_number)` key, selecting the sqlite or postgresql `insert` construct from the bound engine's dialect so the same code path runs on both databases (STORE-01)
- `run_refresh` gained a fundamentals stage **inside** the existing per-ticker loop from plan 02 — one pass over tickers, verified by test (`grep -c 'for .* in .*tickers'` == 1). CIK resolution failures record at stage `"cik"` and skip only fundamentals; fetch/extract/write failures record at stage `"fundamentals"`; both are independent of the `"price"` stage
- `list_companies` now returns every stored `Fundamental` row per ticker — the complete ingested history, not a latest-only filter — ordered ascending by `(period_end, filed_date, accession_number)` so originals and restatements sharing a fiscal year/period are totally ordered and stable across requests
- The endpoint serves 56 tickers with fundamentals within a bounded query count (no N+1), asserted by test

## Task Commits

1. **Task 1: Market cap derivation** — `6198aa9`
2. **Task 2: Point-in-time persistence + refresh integration** — `23ff713`
3. **Task 3: Multi-year history through GET /companies** — `0bd4607`

**Plan metadata:** this SUMMARY + STATE.md/ROADMAP.md update

## Files Created/Modified

- `backend/app/ingest/fundamentals.py` — added `find_nearest_close`, `compute_market_cap`, `write_fundamentals`; `extract_fundamentals` now populates `market_cap` and takes a session parameter
- `backend/app/ingest/refresh.py` — fundamentals + CIK stages added to the per-ticker loop, per-ticker commit
- `backend/app/api/companies.py` — fundamentals array populated, bounded-query fetch, total ordering
- `backend/tests/test_fundamentals.py` — 22 tests (plan 03's 15 plus 7 for market-cap derivation)
- `backend/tests/test_refresh.py` — 20 tests (plan 02's 10 plus 10 for persistence and stage isolation)
- `backend/tests/test_companies_endpoint.py` — 10 tests (6 new for fundamentals history)

## Decisions Made

- **`index_elements` rather than `constraint=` as the conflict target:** it is the one spelling both dialects accept identically — sqlite's `on_conflict_do_nothing()` has no `constraint=` keyword at all. Naming the constraint would have compiled on Postgres and failed on the MVP's actual database.
- **`extract_fundamentals` takes the session as a parameter** rather than opening one internally, so the extraction module stays testable and the caller owns transaction scope.
- **Per-ticker commit rather than one commit at the end of the run:** an interrupted 54-ticker run leaves every completed ticker durably persisted, and the insert-or-ignore semantics make the re-run that completes the remainder free of duplicates.

## Deviations from Plan

None. All three tasks were implemented as specified.

## Issues Encountered

- The executor agent for this plan was terminated twice by transient API stream timeouts. The first attempt did no work (clean tree, no commits). The second attempt committed all three tasks successfully but was cut off before writing this SUMMARY and updating tracking files — this SUMMARY was written during orchestrator closeout after verifying the committed work against the plan's acceptance criteria.
- `uv` is not resolvable on PATH in this environment; `backend/.venv/Scripts/python.exe -m pytest` was used directly (venv already synced from prior plans).

## Verification Status

**Automated (run and confirmed):**
- Full backend suite: 80 passed
- `EntityPublicFloat` occurrences in `fundamentals.py`: 0
- `round(` occurrences in `fundamentals.py`: 0
- ticker loops in `refresh.py`: 1
- route decorators in `companies.py`: 1

**Not run during closeout (deferred to phase verification):**
- The plan's `<verification>` block also lists live end-to-end checks — running `python -m app.ingest.refresh` twice against real EDGAR and confirming the fundamentals row count is unchanged, and `curl`ing the live endpoint to confirm a double-digit maximum fundamentals array with TSM (ifrs-full) and NVDA (us-gaap) both populated. These require the live stack and were **not** performed in this closeout. The idempotency and multi-year-history guarantees they check are covered behaviorally by `test_refresh_twice_produces_identical_fundamentals_row_count` and `test_history_grows_beyond_three_rows_for_at_least_one_ticker`, but the live confirmation remains outstanding.

## User Setup Required

None beyond `EDGAR_USER_AGENT`, already documented in `.env.example`.

## Next Phase Readiness

- The data pipeline is complete end to end locally: taxonomy -> prices -> CIK -> EDGAR fundamentals -> market cap -> point-in-time persistence -> `GET /companies`.
- Plan 05 (Coolify deploy + scheduled refresh) is the remaining work to make this live.
- Phase 2's company browser has its full data contract available from this endpoint.

---
*Phase: 01-data-foundation-taxonomy-ingestion-deployment*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 6 claimed files verified present on disk. All 3 claimed commit hashes (`6198aa9`, `23ff713`, `0bd4607`) verified present in git history. All referenced test names verified present in their claimed files. Test suite re-run at closeout: 80 passed.
