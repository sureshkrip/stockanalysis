# Project Research Summary

**Project:** Data Center Stocks (personal sector research/screening tool)
**Domain:** Personal financial data ingestion + relative-value screening dashboard (self-hosted, single-user)
**Researched:** 2026-07-19
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a personal, single-user financial research tool: a scheduled batch pipeline pulls daily prices and SEC EDGAR fundamentals for ~55 data-center-value-chain tickers, stores them in a normalized store, computes valuation ratios and relative-value screens on read, and serves a Next.js dashboard grouped by a hand-curated sub-sector taxonomy. This is not a generic screener — the entire value proposition is judging each company against its actual peer group (a custom 9-sub-sector taxonomy no off-the-shelf GICS-based tool offers), not the whole market. The recommended stack (FastAPI + SQLAlchemy/Alembic + SQLite→Postgres, Next.js 16 App Router, FinanceToolkit for ratio math, direct yfinance/EDGAR clients instead of OpenBB) is deliberately lightweight and matches the project constraints (Coolify deployment, $0-22/mo budget, decision-support only).

The soundest approach validated across all four research files is: build ingestion and data-provenance discipline first and rigorously (provider abstraction, per-ticker failure isolation, point-in-time fundamentals with filed-date/accession-number, CIK resolution), because these are cheap to get right now and expensive to retrofit later, then layer analytics/screens/UI on top, which are comparatively cheap to iterate on. All four research files converge on the same sequencing conclusion independently — this is a strong, well-triangulated signal for the roadmap.

The key risks are all data-quality risks, not technology risks: yfinance is an unreliable, unofficial scraper that must be isolated behind an adapter from day one; SEC EDGAR requires strict header/rate-limit compliance and produces structurally different data for foreign private issuers (TSM, ASML, ARM, GDS, NBIS) and for REITs/cyclicals/loss-making names whose ratios (P/E especially) are not comparable across sub-sectors without explicit domain-aware handling. A second-order risk is over-building: PROJECT.md and PITFALLS.md both explicitly warn against over-engineering composite scoring/normalization/point-in-time infrastructure before a simple end-to-end screen has proven useful.

## Key Findings

### Recommended Stack

Python 3.12/3.13 + FastAPI 0.139.x + SQLAlchemy 2.0.x + Alembic on the backend; Next.js 16 (App Router, TypeScript, Turbopack) + Recharts on the frontend; SQLite for MVP with a DATABASE_URL-driven path to Postgres; uv for Python dependency management; FinanceToolkit (MIT) for ratio/valuation math fed from already-ingested data rather than its default FMP/yfinance auto-fetch. Deploy as a 3-service docker-compose stack on the owner existing Coolify VPS, using Coolify native scheduled tasks for the daily refresh.

**Core technologies:**
- FastAPI + Pydantic v2 — typed API layer, pairs naturally with response models for ratios/rankings
- SQLAlchemy 2.0 + Alembic — ORM/migrations, database-agnostic models so SQLite to Postgres is a config change
- Next.js 16 App Router + Recharts — dashboard frontend; Server Components fetch, Client Components handle sort/chart interactivity
- FinanceToolkit — ratio/valuation math, fed from EDGAR+price data directly rather than its default provider fetch
- Direct yfinance (prototyping) + hand-rolled httpx SEC EDGAR client (production) — chosen over OpenBB Platform, which is disproportionate weight (AGPL license, 100+ provider abstraction) for a 55-ticker personal tool

### Expected Features

The core differentiator is sub-sector peer-group comparison and relative-value screens scoped to that taxonomy — everything else (table, detail page, heatmap) is table stakes that supports it.

**Must have (table stakes):**
- Sortable multi-column table of the ~55-ticker universe, grouped by sub-sector
- Company detail page with price chart + valuation snapshot
- Sector rollups (median, not mean, per sub-sector)
- Data freshness / last-updated indicator per data point
- CSV export

**Should have (differentiators, this project actual value):**
- Sub-sector peer-group comparison view — the core value proposition
- Relative-value screens scoped to a peer group (cheapest P/E in memory)
- Sector heatmap keyed to the custom 9-sub-sector taxonomy (not GICS)
- Composite score (growth + valuation + momentum), rank-based and peer-group-scoped
- Per-source data provenance tagging (EDGAR vs yfinance vs FMP)

