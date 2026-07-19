---
phase: 01-data-foundation-taxonomy-ingestion-deployment
plan: 01
subsystem: infra
tags: [fastapi, sqlalchemy, alembic, pydantic-settings, pyyaml, nextjs, docker-compose, uv]

# Dependency graph
requires: []
provides:
  - "backend/sectors.yaml — 54-ticker taxonomy across 10 sub-sectors, owner-editable"
  - "app.config.Settings — single typed config source (DATABASE_URL, EDGAR_USER_AGENT, BACKEND_URL)"
  - "app.models — five SQLAlchemy 2.0 models (Ticker, Price, Fundamental, TickerCik, RefreshLog) with point-in-time Fundamental unique key"
  - "app.ingest.taxonomy — load_taxonomy/sync_taxonomy (TAXO-01) plus a container-startup seed entrypoint"
  - "GET /companies and GET /health FastAPI endpoints (D-08 nested response contract)"
  - "Alembic migration history with render_as_batch=True from the first migration"
  - "frontend status page (Server Component) consuming GET /companies"
  - "docker-compose.yml two-service stack (backend, frontend), both Dockerfiles"
affects: ["01-02", "01-03", "01-04", "01-05"]

# Tech tracking
tech-stack:
  added: [fastapi==0.139.2, "sqlalchemy>=2.0,<2.1"==2.0.51, alembic==1.18.5, pydantic-settings==2.14.2, pyyaml==6.0.3, yfinance==1.5.1, tenacity==9.1.4, httpx==0.28.1, uvicorn==0.51.0, ruff, pytest, pytest-mock, respx, uv, "next==16.2.10", react==19.2.4, tailwindcss==4]
  patterns:
    - "Sync FastAPI routes + sync SQLAlchemy (no async) per CLAUDE.md's locked stack decision"
    - "Pydantic response schemas (app/api/companies.py) kept separate from SQLAlchemy models (app/models.py) — provenance columns not forced into API responses"
    - "Point-in-time fundamentals: unique key on (ticker, fiscal_year, fiscal_period, accession_number), insert-or-ignore, never upsert-by-ticker"
    - "Cached get_settings()/get_engine()/get_session_factory() (functools.lru_cache) with explicit .cache_clear() for test isolation"
    - "yaml.safe_load exclusively for owner-editable config; pydantic extra=\"forbid\" for loud validation errors"

key-files:
  created:
    - backend/sectors.yaml
    - backend/app/config.py
    - backend/app/db.py
    - backend/app/models.py
    - backend/app/ingest/taxonomy.py
    - backend/app/api/companies.py
    - backend/app/main.py
    - backend/alembic/env.py
    - backend/alembic/versions/0001_initial_schema.py
    - backend/Dockerfile
    - frontend/app/page.tsx
    - frontend/app/layout.tsx
    - frontend/Dockerfile
    - docker-compose.yml
    - .env.example
    - .gitignore
  modified: []

key-decisions:
  - "Ticker universe is 54, not the ~56 estimated pre-verification — the freshly-verified data-center-value-chain-tickers.md (D-01, dated same-day) lists exactly 54 unique tickers across 10 sub-sectors; sectors.yaml and all tests/acceptance checks use the actual verified count"
  - "Both backend (8000) and frontend (3000) ports are published in docker-compose.yml for local docker-compose smoke testing; Coolify's actual internet exposure is controlled separately via per-service domain assignment (plan 05), not by a compose ports: declaration"
  - "Added a minimal app.ingest.taxonomy._main() container-startup entrypoint (python -m app.ingest.taxonomy, run from the Dockerfile CMD before uvicorn) so docker compose up --build alone seeds sectors.yaml into the DB — required for the phase's own docker-compose smoke test (GET /companies returning 54 entries) and D-07/D-08's full-stack proof to hold without a separate manual step; superseded by the full app.ingest.refresh orchestrator in plan 02"
  - "uv run --no-sync used in the backend Dockerfile CMD (alembic upgrade, taxonomy seed, uvicorn) — without it, uv run re-syncs the project including dev dependencies on every container start, adding unnecessary network dependency and startup latency"
  - "Status page count line renders as a single template-literal text node (not adjacent JSX expressions) so the raw HTML contains the literal contiguous substring \"{count} companies tracked\" — React inserts hydration comment markers between separate adjacent expression children, which broke the plan's own grep-based acceptance check"

