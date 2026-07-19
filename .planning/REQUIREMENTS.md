# Requirements: Data Center Stocks

**Defined:** 2026-07-19
**Core Value:** Seeing every company in the data center value chain grouped by sub-sector, with comparable metrics side by side — so relative value within a peer group is obvious at a glance.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Taxonomy

- [ ] **TAXO-01**: Owner can define and edit the ticker → sub-sector → sub-sub-sector taxonomy in a YAML config file without touching code

### Ingestion

- [ ] **INGEST-01**: System pulls daily close price and basic quote data for every ticker in the taxonomy config
- [ ] **INGEST-02**: System pulls revenue, net income, and market cap for every ticker from SEC EDGAR's company facts API, going back 3-5 years of filings per company (not just the latest quarter — avoids a re-ingestion project when trend charts are added later)

### Storage & Refresh

- [ ] **STORE-01**: Prices and fundamentals persist locally via SQLAlchemy models, running on SQLite in dev with a `DATABASE_URL`-driven Postgres path for production
- [ ] **STORE-02**: A refresh script updates all tickers and logs per-ticker failures without stopping the overall run

### Browsing

- [ ] **BROWSE-01**: Owner can browse all tracked companies in a sortable table grouped by sub-sector, with columns: ticker, name, sub-sector, price, day % change, YTD %, market cap, trailing P/E, forward P/E, EV/EBITDA, revenue growth (YoY), gross margin, last-updated
- [ ] **BROWSE-02**: Owner can view a single company's detail page showing a price chart (1Y+) and a current valuation snapshot (P/E, P/B, P/S, EV/EBITDA, PEG, growth, margins, ROE/ROIC, debt ratios, dividend yield where available)
- [ ] **BROWSE-03**: Owner can view a sector-level heatmap colored by YTD return, sized by market cap, for a single time period (no period selector in v1)

### Analysis

- [ ] **ANALYSIS-01**: System computes P/E, EV/EBITDA, revenue growth, and gross margin trend per company (via FinanceToolkit)
- [ ] **ANALYSIS-02**: Owner can view a sub-sector peer-group comparison showing all companies in a sub-sector side by side with percentile rank within the group
- [ ] **ANALYSIS-03**: Owner can run relative-value screens scoped to a single sub-sector (e.g., cheapest P/E in memory, fastest growth in networking)
- [ ] **ANALYSIS-04**: System computes a composite score (growth + valuation + momentum) per company, rank-based (percentile, not raw z-score) and scoped to its own peer group, with sub-scores visible — never a single opaque number

### Data Trust

- [ ] **TRUST-01**: Every displayed data point shows a last-updated timestamp, visually distinct when stale
- [ ] **TRUST-02**: Every displayed data point shows which source it came from (EDGAR / yfinance / FMP) and its as-of date

### Convenience

- [ ] **CONV-01**: Owner can export any table view to CSV
- [ ] **CONV-02**: Owner can star/pin tickers to a single watchlist that persists across sessions

### Deployment

- [ ] **DEPLOY-01**: The full stack (backend, frontend, db) is defined as a docker-compose stack and deploys to the owner's existing Coolify VPS via git-push-to-deploy

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Multi-Sector

- **MULTI-01**: Generalize the taxonomy/config schema to hold multiple independent sector-themes side by side (data center is the first; e.g., quantum computing as a future theme)
- **MULTI-02**: Theme-level momentum/return rollup — reuse the existing rollup/heatmap machinery at the theme level so a candidate theme's aggregate performance is visible once the owner adds even a small ticker list for it

### Data Quality Upgrade

- **DATA-01**: Add FMP as the primary priced data source (~$22/mo Starter plan) with yfinance as fallback
- **DATA-02**: Add a filings watcher that polls SEC EDGAR for new 10-K/10-Q/8-K filings on tracked tickers and surfaces them in the dashboard

### Depth

- **DEPTH-01**: Fundamental metric trend charts (multi-year margin/growth history, not just current-value snapshot) — the multi-year history is already ingested in v1 (INGEST-02); this is the deferred UI presentation of it
- **DEPTH-02**: Heatmap time-period selector (1W/1M/YTD toggle) — defer until enough daily price history has accumulated to make period comparisons meaningful
- **DEPTH-03**: Multiple named/custom watchlists (vs. the single starred list in v1)
- **DEPTH-04**: FRED macro overlay (rates, industrial production) for sector context

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Automated buy/sell signals or alerts | Decision-support only — screens are inputs the owner reviews manually, never actions the system takes on its own |
| Automated sector/theme discovery (news volume, IPO activity, capex trends, search trends) | The owner decides which sectors are worth watching and adds a candidate ticker list themselves; the tool shows momentum for themes already added, it doesn't surface new ones on its own |
| Multi-user accounts / auth | Single personal user; revisit only if the tool is ever shared |
| Real-time or intraday quotes | Daily EOD data is sufficient for the research cadence this supports; also has licensing/cost implications outside the $0-$22/mo budget |
| Backtesting engine | The taxonomy is hand-edited roughly monthly, so historical scores aren't comparable across time without point-in-time taxonomy snapshots — real engineering effort, not a quick add-on |
| Paper trading / simulated portfolio | Adds portfolio accounting complexity (fills, cash, corporate actions) for a tool whose purpose is research, not trade simulation |
| Social/sentiment feeds, analyst-rating aggregation | No community to aggregate for a single-user tool; a sentiment black box conflicts with the decision-support/judgment-first design |
| Chart-pattern recognition / technical-analysis overlays (RSI/MACD, head-and-shoulders, etc.) | Dilutes effort from the actual differentiator (fundamental relative-value screening within a taxonomy); momentum in the composite score is a simple price-return factor, not pattern ML |
| Third-party PaaS hosting (Vercel/Fly.io/Railway) | Owner has a VPS with Coolify already running |
| Options, crypto, or non-equity instruments | The universe is public-company equities in this value chain |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TAXO-01 | Phase 1 | Pending |
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 1 | Pending |
| STORE-01 | Phase 1 | Pending |
| STORE-02 | Phase 1 | Pending |
| DEPLOY-01 | Phase 1 | Pending |
| BROWSE-01 | Phase 2 | Pending |
| TRUST-01 | Phase 2 | Pending |
| TRUST-02 | Phase 2 | Pending |
| BROWSE-02 | Phase 3 | Pending |
| BROWSE-03 | Phase 3 | Pending |
| ANALYSIS-01 | Phase 4 | Pending |
| ANALYSIS-02 | Phase 4 | Pending |
| ANALYSIS-03 | Phase 4 | Pending |
| ANALYSIS-04 | Phase 4 | Pending |
| CONV-01 | Phase 5 | Pending |
| CONV-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17 (100%)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-19*
*Last updated: 2026-07-19 after roadmap creation (5 phases, full v1 coverage)*