**Defer (v2+):**
- Composite score, watchlist, provenance tags — add after v1 usage validates the core thesis
- Heatmap time-period selector, multiple named watchlists, FRED macro overlay
- Explicitly out of scope permanently: automated buy/sell signals, backtesting engine, paper trading, social/sentiment feeds, real-time quotes, technical-analysis overlays, multi-user accounts

### Architecture Approach

A one-directional pipeline: scheduled ingestion (Coolify cron) to a provider abstraction layer to a normalized SQLite/Postgres store (raw data only, never derived values) to a FastAPI service layer that computes ratios/screens fresh on every read to a Next.js dashboard that owns zero business logic. The taxonomy lives in a YAML config file, loaded once at process start, never duplicated into the database — both ingestion and API resolve sub-sector membership from the same in-memory structure.

**Major components:**
1. Taxonomy loader (sectors.yaml) — single source of truth for ticker to sub-sector to sector, read-only after load
2. Provider abstraction (PriceProvider/FundamentalsProvider Protocols) — swappable price feed (yfinance to FMP), fixed EDGAR fundamentals source, deliberately two separate interfaces
3. Refresh orchestrator — per-ticker isolated try/except loop, retry/backoff, run-log, invoked by Coolify cron (not a queue/worker system)
4. Data store — point-in-time fundamentals (new row per restatement, never overwrite), simple upsert for prices, no derived-metric tables
5. Analytics/screens — pure functions computing ratios/scores from stored raw data, called at request time, unit-testable independent of the API
6. FastAPI routers + Next.js frontend — thin HTTP layer and presentation layer respectively, all business logic stays server-side in Python

### Critical Pitfalls

1. **Treating yfinance as production-grade** — it is an unofficial scraper with undocumented, inconsistent rate limits. Isolate every call behind one provider-adapter module from day one so swapping to FMP is a config change, not a rewrite.
2. **Missing SEC EDGAR compliance** — no compliant User-Agent header or rate limiting (~8-10 req/sec) causes silent 403s and IP soft-blocks. Build one shared, compliant EDGAR client before pulling real data.
3. **Foreign private issuers break uniform EDGAR assumptions** — TSM, ASML, ARM, GDS, NBIS file 20-F/6-K under ifrs-full tags, not 10-K/us-gaap, and have non-1:1 ADR ratios. Test the pipeline against one of these tickers early, not as an afterthought.
4. **Comparing raw P/E across incomparable sub-sectors produces nonsense** — REITs need P/FFO, cyclical semis need normalized/multi-year earnings, loss-making names need P/E rendered as N/A. This must be encoded in the taxonomy schema, not left to a generic ratio engine.
5. **No point-in-time provenance on fundamentals** — storing only latest known value means restatements silently rewrite history. Add filed_date/accession_number columns from the first migration; this is the single most expensive-to-retrofit decision in the whole system.
6. **Composite scoring with naive normalization or tiny peer groups** — plain z-scores are outlier-distorted, and sub-sectors with n=3-4 (DC REITs, cooling/thermal) cannot support meaningful percentile ranking. Use median/MAD normalization and visibly flag small-n rankings as low-confidence.

## Implications for Roadmap

Based on research, suggested phase structure (this maps directly onto ARCHITECTURE.md build-order and PITFALLS.md phase mapping, which independently converge on the same sequence):

### Phase 0: Scaffold + Deployment Wiring
**Rationale:** Coolify docker-compose deployment should exist in parallel with schema work, not retrofitted after the frontend is built — avoids the exact restructuring the project docker-compose-from-Phase-0 decision is meant to prevent.
**Delivers:** 3-service docker-compose stack (backend/frontend/optional db), reverse proxy via Coolify, scheduled-task wiring in place before there is real data to serve
**Uses:** Coolify native compose deploy, uv-managed backend, Next.js 16 scaffold
**Research flags:** Standard pattern (Coolify compose docs well-documented) — skip research-phase