patterns-established:
  - "Config: all env vars flow through app.config.get_settings() — no scattered os.environ access"
  - "DB access: get_db() FastAPI dependency + cached engine/session-factory, database-agnostic (no SQLite-only constructs) so the Postgres DATABASE_URL swap needs no code change"
  - "Alembic: render_as_batch=True set in both online and offline paths from migration 0001 onward"

requirements-completed: [TAXO-01, STORE-01, DEPLOY-01]

coverage:
  - id: D1
    description: "backend/sectors.yaml holds all 54 verified tickers across 10 sub-sectors; owner can edit a ticker's sub_sector and the next sync reflects it with zero code changes"
    requirement: "TAXO-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_taxonomy.py::test_load_sectors_yaml"
        status: pass
      - kind: unit
        ref: "backend/tests/test_taxonomy.py::test_sync_taxonomy_updates_changed_sub_sector_without_deleting_others"
        status: pass
      - kind: unit
        ref: "backend/tests/test_taxonomy.py::test_sync_taxonomy_is_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "Malformed sectors.yaml (missing required field or unrecognized field) fails loudly with a pydantic ValidationError naming the offending field, not a bare KeyError"
    requirement: "TAXO-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_taxonomy.py::test_load_taxonomy_missing_required_field_raises"
        status: pass
      - kind: unit
        ref: "backend/tests/test_taxonomy.py::test_load_taxonomy_unrecognized_field_raises"
        status: pass
    human_judgment: false
  - id: D3
    description: "Five SQLAlchemy 2.0 typed models persist to SQLite; Fundamental's point-in-time unique constraint (ticker, fiscal_year, fiscal_period, accession_number) blocks exact duplicates while allowing a new accession number as a second row"
    requirement: "STORE-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_models.py::test_crud_roundtrip"
        status: pass
      - kind: unit
        ref: "backend/tests/test_models.py::test_fundamental_unique_constraint_blocks_exact_duplicate"
        status: pass
    human_judgment: false
  - id: D4
    description: "Alembic migrates a fresh SQLite file cleanly with render_as_batch=True configured from the first migration, creating all five tables plus both named unique constraints"
    requirement: "STORE-01"
    verification:
      - kind: integration
        ref: "cd backend && DATABASE_URL=sqlite:///verify_fresh.db uv run alembic upgrade head (manual command, exit 0)"
        status: pass
    human_judgment: false
  - id: D5
    description: "GET /companies returns the D-08 nested taxonomy/price/fundamentals shape for every tracked ticker (price=null, fundamentals=[] this plan)"
    requirement: "STORE-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_companies_endpoint.py::test_companies_returns_full_taxonomy"
        status: pass
    human_judgment: false
  - id: D6
    description: "docker compose up --build brings up backend + frontend together; the status page renders the live company count (54) fetched server-side from the backend, with no client-visible loading spinner"
    requirement: "DEPLOY-01"
    verification:
      - kind: e2e
        ref: "manual command: docker compose up --build -d && curl -sf http://localhost:8000/companies (54 entries) && curl -sf http://localhost:3000 | grep '54 companies tracked'"
        status: pass
    human_judgment: false
  - id: D7
    description: "Status page degrades to the 'API unreachable' error copy (with retry-by-refresh instruction) when the backend is down, without a Next.js error overlay or a hanging request"
    requirement: "DEPLOY-01"
    verification:
      - kind: e2e
        ref: "manual command: docker compose stop backend && curl -sf http://localhost:3000 (200, contains 'API unreachable') && docker compose start backend"
        status: pass
    human_judgment: false
  - id: D8
    description: "docker-compose.yml declares exactly two services, no db container, and no hardcoded secrets (DATABASE_URL passes through ${} substitution)"
    requirement: "DEPLOY-01"
    verification:
      - kind: unit
        ref: "manual command: docker compose config --services | wc -l == 2; grep -c 'DATABASE_URL=\\${' docker-compose.yml == 1"
        status: pass
    human_judgment: false

# Metrics
duration: 1h30m
completed: 2026-07-19
status: complete
---

# Phase 1 Plan 1: Walking Skeleton Summary

**FastAPI + SQLAlchemy 2.0 + Alembic backend serving a taxonomy-driven `GET /companies`, a Next.js 16 Server Component status page, and a two-service docker-compose stack that seeds all 54 tickers on `docker compose up --build`.**

## Performance

- **Duration:** ~1h 30m
- **Started:** 2026-07-19T11:30:00-04:00 (approx.)
- **Completed:** 2026-07-19T13:05:00-04:00 (approx.)
- **Tasks:** 3
- **Files modified:** 50 (14,379 insertions)

