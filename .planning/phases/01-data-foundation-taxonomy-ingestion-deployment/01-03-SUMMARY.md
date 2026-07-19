---
phase: 01-data-foundation-taxonomy-ingestion-deployment
plan: 03
subsystem: infra
tags: [httpx, tenacity, respx, sec-edgar, xbrl, ingestion]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Ticker/Fundamental/TickerCik models, app.config.Settings (edgar_user_agent), sectors.yaml taxonomy"
provides:
  - "app.ingest.edgar_client — shared httpx.Client with settings-sourced User-Agent, explicit timeout, bounded/selective retry, and request pacing under SEC's 10 req/sec limit"
  - "app.ingest.cik_resolver — resolve_cik with a persistent ticker_ciks cache, zero-padded to 10 digits, CikNotFoundError for unindexed tickers"
  - "app.ingest.fundamentals — pick_taxonomy/extract_concept/extract_fundamentals with full us-gaap/ifrs-full filer-type branching, live-verified against both NVDA and TSM"
affects: ["01-04", "01-05"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single lru_cache'd httpx.Client (get_edgar_client) shared across every EDGAR call, never a per-call header — the only way to guarantee no code path forgets the required User-Agent (T-01-10)"
    - "tenacity retry with a custom retry_if_exception predicate that excludes 404 explicitly — permanent per-ticker conditions must not consume the shared 3-attempt retry budget"
    - "In-run lru_cache (not a global mutable dict) for the fetched company_tickers.json mapping, matching the codebase's existing get_settings()/get_engine() cached-accessor pattern, with .cache_clear() for test isolation"
    - "Reduce-then-join grouping for XBRL facts: a single filing accession carries many duration facts (quarterly breakdowns, prior-year comparatives) sharing one (fiscal_year, fiscal_period, accession_number) context; the entry with the latest period end is that filing's own headline figure — reduce each concept to one headline entry per key, then join revenue/net_income/shares_outstanding across concepts on that key rather than zipping positionally"

key-files:
  created:
    - backend/app/ingest/edgar_client.py
    - backend/app/ingest/cik_resolver.py
    - backend/app/ingest/fundamentals.py
    - backend/tests/test_cik_resolver.py
    - backend/tests/test_fundamentals.py
  modified: []

key-decisions:
  - "Grouping key (fiscal_year, fiscal_period, accession_number) reduces to the entry with the MAX period-end date per key, not an arbitrary/first entry — verified this is required because real (not fixture-simplified) EDGAR companyfacts responses carry multiple duration facts (quarterly + annual + prior-year comparative) under the identical fy/fp/accn context; picking the max-end entry per group reproduces NVDA's and TSM's actual known historical annual figures exactly (e.g. NVDA FY2019-2022 revenue $11.72B/$10.92B/$16.68B/$26.91B, matching real filings)"
  - "Shares outstanding is sourced from dei:EntityCommonStockSharesOutstanding first (used by both filer types), falling back to CONCEPT_MAP's us-gaap-only CommonStockSharesOutstanding candidate only when dei is absent — matches RESEARCH.md's stated fallback intent for the ifrs-full branch, which has no shares candidates of its own"
  - "Entries missing fy, fp, or accn (a handful of un-tagged submission-type facts observed in real TSM/NVDA data) are silently skipped during extraction rather than raising — FactRow's provenance fields must be non-empty per the plan's own acceptance criteria, and an entry lacking a fiscal-year/period tag cannot satisfy that contract"
  - "History cutoff computed via date.replace(year=today.year - years) with a Feb-29 fallback to Feb-28, rather than a fixed 365*years day delta — gives an exact calendar-year boundary that closes cleanly at the cutoff, matching the plan's explicit closed-boundary requirement"

patterns-established:
  - "EDGAR requests: single shared, paced, retried httpx.Client (edgar_client.get_edgar_client()) is the only sanctioned way to call SEC EDGAR anywhere in this codebase — no ad hoc httpx.get() calls to sec.gov/data.sec.gov"
  - "XBRL concept extraction: ordered candidate-name fallback lists (CONCEPT_MAP) rather than a single hardcoded concept name, so a company's concept-name rename mid-history degrades to the next candidate instead of silently returning nothing"

requirements-completed: [INGEST-02]

coverage:
  - id: D1
    description: "A ticker's CIK resolves from SEC's company_tickers.json, zero-padded to exactly 10 digits (Apple's 320193 -> '0000320193'), cached in ticker_ciks so a second resolve makes zero network calls, and a ticker absent from the mapping raises CikNotFoundError rather than crashing or producing a malformed URL"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_resolve_cik_apple_zero_pads_to_ten_digits"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_resolve_cik_cache_hit_makes_zero_network_calls"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_resolve_cik_second_call_after_miss_issues_no_further_http"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_resolve_cik_missing_ticker_raises_cik_not_found"
        status: pass
      - kind: integration
        ref: "manual command: resolve_cik against live SEC endpoint for NVDA/TSM -> 0001045810 / 0001046179"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every EDGAR request carries a settings-sourced User-Agent, an explicit connect+read timeout, is retried with bounded exponential backoff on transport errors and 5xx/429 only (never on 404), and consecutive requests are paced under SEC's 10 req/sec limit"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_edgar_client_sends_user_agent_from_settings"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_edgar_client_has_explicit_connect_and_read_timeout"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_edgar_get_retries_5xx_then_succeeds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_edgar_get_404_is_not_retried"
        status: pass
      - kind: unit
        ref: "backend/tests/test_cik_resolver.py::test_edgar_get_exhausts_retry_budget_bounded_at_3"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both us-gaap (NVDA) and ifrs-full (TSM, representing the TSM/ASML/ARM/GDS/NBIS foreign-private-issuer branch) filers extract non-empty revenue and net income; a response with neither taxonomy raises UnknownTaxonomyError naming the taxonomies actually present"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_filer_type_branching"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_pick_taxonomy_neither_present_raises_naming_present_keys"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_unknown_taxonomy_raises_with_present_key_named"
        status: pass
      - kind: integration
        ref: "manual command: extract_fundamentals against live companyfacts for NVDA/TSM -> us-gaap 20 rows / ifrs-full 4 rows, both with non-empty revenue"
        status: pass
    human_judgment: false
  - id: D4
    description: "TSM's dual TWD/USD Revenue reporting extracts only the USD series; NVDA extraction spans at least 3 distinct fiscal years; a concept entirely absent from a response yields an empty list, never a fabricated zero"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_extract_concept_tsm_revenue_returns_only_usd_never_twd"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_tsm_extraction_never_includes_twd_revenue_values"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_nvda_extraction_spans_at_least_three_distinct_fiscal_years"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_extract_concept_absent_field_returns_empty_list"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_extract_concept_first_present_candidate_name_wins"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every extracted FactRow carries a non-empty accession_number, filed_date, fiscal_year, fiscal_period, and form; results are sorted ascending by (period_end, filed_date, accession_number) and stable across repeated calls; a filing at the history cutoff is included and one day before it is excluded"
    requirement: "INGEST-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_every_factrow_has_truthy_provenance"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_ordering_is_stable_across_repeated_calls"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_results_sorted_ascending_by_period_end_then_filed_then_accn"
        status: pass
      - kind: unit
        ref: "backend/tests/test_fundamentals.py::test_boundary_closed_at_cutoff_inclusive_day_before_excluded"
        status: pass
    human_judgment: false

# Metrics
duration: 45min
completed: 2026-07-19
status: complete
---

# Phase 1 Plan 3: SEC EDGAR Fundamentals Extraction Summary

**Hand-rolled `httpx` EDGAR client with settings-sourced User-Agent/timeout/pacing/retry, a persistent zero-padded CIK cache, and full us-gaap/ifrs-full filer-type branching that extracts multi-year revenue and net income correctly for both NVDA and TSM — live-verified against real SEC endpoints.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-19T15:25:00-04:00 (approx.)
- **Completed:** 2026-07-19T16:10:00-04:00 (approx.)
- **Tasks:** 2
- **Files modified:** 5 (3 created app modules, 2 created test files)

## Accomplishments

- `edgar_client.py`: a single shared, `lru_cache`'d `httpx.Client` with a settings-sourced User-Agent header (T-01-10), explicit `httpx.Timeout(10.0, connect=5.0)` (T-01-12), a monotonic-clock pacing guard (`EDGAR_MIN_REQUEST_INTERVAL`) keeping every outbound call under SEC's 10 req/sec limit (T-01-11), and a `tenacity` retry bounded at 3 attempts that retries transport errors/5xx/429 only — 404 is never retried, preserving rate-limit budget for other tickers
- `cik_resolver.py`: `resolve_cik` checks the `ticker_ciks` table first (zero network calls on a hit), else fetches/zero-pads `company_tickers.json` (Apple's `320193` -> `"0000320193"`, verified length-10) and persists; `CikNotFoundError` for tickers absent from the mapping; an in-run `lru_cache` so a cold multi-ticker run issues one mapping request, not one per ticker
- `fundamentals.py`: `pick_taxonomy` branches on the response's own keys (never a hardcoded `"us-gaap"` index) and raises `UnknownTaxonomyError` naming the taxonomies actually present; `extract_concept` walks ordered candidate-name fallback lists and filters explicitly to the requested unit, so TSM's dual TWD/USD `Revenue` reporting never lets TWD leak in as USD; `extract_fundamentals` reduces each concept's raw entries to one headline fact per `(fiscal_year, fiscal_period, accession_number)` filing (the max-period-end entry within that group), joins revenue/net_income/shares_outstanding across concepts on that key, applies a closed-at-cutoff multi-year history window, and returns results sorted ascending by `(period_end, filed_date, accession_number)`
- Live end-to-end verification against real SEC endpoints (not just fixtures): `resolve_cik` -> NVDA CIK `0001045810`, TSM CIK `0001046179`; `extract_fundamentals(years=5)` against live `companyfacts` returned 20 rows for NVDA (`us-gaap`, non-empty revenue) and 4 rows for TSM (`ifrs-full`, non-empty revenue)
- Extraction logic verified to reproduce NVDA's and TSM's actual known historical financials exactly (e.g. NVDA FY2019-2022 revenue $11.72B/$10.92B/$16.68B/$26.91B; TSM FY2017-2024 revenue $32.98B rising to $88.27B) — confirms the max-period-end-per-filing grouping heuristic is correct, not just internally consistent

## Task Commits

Each task followed a compressed TDD flow (tests committed first, implementation second):

1. **Task 1: CIK resolution + EDGAR client** - `5110506` (test) / `7ddeb89` (feat)
2. **Task 2: Filer-type branching + fundamentals extraction** - `b2ff8da` (test) / `fc5a888` (feat)

**Plan metadata:** commit pending (this SUMMARY + STATE.md/ROADMAP.md update)

## Files Created/Modified

- `backend/app/ingest/edgar_client.py` - `get_edgar_client`, `edgar_get`, `get_companyfacts`, `EDGAR_MIN_REQUEST_INTERVAL`, `_is_retryable_error`
- `backend/app/ingest/cik_resolver.py` - `resolve_cik`, `fetch_company_tickers_json`, `persist_cik_cache`, `CikNotFoundError`
- `backend/app/ingest/fundamentals.py` - `CONCEPT_MAP`, `pick_taxonomy`, `extract_concept`, `extract_fundamentals`, `FactRow`, `UnknownTaxonomyError`
- `backend/tests/test_cik_resolver.py` - 11 tests, all `respx`-mocked (no live network in the test suite itself)
- `backend/tests/test_fundamentals.py` - 15 tests, all against recorded NVDA/TSM fixtures

## Decisions Made

- **Max-period-end-per-(fy,fp,accn) grouping, not a first-wins or last-wins pick:** real EDGAR `companyfacts` responses carry many duration facts (quarterly breakdowns, prior-year comparative restatements) sharing the identical fiscal-year/fiscal-period/accession context — this is genuine EDGAR behavior verified against both fixtures, not a fixture-trimming artifact. Reducing each group to the entry with the latest `end` date is what correctly isolates each filing's own headline annual (or current-quarter, for a 10-Q) figure. Verified this reproduces NVDA's and TSM's real, known historical revenue figures exactly across every fiscal year checked.
- **Shares outstanding sourced from `dei` first, `us-gaap` fallback only:** matches RESEARCH.md's stated design (`ifrs-full` has no shares candidates of its own since foreign filers report via the shared `dei:EntityCommonStockSharesOutstanding` tag).
- **Entries missing `fy`/`fp`/`accn` are skipped, not errored:** a small number of real EDGAR facts (observed in both fixtures) carry no fiscal-year/period tag at all (e.g. certain 6-K-adjacent submissions). Since `FactRow`'s provenance fields must be non-empty per this plan's own acceptance criteria, these untagged entries cannot produce a valid row and are silently excluded rather than raising or fabricating placeholder provenance.
- **Calendar-year cutoff via `date.replace(year=...)` with a Feb-29 fallback:** gives an exact, closed-at-the-boundary cutoff date rather than an approximate `365*years`-day delta, matching the plan's explicit "closed at the cutoff" boundary requirement precisely.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Literal `(fy, fp, accn)` grouping as described in the plan's action text would silently conflate multiple distinct financial periods into one FactRow**
- **Found during:** Task 2 (validating extraction against the real NVDA/TSM fixtures before writing tests)
- **Issue:** The plan's action text describes grouping revenue/net-income entries by `(fy, fp, accn)` alone and joining them onto one FactRow. Live-recorded EDGAR data shows a single accession routinely contains 2-6+ duration facts for the same concept sharing that exact key (annual totals, prior-year comparatives, and quarterly breakdowns all tagged with the filing's own fy/fp). Grouping on that key alone, with no tiebreak, would pick an arbitrary (whichever-iterated-last) entry per group — for NVDA this would non-deterministically mix a $6.91B one-year-old comparative figure with the filing's actual $11.72B current-year figure, silently corrupting every downstream relative-value comparison (directly the class of bug T-01-13 was written to prevent).
- **Fix:** Added an explicit reduction step (`_reduce_to_headline_per_filing`) that keeps, within each `(fy, fp, accn)` group, only the entry with the maximum `end` (period-end) date — the filing's own headline period. Verified this choice against real known NVDA/TSM historical financials (see Decisions Made) rather than assuming it was correct.
- **Files modified:** `backend/app/ingest/fundamentals.py`
- **Verification:** `extract_fundamentals` against both fixtures reproduces exact, correct, real historical revenue/net-income figures for every fiscal year checked; `test_ordering_is_stable_across_repeated_calls` and `test_boundary_closed_at_cutoff_inclusive_day_before_excluded` pass; live spot-check against real SEC data also confirmed correct.
- **Committed in:** `fc5a888`

---

**Total deviations:** 1 auto-fixed (1 bug, discovered via validation against real fixture data structure rather than the plan's simplified prose description)
**Impact on plan:** Necessary for the phase's own stated highest-risk requirement (correct filer-type/period extraction) to actually hold against real EDGAR data rather than an idealized one-fact-per-filing model. No scope creep — same public function signatures and CONCEPT_MAP the plan specified.

## Issues Encountered

- `uv` was not resolvable on PATH in this shell session; used the already-provisioned `backend/.venv/Scripts/python.exe` directly for `pytest`/`ruff` invocations instead (the venv was already synced with all dependencies from plans 01/02, so no re-install was needed).

## User Setup Required

None - no new external service configuration required. `EDGAR_USER_AGENT` (already documented in `.env.example` per plan 01) is the only owner-supplied value this plan depends on; live verification in this session used a temporary override value for spot-checking only, never written to `.env`.

## Next Phase Readiness

- `edgar_client.py`, `cik_resolver.py`, and `fundamentals.py` are ready for plan 04 to wire into the refresh orchestrator (persistence + market-cap derivation from the price series, per this plan's stated scope boundary).
- The filer-type branch is proven correct against real, live SEC data for one filer of each type in this ticker universe (NVDA/us-gaap, TSM/ifrs-full) — ASML, ARM, GDS, and NBIS all share TSM's ifrs-full code path with no additional branching needed.
- No blockers.

---
*Phase: 01-data-foundation-taxonomy-ingestion-deployment*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 5 claimed files verified present on disk. All 4 claimed commit hashes (`5110506`, `7ddeb89`, `b2ff8da`, `fc5a888`) verified present in git history.