### Phase 1: Data Model + Taxonomy Config
**Rationale:** Everything downstream depends on the schema existing; provenance/point-in-time decisions are cheap now, expensive to retrofit (Pitfall 6), so they must be designed into the first migration, not added later.
**Delivers:** SQLAlchemy models (tickers, daily_prices, fundamentals with filed_date/accession_number, refresh_runs), Alembic migrations with SQLite-batch-mode from the start, sectors.yaml + loader, resolved and zero-padded CIK mapping stored explicitly per ticker
**Addresses:** Taxonomy config requirement, data freshness requirement
**Avoids:** Pitfall 3 (CIK drift), Pitfall 6 (no point-in-time provenance), Pitfall 7 (initial ticker-list validation against EDGAR + reference ETFs)
**Research flags:** Needs research — point-in-time schema pattern and CIK zero-padding conventions are niche enough to warrant a research-phase pass

### Phase 2: Provider Abstraction + Ingestion (Price + Fundamentals)
**Rationale:** Provider interfaces must exist before any ingestion code is written — this is the single most-repeated recommendation across all four files.
**Delivers:** PriceProvider/FundamentalsProvider Protocols, YFinanceProvider, compliant-header/rate-limited EdgarProvider, refresh orchestrator with per-ticker try/except isolation and retry/backoff, tested explicitly against at least one foreign private issuer (TSM/ASML) and one REIT
**Addresses:** Price/fundamentals pull requirements, refresh-script-survives-failures requirement
**Avoids:** Pitfall 1 (yfinance direct-wiring), Pitfall 2 (EDGAR compliance), Pitfall 4 (XBRL tag inconsistency), Pitfall 5 (foreign issuer filing differences), Pitfall 10 (staleness indicators)
**Research flags:** Needs research — SEC EDGAR filer-type branching, XBRL ifrs-full fallback, and yfinance rate-limit behavior are exactly the kind of niche, fast-moving domain detail that benefits from a dedicated research pass

### Phase 3: Analytics, Ratios, and Screens
**Rationale:** Depends entirely on Phase 2 real ingested data existing; pure-function analytics are unit-testable independent of the API and should be validated against fixture rows spanning REIT/cyclical/foreign-filer/loss-making edge cases before any UI consumes them.
**Delivers:** Ratio computation module (P/E, EV/EBITDA, growth, margins) with sub-sector-aware primary metrics (P/FFO for REITs, N/A guards for negative earnings), named screens registry, composite score with median/MAD normalization and small-n flagging
**Addresses:** Valuation ratio requirement, relative-value screens requirement, composite score requirement
**Avoids:** Pitfall 8 (cross-sub-sector P/E nonsense), Pitfall 9 (naive z-score composite scoring)
**Research flags:** Needs research — sub-sector-appropriate valuation metric selection (P/FFO, normalized cyclical earnings) and modified z-score/percentile mechanics are domain judgment calls, not standard engineering patterns

### Phase 4: FastAPI Service Layer
**Rationale:** Thin HTTP wrapper around Phase 1-3 repository/analytics layer; low architectural risk once the layers below are solid.
**Delivers:** /sectors, /companies, /companies/{ticker}, /screens routers, response schemas
**Uses:** FastAPI, Pydantic response models, repository pattern
**Research flags:** Standard pattern — skip research-phase

### Phase 5: Next.js Dashboard
**Rationale:** Carries the least architectural risk and the most expected visual/UX iteration; should come last since it depends entirely on a stable API contract.
**Delivers:** Sortable table, company detail page + price chart, sector heatmap, screens view, CSV export, staleness indicators
**Addresses:** All table-stakes and MVP differentiator features from FEATURES.md
**Avoids:** Pitfall 10 (staleness must be visible in UI, not just stored)
**Research flags:** Standard pattern (Server/Client Component split, Recharts usage) — skip research-phase; heatmap component may need a lighter research touch if Recharts custom-cell grid proves insufficient (Nivo ResponsiveHeatMap fallback)

### Later Phase: FMP Provider Swap + Multi-Sector Generalization
**Rationale:** Explicitly deferred per PROJECT.md — validate the data-center vertical end-to-end before generalizing the taxonomy schema to hold multiple themes or adding a paid data feed.
**Delivers:** FMPProvider implementing the existing PriceProvider Protocol; N-theme taxonomy schema; theme-level momentum rollup reusing existing heatmap machinery

### Phase Ordering Rationale