## Accomplishments

- `backend/sectors.yaml` transcribes all 54 verified tickers across 10 sub-sectors (D-03/D-04/D-05/D-06); `load_taxonomy`/`sync_taxonomy` prove TAXO-01's owner-editable, zero-code-change round trip
- Five-model SQLAlchemy 2.0 schema (`Ticker`, `Price`, `Fundamental`, `TickerCik`, `RefreshLog`) with the point-in-time `Fundamental` unique key (`ticker`, `fiscal_year`, `fiscal_period`, `accession_number`) that later plans depend on to never lose filing history on re-run
- Alembic configured with `render_as_batch=True` from migration `0001_initial_schema` (both online and offline paths), verified against a fresh SQLite file
- `GET /companies` (D-08 nested shape) and `GET /health`, both sync routes, with a global exception handler that never leaks stack traces (T-01-04)
- Next.js 16 App Router status page: async Server Component, 5s `AbortSignal.timeout`, three states (error/empty/healthy) matching UI-SPEC copy and color tokens exactly, no client-side JS, no component library
- Two-service `docker-compose.yml` (no `db` container), both Dockerfiles, backend self-migrates and self-seeds the taxonomy on startup
- Live-verified end to end: `docker compose up --build` → `GET /companies` returns 54 entries → status page renders "54 companies tracked" with the green healthy indicator → stopping the backend degrades the page to "API unreachable" without a crash or hang

## Task Commits

Each task was committed atomically (Task 2 followed TDD: RED then GREEN):

1. **Task 1: Wave 0 — backend scaffold, test harness, failing E2E test** - `1f3c7da` (test)
2. **Task 2 RED: sectors.yaml + failing taxonomy/model tests** - `d3861b5` (test)
   **Task 2 GREEN: taxonomy sync, five-model schema, GET /companies** - `05745af` (feat)
3. **Task 3: Next.js status page and docker-compose** - `adac027` (feat)

**Plan metadata:** commit pending (this SUMMARY + STATE.md/ROADMAP.md update)

## Files Created/Modified

- `backend/sectors.yaml` - 54-ticker taxonomy, 10 sub-sectors, owner-editable
- `backend/app/config.py` - `Settings` (pydantic-settings), `get_settings()` cached accessor
- `backend/app/db.py` - cached `get_engine()`/`get_session_factory()`, `get_db()` FastAPI dependency
- `backend/app/models.py` - `Base` + `Ticker`/`Price`/`Fundamental`/`TickerCik`/`RefreshLog`, SQLAlchemy 2.0 `Mapped[]` idiom
- `backend/app/ingest/taxonomy.py` - `load_taxonomy`/`sync_taxonomy` (TAXO-01) + container-startup `_main()` seed entrypoint
- `backend/app/api/companies.py` - `GET /companies`, D-08 response schemas, sync route
- `backend/app/main.py` - FastAPI app, `GET /health`, global exception handler (T-01-04)
- `backend/alembic/env.py` - `render_as_batch=True`, imports `Base.metadata`, reads `DATABASE_URL` via `get_settings()`
- `backend/alembic/versions/0001_initial_schema.py` - all five tables, both named unique constraints
- `backend/Dockerfile` - `python:3.13-slim` + `uv`, frozen no-dev sync, `uv run --no-sync` startup, self-migrate + self-seed
- `frontend/app/page.tsx` - status page Server Component, three states per UI-SPEC
- `frontend/app/layout.tsx` - page metadata title "Data Center Stocks"
- `frontend/next.config.ts` - pinned `turbopack.root` (avoids stray-lockfile workspace misdetection)
- `frontend/Dockerfile` - multi-stage Node 22 build (deps/builder/runner)
- `docker-compose.yml` - two services, no `db`, `${VAR}` substitution only
- `.env.example` - documents `DATABASE_URL`/`EDGAR_USER_AGENT` with the EDGAR User-Agent rationale
- `.gitignore` - `.venv/`, `__pycache__/`, `.env`, `data/`, `*.db`, `node_modules/`, `.next/`
- `backend/tests/{conftest,test_taxonomy,test_models,test_companies_endpoint}.py` - 8 tests, all green
- `backend/tests/fixtures/{nvda,tsm}_companyfacts.json` - trimmed live EDGAR fixtures (us-gaap / ifrs-full, TWD+USD units preserved)

## Decisions Made

