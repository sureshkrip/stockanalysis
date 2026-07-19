# Roadmap: Data Center Stocks

## Overview

This roadmap builds the data center value chain tracker as five vertical slices, each ending in something the owner can actually observe. Phase 1 lands the hard, expensive-to-retrofit groundwork first — taxonomy config, provider abstraction, point-in-time ingestion, and Coolify deployment wiring — but proves itself through a real (if minimal) endpoint/CLI output rather than staying invisible until a later "API phase." Phase 2 turns that ingested data into the sortable, provenance-aware browse table that is the project's core value proposition. Phase 3 adds the company detail page and sector heatmap. Phase 4 layers on the actual differentiator — peer-group percentile comparisons, scoped screens, and a transparent composite score. Phase 5 closes the MVP with CSV export and a persistent watchlist. Multi-sector generalization and the FMP data-source swap are deliberately deferred to v2, per PROJECT.md.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment** - Taxonomy config, provider-abstracted price/fundamentals ingestion with full provenance, and a deployed docker-compose stack on Coolify
- [ ] **Phase 2: Company Browser — Sortable Table with Trust Indicators** - Sortable, sub-sector-grouped company table with visible data freshness and source, realizing the core value proposition
- [ ] **Phase 3: Company Detail & Sector Heatmap** - Single-company valuation detail page with price chart, plus a sector-level return heatmap
- [ ] **Phase 4: Relative-Value Analysis & Screens** - Peer-group percentile comparisons, scoped relative-value screens, and a transparent composite score
- [ ] **Phase 5: Convenience — Export & Watchlist** - CSV export of any table view and a persistent starred-ticker watchlist

## Phase Details

### Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment

**Goal**: Owner has a live, deployed data pipeline where every tracked ticker's prices and SEC EDGAR fundamentals are ingested with full provenance, and the taxonomy is editable without touching code — the foundation everything downstream is built on.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: TAXO-01, INGEST-01, INGEST-02, STORE-01, STORE-02, DEPLOY-01
**Success Criteria** (what must be TRUE):

  1. Owner can edit the ticker → sub-sector → sub-sub-sector taxonomy in a YAML config file, and the next ingestion run picks up the change without any code edits
  2. A minimal API endpoint or CLI report shows real daily close prices and SEC EDGAR fundamentals (revenue, net income, market cap, 3-5 years of filing history) for every ticker in the taxonomy, each tagged with its source and as-of date
  3. Running the refresh script against the full ~55-ticker universe completes end-to-end even when individual tickers fail, logging each failure rather than halting the overall run
  4. The backend, frontend scaffold, and database run together as a docker-compose stack that deploys to the owner's Coolify VPS via git-push-to-deploy

**Plans**: 3/5 plans executed

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Walking skeleton: taxonomy YAML → SQLite → GET /companies → Next.js status page → docker-compose

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Price ingestion and the per-ticker-resilient refresh orchestrator
- [x] 01-03-PLAN.md — CIK resolution and SEC EDGAR filer-type branching (us-gaap / ifrs-full) extraction

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-04-PLAN.md — Derived market cap, point-in-time persistence, and full fundamentals history in the API

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-05-PLAN.md — Coolify deployment, daily scheduled refresh, and operations runbook

**UI hint**: yes

### Phase 2: Company Browser — Sortable Table with Trust Indicators

**Goal**: Owner can browse the full company universe in one sortable table grouped by sub-sector, with clear visibility into data freshness and source — delivering the project's core value proposition end-to-end.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: BROWSE-01, TRUST-01, TRUST-02
**Success Criteria** (what must be TRUE):

  1. Owner can open the dashboard and see all tracked companies in a single table grouped by sub-sector, with columns for ticker, name, sub-sector, price, day % change, YTD %, market cap, trailing/forward P/E, EV/EBITDA, revenue growth, gross margin, and last-updated
  2. Owner can sort the table by any column across the whole universe (e.g., cheapest P/E, highest YTD return)
  3. Every data point in the table shows a last-updated timestamp that is visually distinct when the data is stale
  4. Every data point in the table shows which source it came from (EDGAR/yfinance/FMP) and its as-of date

**Plans**: TBD
**UI hint**: yes

### Phase 3: Company Detail & Sector Heatmap

**Goal**: Owner can drill into any single company's valuation detail and see the whole sector's relative performance at a glance.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: BROWSE-02, BROWSE-03
**Success Criteria** (what must be TRUE):

  1. Owner can open any company's detail page and see a 1-year-plus price chart
  2. The detail page shows a current valuation snapshot: P/E, P/B, P/S, EV/EBITDA, PEG, growth, margins, ROE/ROIC, debt ratios, and dividend yield where available
  3. Owner can view a sector-level heatmap colored by YTD return and sized by market cap for the current period

**Plans**: TBD
**UI hint**: yes

### Phase 4: Relative-Value Analysis & Screens

**Goal**: Owner can judge each company against its true peer group via percentile-ranked comparisons, scoped screens, and a transparent composite score.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: ANALYSIS-01, ANALYSIS-02, ANALYSIS-03, ANALYSIS-04
**Success Criteria** (what must be TRUE):

  1. Owner can view computed valuation ratios (P/E, EV/EBITDA, revenue growth, gross margin trend) per company, computed from stored raw data via FinanceToolkit
  2. Owner can view a sub-sector peer-group comparison showing all companies in a sub-sector side by side, with each metric's percentile rank within that group
  3. Owner can run a relative-value screen scoped to a single sub-sector (e.g., cheapest P/E in memory, fastest revenue growth in networking) and see ranked results
  4. Owner can view a composite score per company (growth + valuation + momentum), rank-based within its own peer group, with the growth/valuation/momentum sub-scores visible alongside the composite — never a single opaque number

**Plans**: TBD
**UI hint**: yes

### Phase 5: Convenience — Export & Watchlist

**Goal**: Owner can export any view for offline analysis and maintain a persistent watchlist of tickers worth following closely.
**Mode:** mvp
**Depends on**: Phase 2, Phase 4
**Requirements**: CONV-01, CONV-02
**Success Criteria** (what must be TRUE):

  1. Owner can export any table view (browse table, peer comparison, screen results) to a CSV file
  2. Owner can star/pin any ticker, and it remains marked the next time the dashboard is opened, across browser sessions
  3. Owner can view their starred tickers as a single watchlist

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation — Taxonomy, Ingestion & Deployment | 3/5 | In Progress|  |
| 2. Company Browser — Sortable Table with Trust Indicators | 0/TBD | Not started | - |
| 3. Company Detail & Sector Heatmap | 0/TBD | Not started | - |
| 4. Relative-Value Analysis & Screens | 0/TBD | Not started | - |
| 5. Convenience — Export & Watchlist | 0/TBD | Not started | - |

---
*Roadmap created: 2026-07-19*
*Granularity: standard*
*Mode: mvp (Vertical MVP — every phase ends in an observable, user-facing capability)*