- Ingestion-adjacent phases (1-2) come before any analytics or UI because every downstream feature (FEATURES.md dependency graph) traces back to per-company ratios computed, which traces back to both price and fundamentals landing in the store first.
- Provenance/schema decisions (point-in-time fundamentals, CIK resolution) are placed in Phase 1, before ingestion code exists, because PITFALLS.md is explicit that these are cheap to add now and expensive to retrofit — this is the clearest front-load-this signal across all four files.
- Analytics (Phase 3) is separated from ingestion (Phase 2) and from the API (Phase 4) because it is pure computation, independently testable, and is where the domain-specific pitfalls (REIT/cyclical/foreign-issuer ratio handling) concentrate.
- The frontend is last because it is the lowest-risk, most-iterated layer and has zero business logic of its own — nothing downstream of the API needs to be stable before frontend work starts except the API contract itself.
- Multi-sector generalization and FMP are explicitly sequenced after the whole vertical ships, per PROJECT.md own stated decision, and PITFALLS.md over-engineering-before-proven-useful pitfall reinforces not pulling this forward.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Point-in-time fundamentals schema pattern and CIK zero-padding/resolution conventions
- **Phase 2:** SEC EDGAR filer-type branching (10-K vs 20-F), XBRL ifrs-full tag fallback, yfinance rate-limit/backoff behavior
- **Phase 3:** Sub-sector-appropriate valuation metric selection (P/FFO, normalized cyclical earnings) and composite-score normalization method (modified z-score vs percentile, small-n handling)

Phases with standard patterns (skip research-phase):
- **Phase 0:** Coolify docker-compose deployment is well-documented
- **Phase 4:** FastAPI routers/repository pattern is a standard, well-established pattern
- **Phase 5:** Next.js Server/Client Component split and Recharts usage are standard, well-documented patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Versions verified directly against PyPI/npm/official docs; architectural opinions flagged as synthesis, not fact |
| Features | MEDIUM | Cross-checked across 8 retail platforms and factor-investing literature; feature framing is inference from competitor patterns, not user testing |
| Architecture | MEDIUM | Established software patterns (repository, point-in-time modeling, Protocol-based providers) well-sourced; project-specific sizing/tradeoffs are original analysis |
| Pitfalls | MEDIUM-HIGH | SEC official docs and yfinance GitHub issue threads are HIGH confidence primary sources; valuation/scoring guidance is MEDIUM, single-sourced per claim |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- FinanceToolkit DataFrame-input constructor behavior (feeding it pre-ingested data rather than letting it fetch) was not independently re-verified against source code — verify against toolkit_controller.py during Phase 2/3 implementation
- The seed ticker list itself is explicitly unverified against live market data (per PROJECT.md) — Phase 1 taxonomy validation pass must resolve open questions (Cerebras IPO status/ticker, neocloud listing status) before ingestion work proceeds
- Composite score normalization method (modified z-score vs percentile) is a judgment call the research surfaces but does not resolve definitively — decide and document during Phase 3 planning
- Whether Recharts custom-cell grid is sufficient for the sub-sector heatmap or whether Nivo dedicated ResponsiveHeatMap is needed is unresolved — validate with a quick spike early in Phase 5

## Sources

### Primary (HIGH confidence)
- PyPI direct fetch — fastapi, sqlalchemy, alembic, financetoolkit, openbb version/release data
- nextjs.org/blog/next-16 — Next.js 16 release notes and breaking changes
- SEC.gov official docs — EDGAR access, rate-control limits, IFRS taxonomy, Financial Reporting Manual (foreign private issuers)
- GDS Holdings and Nebius Group 20-F filings — ADS ratio and foreign private issuer status, primary filings
- GitHub ranaroussi/yfinance issue tracker — rate-limiting failure patterns, primary community evidence
- .planning/PROJECT.md and data-center-value-chain-tickers.md — project-internal source of requirements

### Secondary (MEDIUM confidence)
- Coolify Docker Compose docs, OpenBB license/architecture docs — deployment and alternative-stack context
- Stock Rover/Finviz/Koyfin/Seeking Alpha comparison articles — feature landscape and competitor positioning
- Repository pattern and bitemporal modeling articles (cosmicpython, vbase, StarQube) — architecture pattern justification
- REIT valuation (P/FFO), cyclical stock valuation, negative P/E, z-score normalization articles — pitfall domain reasoning

### Tertiary (LOW confidence)
- None flagged beyond the Gaps section above

---
*Research completed: 2026-07-19*
*Ready for roadmap: yes*