- **54 tickers, not 56:** `data-center-value-chain-tickers.md` (verified same-day per D-01) lists exactly 54 unique tickers across 10 sub-sectors, not the ~56 the plan's prose estimated pre-verification. Every count in `sectors.yaml`, the test suite, and the docker-compose smoke test uses 54 — the actual, authoritative source-of-truth count. This is documented as a deviation below since the PLAN.md text and acceptance-criteria examples hardcode "56" in several places.
- **Backend port published locally:** `docker-compose.yml` publishes both `8000:8000` (backend) and `3000:3000` (frontend), even though Task 3's action text describes the backend as having "no published port." The plan's own validation script (`01-VALIDATION.md`'s automated command for 01-01-T3) and Task 3's acceptance criteria both curl `localhost:8000` directly, which is unreachable without a published port. Publishing it locally doesn't change Coolify's actual internet-exposure model — that's controlled per-service by domain assignment in the Coolify UI (plan 05), not by a compose `ports:` declaration — so this doesn't weaken the T-01-02 threat disposition, which already accepts `GET /companies` being reachable.
- **Startup taxonomy seed added:** Task 3's acceptance criteria requires `GET /companies` to return all tickers immediately after `docker compose up --build`, but the action block never says to sync sectors.yaml at container startup (only "run `alembic upgrade head` on startup"). Added a minimal `python -m app.ingest.taxonomy` step to the Dockerfile CMD, run after the migration and before uvicorn. This is a stand-in for the full `app.ingest.refresh` orchestrator that plans 02-04 build out.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ticker universe is 54, not 56 — sectors.yaml and all test/acceptance counts use the verified figure**
- **Found during:** Task 2 (authoring `sectors.yaml`)
- **Issue:** PLAN.md's must-haves, D-05, and several acceptance-criteria examples state "~56 tickers" / assert `len(c)==56`. Counting `data-center-value-chain-tickers.md` (the canonical, same-day-verified source per D-01) yields exactly 54 unique tickers across the 10 declared sub-sectors — the PLAN's number was a pre-verification estimate that was never updated after D-01's verification pass.
- **Fix:** Authored `sectors.yaml` with all 54 tickers exactly as listed in the source file (no fabricated entries to hit 56). Wrote `test_load_sectors_yaml` and the E2E test to assert against the loaded count (`len(config.companies)`) rather than hardcoding either number, so the tests stay correct if the owner edits the list later. Verified the docker-compose smoke test against the real count (54).
- **Files modified:** `backend/sectors.yaml`, `backend/tests/test_taxonomy.py`, `backend/tests/test_companies_endpoint.py`
- **Verification:** `python -c "...len(c)==54..."` and equivalent 10-sub-sector check both pass; `GET /companies` returns 54 live entries via docker-compose
- **Committed in:** `d3861b5`, `05745af`, `adac027`

**2. [Rule 2 - Missing Critical] Container-startup taxonomy seed added so `docker compose up --build` alone proves TAXO-01/D-07**
- **Found during:** Task 3 (docker-compose smoke test)
- **Issue:** Without seeding, a fresh `docker compose up --build` produces an empty `tickers` table (`GET /companies` returns `[]`), failing Task 3's own acceptance criteria (`GET /companies` returning 54 entries, status page showing "54 companies tracked") and the phase's must-have truth ("the status page renders the live company count fetched server-side from the backend").
- **Fix:** Added `app.ingest.taxonomy._main()` (a `python -m app.ingest.taxonomy` CLI entrypoint) that loads and syncs `sectors.yaml` into the DB; wired into the backend `Dockerfile` CMD between the Alembic migration and uvicorn startup.
- **Files modified:** `backend/app/ingest/taxonomy.py`, `backend/Dockerfile`
- **Verification:** Fresh `docker compose up --build` (empty volume) → backend log shows "Synced 54 tickers from /app/sectors.yaml" → `GET /companies` returns 54 entries → status page renders "54 companies tracked"
- **Committed in:** `adac027`

**3. [Rule 1 - Bug] `uv run` re-syncing dev dependencies on every container start**
- **Found during:** Task 3 (first docker-compose smoke test)
- **Issue:** The Dockerfile CMD used plain `uv run alembic ...` / `uv run uvicorn ...`. Without `--no-sync`, `uv run` re-syncs the project against `pyproject.toml` on every invocation, which re-downloaded `ruff` (a dev-only dependency, ~10MB) on container start — unnecessary network dependency and startup latency in a container that was already frozen-synced at build time.
- **Fix:** Added `--no-sync` to all three `uv run` invocations in the CMD.
- **Files modified:** `backend/Dockerfile`
- **Verification:** Rebuilt and restarted the backend container; startup log no longer shows a `ruff` download, only the Alembic migration, taxonomy sync, and uvicorn boot lines
- **Committed in:** `adac027`

**4. [Rule 1 - Bug] Status page count line broken by React hydration comment markers**
- **Found during:** Task 3 (docker-compose smoke test, `grep -q '54 companies tracked'` acceptance check)
- **Issue:** The status page originally rendered the count number and the "companies tracked" text as two adjacent JSX expression children (`{state.count} {ternary}`). React inserts `<!-- -->` hydration boundary comments between adjacent dynamic text expressions, so the raw server-rendered HTML contained `54<!-- --> <!-- -->companies tracked` instead of a contiguous string — breaking the plan's own literal grep-based acceptance check.
- **Fix:** Changed to a single template-literal expression (`` {`${count} ${unit}`} ``) so React renders one text node with no comment markers in between.
- **Files modified:** `frontend/app/page.tsx`
- **Verification:** `curl -sf http://localhost:3100 | grep -o '54 companies tracked'` returns a match after the fix (failed before it)
- **Committed in:** `adac027`

**5. [Rule 1 - Bug] Unused `yaml` import in test_taxonomy.py**
- **Found during:** Task 2 (post-GREEN ruff check)
- **Issue:** `import yaml` was left in `test_taxonomy.py` after refactoring the assertions to go through `load_taxonomy` instead of parsing YAML directly in the test.
- **Fix:** Removed the unused import.
- **Files modified:** `backend/tests/test_taxonomy.py`
- **Verification:** `uv run ruff check app/ tests/` reports "All checks passed!"
- **Committed in:** `05745af`

**6. [Rule 1 - Bug] `next.config.ts` misdetecting workspace root**
- **Found during:** Task 3 (`npm run build`)
- **Issue:** Next.js 16's Turbopack build emitted a warning that it inferred the workspace root from a stray `package-lock.json` in the developer's home directory (outside this repo), which could cause incorrect build behavior in some environments.
- **Fix:** Pinned `turbopack.root` explicitly to `__dirname` in `next.config.ts`.
- **Files modified:** `frontend/next.config.ts`
- **Verification:** Rebuild no longer emits the workspace-root warning
- **Committed in:** `adac027`

---

**Total deviations:** 6 auto-fixed (1 blocking data-count correction, 1 missing-critical-functionality addition, 4 bugs)
**Impact on plan:** All auto-fixes were necessary for the plan's own acceptance criteria and success criteria to actually pass against real, verified data and real container behavior. No scope creep — no functionality was added beyond what Task 3's acceptance criteria already required.

## Issues Encountered

- Local dev machine had an unrelated project (`realstatefinder`) already publishing host ports 3000 and 8000, which collided with this plan's docker-compose smoke test. Resolved by temporarily remapping ports for verification only (`8100`/`3100`), then restoring the canonical `8000`/`3000` mapping in the committed `docker-compose.yml` before each commit — the committed file was never left with the temporary ports.
- `uv` was not on PATH at session start (`pip install uv` succeeded but the install location wasn't on PATH by default) — resolved by adding the pip user-scripts directory to PATH for each shell invocation that needed `uv`.

## User Setup Required

None - no external service configuration required for this plan. (SEC EDGAR fetches in plans 02-04 will need a real `EDGAR_USER_AGENT` value in the owner's actual `.env`/Coolify config — `.env.example` documents this.)

## Next Phase Readiness

- The full-stack skeleton is proven end to end: taxonomy config → DB → API → frontend → docker-compose, all live-verified.
- `GET /companies`'s response contract (`price: null`, `fundamentals: []`) is stable and ready for plans 02 (prices) and 03/04 (fundamentals) to populate without changing the shape.
- Alembic's `render_as_batch=True` is locked in from migration 0001, so later migrations (adding columns for CIK caching details, refresh_log fields, etc.) will apply cleanly on SQLite.
- No blockers. One open item for plan 02+: the Coolify scheduled-task cron (D-10/D-11, recommended `0 2 * * *` UTC) and the real `app.ingest.refresh` orchestrator are not yet built — this plan's container-startup taxonomy seed is an intentional, documented stand-in.

---
*Phase: 01-data-foundation-taxonomy-ingestion-deployment*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 16 claimed files verified present on disk. All 4 claimed commit hashes (`1f3c7da`, `d3861b5`, `05745af`, `adac027`) verified present in git history.
