# Feature Research

**Domain:** Personal stock screening / sector-tracking tool (data center value chain, single-user, decision-support only)
**Researched:** 2026-07-19
**Confidence:** MEDIUM (cross-checked across multiple retail platforms — Finviz, Stock Rover, TradingView, Koyfin, Simply Wall St, Seeking Alpha, InvestingPro, WallStreetZen — plus factor-investing literature on composite scoring; no single vendor doc was treated as sole source)

## Feature Landscape

### Table Stakes (Users Expect These)

Features every retail screening/tracking tool has in some form. Missing these makes the tool feel broken, not "minimal."

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sortable multi-column data table | Every screener (Finviz ~80 filters, TradingView ~168, Stock Rover ~650 metrics) is fundamentally a sortable table; it's the primary interaction model | LOW | Essential columns for this project: ticker, company name, sub-sector, price, day % change, YTD %, market cap, P/E (trailing), forward P/E, EV/EBITDA, revenue growth (YoY), gross margin, and last-updated date per row. Sort + filter by any column. |
| Company detail page with price chart + key metrics | Users expect a "profile page" per ticker showing at minimum a price chart and current valuation snapshot before drilling further | LOW-MEDIUM | Table-stakes metrics per Koyfin/Seeking Alpha convention: P/E (trailing + forward), P/B, P/S, EV/EBITDA, PEG, revenue growth, earnings growth, gross/operating margin, ROE/ROIC, debt ratios, dividend yield. Table-stakes chart: price history (1Y minimum), ideally with volume. |
| Sector/industry grouping | All value-chain-style research is organized by sector/industry first — it's how Finviz Map, GICS-based tools, and this project's own core value proposition all work | LOW | This project already has taxonomy as a config file — the win is making sub-sector the primary navigation axis, not an afterthought filter. |
| Basic valuation ratios computed consistently | P/E, EV/EBITDA, P/S, P/B are the baseline vocabulary of every tool researched; users assume these are present and computed the same way for every company | MEDIUM | Consistency of *formula* matters more than breadth — a P/E computed with stale shares-outstanding or wrong FX will erode trust fast. FinanceToolkit (already chosen) standardizes these. |
| Watchlist (add/remove tickers, persist across sessions) | Every platform studied (Finviz, Investing.com, WallStreetZen, InvestingPro) treats watchlist as a first-class, distinct object from portfolio holdings | LOW | For a single-user tool this can be as simple as a starred/pinned flag per ticker in the DB — no need for multiple named lists at MVP. |
| CSV export of table/screen results | Present (often paywalled) at InvestingPro, Investing.com, WallStreetZen, Uncle Stock — retail users expect to get data out for their own spreadsheet modeling | LOW | Trivial for a personal tool since there's no paywall logic — just a "download CSV" button on any table view. |
| "Last updated" / data freshness indicator per data point | Universal dashboard UX best practice (Smashing Magazine, DQOps): explicit timestamp, not vague relative time; stale data should look visually distinct | LOW-MEDIUM | Elevated to differentiator-level importance here because the data sourcing strategy explicitly mixes free feeds (yfinance, EDGAR, FMP) with different lag characteristics — see Differentiators. |
| Basic sector rollups (average/median metrics per sector) | Users expect the aggregate view before the constituent-level view — this is how every heatmap and sector page is structured | LOW-MEDIUM | Median (not mean) P/E, growth, and margin per sub-sector; mean is skewed hard by outliers in a 55-ticker universe with names ranging from mega-cap hyperscalers to micro-cap neoclouds. |

### Differentiators (Competitive Advantage)

Features that set this tool apart from generic screeners. These should align directly with the Core Value in PROJECT.md: relative value *within* a hand-curated sub-sector taxonomy, not against the whole market.

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Sub-sector peer-group comparison view | This is the actual core value of the project. Generic screeners (Finviz, TradingView) let you filter by GICS sector but don't offer a hand-tuned, narrower taxonomy (e.g., "power/electrical" split from "cooling/thermal", "AI chips" split from "semi equipment"). Stock Rover and Koyfin both treat peer comparison as a premium differentiator, not a filter checkbox, confirming this is genuinely valuable, not table stakes | MEDIUM | Depends on: taxonomy config (already an active requirement) + computed ratios per company. Should show peer-group members side by side with the same column set as the main table, plus percentile rank within group (not just raw values). |
| Relative-value screens scoped to a peer group | "Cheapest P/E in memory," "fastest revenue growth in networking," "best margin trend in cooling" — these are queries generic screeners can't answer because they don't know your taxonomy. This is where the hand-built taxonomy actually pays off vs. an off-the-shelf tool | MEDIUM | Depends on: sub-sector taxonomy + per-company ratios. Implementation is a parameterized "sort/filter within group X" — not a new query engine, just scoping the existing sortable table to one sub-sector. |
| Sector heatmap with sub-sector granularity | Finviz Map is the reference pattern (treemap: box size = market cap, color = return, hierarchical sector→industry→company, time-period selector) — replicating this but keyed to the custom 9-sub-sector taxonomy instead of GICS gives a heatmap no off-the-shelf tool can produce for this specific value chain | MEDIUM-HIGH | Needs a treemap/heatmap charting component (d3 or a library like nivo/visx) plus the same rollup data as sector rollups above. Time-period selector (1D/1W/1M/YTD) is a nice-to-have extension, not MVP-required — daily EOD data makes intraday selectors moot anyway (explicitly out of scope: no intraday quotes). |
| Composite score (growth + valuation + momentum) computed and shown per peer group, with sub-scores visible | Differentiator *if* built carefully — literature (Alpha Architect, Deutsche Bank "Seven Sins of Quantitative Investing") shows equal-weight composites are a legitimate, hard-to-beat baseline, but only when sub-scores are inspectable and normalization is rank-based rather than raw z-scores | MEDIUM-HIGH | See Pitfalls below — this is the single feature most likely to mislead the owner if built naively. Score within the peer group, not the whole universe (reinforces the core value prop) — a "cheap" score for a hyperscaler is meaningless next to a memory-chip maker. |
| Fundamental metric history/trend charts (not just price) | Koyfin's ability to chart P/E, margins, and growth over time (not just current snapshot) is called out as "rare in the retail space" — most tools show current-value-only. Given SEC EDGAR is the fundamentals source of record, historical filings are already available for trend charts at low marginal cost | MEDIUM | Depends on: EDGAR ingestion pulling multiple historical filings, not just latest. High leverage for the "understand how this sector fits together" goal in PROJECT.md — margin/growth trend over 3-5 years tells a better story than a single point-in-time ratio. |
| Explicit per-source data provenance (not just "last updated," but "from which provider") | The project's data strategy deliberately blends SEC EDGAR (official, slow), yfinance (fast, unofficial, gap-prone), and eventually FMP — a generic "updated 2 hours ago" label hides *which* number is EDGAR-verified vs. scraped. Given the explicit "cross-check anything informing a real decision against SEC filings" constraint in PROJECT.md, the UI should make that traceable | LOW-MEDIUM | Small addition on top of table-stakes freshness indicator: a per-field source tag/icon (e.g., "EDGAR · filed 2026-05-01" vs "yfinance · 3h ago") is cheap once the data model tracks source+timestamp per fact, which it should anyway for the fallback design. |

### Anti-Features (Commonly Requested, Often Problematic)

Explicitly out of scope per PROJECT.md, plus additional adjacent asks that surface in this domain. Documented so future "wouldn't it be cool if..." requests get redirected rather than re-litigated.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|----------------|-------------------|-------------|
| Automated buy/sell signals or trading alerts | Surface appeal: "just tell me when to buy" is what most commercial tools (VectorVest, some Finviz Elite features) monetize on | Turns a decision-support tool into something the owner trusts uncritically; a single-user tool with no compliance/review process is exactly where "the system told me to" causes the worst outcomes; also explicitly out of scope per PROJECT.md | Screens surface candidates ("cheapest P/E in memory this week"); the owner reviews and decides manually every time. No push notifications, no "signal fired" state. |
| Backtesting engine | Natural next question once a composite score exists: "would this score have worked historically?" | Backtesting on ~55 tickers with a hand-edited taxonomy that changes monthly is close to guaranteed overfitting — survivorship bias (tickers get removed from the seed list when they're delisted/acquired) and taxonomy drift make historical scores non-comparable across time. Explicitly out of scope per PROJECT.md ("revisit only if the screens prove genuinely useful") | If ever revisited, would need point-in-time taxonomy snapshots and a frozen ticker universe per period — real engineering effort, not a quick add-on. |
| Paper trading / simulated portfolio | Common feature in TradingView, Investing.com, etc. — feels like a natural companion to a watchlist | Adds portfolio accounting complexity (fills, cash balance, P&L, corporate actions like splits/spinoffs — this sector alone has SanDisk's 2025 WDC spinoff as an example of how messy this gets) for a tool whose stated purpose is research, not trade simulation | Watchlist (already table stakes) covers "things I'm tracking" without the accounting surface area. |
| Social/sentiment feeds, analyst-rating aggregation, news sentiment scoring | Seeking Alpha, TradingView, and most retail platforms bundle a social/community layer and sentiment scores because engagement/retention benefits from it | Single-user tool has no community to aggregate; sentiment scores from unknown methodology add a "black box confidence" layer the owner explicitly doesn't want (PROJECT.md: decision-support only, judgment is the point); also pulls in unreliable/paid data sources this project isn't budgeting for | If macro/news context is wanted later, FRED (already in the data strategy) covers macro series without a sentiment layer. |
| Real-time/intraday quotes and streaming price updates | Feels like a natural "more is better" upgrade once a price table exists | Explicitly out of scope per PROJECT.md; daily EOD is sufficient for the research cadence, and intraday data has real licensing/cost implications that don't fit the $0-$22/mo budget | Daily close, refreshed on the existing schedule. Heatmap time-period selector should default to Day/Week/Month/YTD, never intraday. |
| Chart-pattern recognition / technical-analysis overlays (head-and-shoulders, triangles, RSI/MACD indicators) | A headline Finviz/TradingView feature; "since other tools have it, ours should too" | This project's stated core value is fundamental relative-value screening within a taxonomy, not technical/momentum trading — pattern recognition is a different product with a different user (swing trader) and would dilute build effort away from the actual differentiator | Momentum, if included in the composite score, is a simple price-return factor (e.g., 6-month or 12-month return), not chart-pattern ML. |
| Multi-user accounts, sharing, permissions | Natural "what if I want to show this to someone" ask once the tool works well | Explicitly out of scope per PROJECT.md; auth/multi-tenancy is real scope, not a checkbox, and irrelevant until the tool is actually shared | If ever shared, revisit as its own milestone, not bolted onto the single-user data model retroactively. |

## Feature Dependencies

```
Sub-sector taxonomy config (already active requirement)
    └──requires──> Sortable multi-column table (table stakes)
                       └──enhances──> Sub-sector peer-group comparison view (differentiator)
                                          └──requires──> Per-company valuation ratios computed
                                                             └──requires──> Fundamentals ingestion (EDGAR)
                                                             └──requires──> Price ingestion (yfinance/FMP)

Sub-sector peer-group comparison view
    └──enables──> Relative-value screens scoped to a peer group (differentiator)
    └──enables──> Composite score within peer group (differentiator)

Sector rollups (table stakes: median metrics per sub-sector)
    └──requires──> Per-company valuation ratios computed
    └──enables──> Sector heatmap with sub-sector granularity (differentiator)

Composite score (growth + valuation + momentum)
    └──requires──> Per-company valuation ratios computed
    └──requires──> Revenue growth / margin trend data (needs historical fundamentals, not just latest)
    └──requires──> Price momentum data (return over N months)
    └──enhances──> Relative-value screens (score becomes one more sortable column)

Fundamental metric history/trend charts
    └──requires──> Multiple historical EDGAR filings ingested (not just latest quarter)
    └──enhances──> Company detail page

Data freshness indicator (table stakes)
    └──enhances──> Per-source data provenance tag (differentiator)
                       └──requires──> Data model tracks source + fetched-at timestamp per fact, not just per table

Watchlist (table stakes)
    └──enhances──> CSV export (table stakes) — export scoped to watchlist or full screen results

Backtesting engine (anti-feature) ──conflicts──> Monthly taxonomy edits + non-frozen ticker universe
Automated alerts (anti-feature) ──conflicts──> Decision-support-only design principle in PROJECT.md
```

### Dependency Notes

- **Sub-sector peer-group comparison requires per-company ratios, which require both ingestion pipelines:** the comparison view is only as good as the ratios feeding it, and ratios need both a price series (for market cap, momentum) and fundamentals (for P/E, EV/EBITDA, growth, margins) landed first. This is why ingestion phases must precede any comparison/screening UI phase in the roadmap.
- **Composite score enhances but does not require the peer-group view** — it could technically be computed universe-wide — but scoring should be scoped to the peer group to stay true to the core value prop ("relative value within a sub-sector, not against the whole market"). Building it universe-wide first and retrofitting group-scoping later is wasted work; build it group-scoped from the start.
- **Fundamental trend charts require historical filings, not just the latest** — if the EDGAR ingestion pipeline is built to only fetch the most recent filing, trend charts become a re-ingestion project later. Worth deciding up front whether to pull N years of filings per company at initial ingest.
- **Data provenance tagging conflicts with a naive schema that stores only "latest known value" per metric** — if the data model doesn't track source + timestamp per fact from day one, retrofitting provenance display later means a schema migration, not a UI addition. This is a case where a small upfront modeling decision (store facts as {value, source, as_of, fetched_at} tuples) avoids real rework.
- **Backtesting conflicts with the taxonomy-in-config design** — because the taxonomy is edited roughly monthly (per PROJECT.md), a backtest run today can't cleanly answer "how would this scoring model have performed a year ago" without point-in-time taxonomy snapshots, which is why it stays out of scope rather than becoming a fast-follow.

## MVP Definition

### Launch With (v1)

Minimum viable product — enough to validate that sub-sector-scoped relative value is actually more useful than a generic screener.

- [ ] Sortable multi-column table of the full ~55-ticker universe, grouped/filterable by sub-sector — the baseline table-stakes interaction
- [ ] Per-company valuation ratios: P/E, EV/EBITDA, revenue growth, gross margin (already active requirements)
- [ ] Sub-sector peer-group comparison view — the core differentiator; without this the tool is just a spreadsheet with extra steps
- [ ] Company detail page with price chart + current valuation snapshot
- [ ] Sector-level heatmap colored by return (already an active requirement)
- [ ] Relative-value screens within a sub-sector (cheapest P/E, fastest growth) — the second core differentiator
- [ ] Data freshness indicator ("last updated") per data point — essential given the explicit free-data-gaps caveat in PROJECT.md
- [ ] CSV export of any table view — trivial to build, high leverage for a personal research workflow

### Add After Validation (v1.x)

Features to add once the core sub-sector comparison proves genuinely more useful than generic screening.

- [ ] Composite score (growth + valuation + momentum) — trigger: once individual ratio columns and manual sorting feel like they're missing a "which one wins overall" answer, and only after deciding on rank-based (not raw z-score) normalization to avoid outlier distortion
- [ ] Watchlist (starred tickers) — trigger: once the owner starts re-checking the same subset of names repeatedly instead of browsing the full universe each time
- [ ] Per-source data provenance tags (EDGAR vs yfinance vs FMP, with as-of date) — trigger: once a paid feed (FMP) is added and there are genuinely multiple sources to distinguish between, not just one
- [ ] Fundamental metric trend charts (multi-year margin/growth history, not just current value) — trigger: once historical EDGAR filings are being ingested for more than the latest quarter anyway

### Future Consideration (v2+)

Features to defer until the core screening loop has been used for a while and specific gaps are felt.

- [ ] Time-period selector on the heatmap (1W/1M/YTD toggle) — defer until daily EOD history has accumulated enough range to make period comparisons meaningful
- [ ] Multiple named/custom watchlists (vs a single starred list) — defer until one watchlist genuinely feels insufficient
- [ ] Macro overlay from FRED (rates, industrial production, etc., contextualizing sector moves) — defer until the core sector/company views are solid; macro context is a nice-to-have layer, not core value

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| Sortable multi-column table by sub-sector | HIGH | LOW | P1 |
| Per-company valuation ratios | HIGH | MEDIUM | P1 |
| Sub-sector peer-group comparison view | HIGH | MEDIUM | P1 |
| Company detail page + price chart | HIGH | LOW-MEDIUM | P1 |
| Sector heatmap | HIGH | MEDIUM-HIGH | P1 |
| Relative-value screens within peer group | HIGH | MEDIUM | P1 |
| Data freshness / last-updated indicator | MEDIUM-HIGH | LOW | P1 |
| CSV export | MEDIUM | LOW | P1 |
| Composite score (rank-based, group-scoped) | MEDIUM-HIGH | MEDIUM-HIGH | P2 |
| Watchlist | MEDIUM | LOW | P2 |
| Per-source provenance tags | MEDIUM | LOW-MEDIUM | P2 |
| Fundamental trend charts | MEDIUM | MEDIUM | P2 |
| Heatmap time-period selector | LOW-MEDIUM | LOW-MEDIUM | P3 |
| Multiple named watchlists | LOW | LOW | P3 |
| FRED macro overlay | LOW-MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (validates the core "sub-sector relative value" thesis)
- P2: Should have, add once P1 usage confirms the thesis
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Finviz | Stock Rover | Koyfin | This Project's Approach |
|---------|--------|--------------|--------|--------------------------|
| Screener breadth | ~80 filters, GICS sector/industry | ~650 metrics, 14 built-in fair-value screens | Peer dashboards linking multiples to fundamentals | Narrow universe (~55 tickers) but a hand-tuned 9-sub-sector taxonomy no GICS-based tool offers for this value chain specifically |
| Peer comparison | Filter by sector/industry, no dedicated peer view | Dedicated peer comparison across income/growth/profitability/cash flow/dividends, computes fair value + quality/growth/value/sentiment score | Peer comparison dashboards, valuation multiples vs fundamentals | Same idea, scoped to a custom taxonomy the owner controls and edits monthly — the differentiator is taxonomy control, not metric count |
| Heatmap | Finviz Map: treemap by market cap, colored by return, sector→industry→company drill-down, time selector | Not a core feature | Not a core feature | Same treemap pattern, keyed to the 9 custom sub-sectors instead of 11 GICS sectors |
| Composite scoring | Not a core feature | Quality/growth/value/sentiment composite score, weighting not fully disclosed | Percentile-rank snapshots vs peers (0-100 scale) on valuation/margins/profitability | Rank-based (percentile) composite scoped to peer group, sub-scores always visible — explicitly avoiding the "black box" pattern some competitors use |
| Data provenance | Single vendor-controlled feed, not user-visible | Single vendor-controlled feed | Single vendor-controlled feed | Genuinely multi-source (EDGAR + yfinance + FMP) by design, so provenance display is a necessity here that competitors don't need |
| Automated signals/alerts | Yes (Elite tier) — alerts, backtesting | Yes — alerts | Limited | Deliberately absent — decision-support only |

## Sources

- [Stock Rover vs Finviz 5-Year Test](https://www.liberatedstocktrader.com/stock-rover-vs-finviz/) — screener breadth and use-case comparison
- [Finviz vs TradingView Tested](https://www.greatworklife.com/tradingview-vs-finviz/) — filter counts and platform strengths
- [Finviz Stock Market Map](https://finviz.com/map) and [Finviz Elite Heatmap coverage](https://chartmini.com/blog/finviz-elite-heatmap-market-visualization-made-simple-2026) — treemap heatmap design pattern
- [Deutsche Bank "Seven Sins of Quantitative Investing"](https://hudsonthames.org/wp-content/uploads/2022/01/DB-201409-Seven_Sins_of_Quantitative_Investing.pdf) and [Alpha Architect: Combining Factors in Multifactor Portfolios](https://alphaarchitect.com/combining-factors-in-multifactor-portfolios/) — equal-weight vs dynamic-weight composite scoring tradeoffs
- [Koyfin vs Stock Rover comparison (TraderHQ)](https://traderhq.com/koyfin-vs-stock-rover/) and [Slashdot Koyfin/Simply Wall St/Stock Rover comparison](https://slashdot.org/software/comparison/Koyfin-vs-Simply-Wall-St-vs-Stock-Rover/) — peer-comparison feature positioning
- [Koyfin Data Dictionary](https://www.koyfin.com/help/koyfin-data-dictionary/) and [Koyfin: Full company's financials overview](https://www.koyfin.com/features/financial-analysis/) — company detail page metric expectations
- [Seeking Alpha Valuation Tab help doc](https://help.seekingalpha.com/premium/what-is-the-valuation-tab-and-how-do-i-use-it) — standard valuation metric set
- [Smashing Magazine: UX Strategies for Real-Time Dashboards](https://www.smashingmagazine.com/2025/09/ux-strategies-real-time-dashboards/) and [DQOps: Measuring Data Timeliness, Freshness, Staleness](https://dqops.com/docs/categories-of-data-quality-checks/how-to-detect-timeliness-and-freshness-issues/) — data freshness UX patterns
- [WallStreetZen CSV export help doc](https://help.wallstreetzen.com/article/fa8zfyyu4k-how-do-i-export-data-from-the-stock-screener-watchlist-into-my-spreadsheet) and [Investing.com Stock Screener](https://www.investing.com/stock-screener) — CSV export and watchlist conventions
- Project context: `.planning/PROJECT.md`, `data-center-value-chain-tickers.md`

---
*Feature research for: Personal stock screening / sector-tracking tool (data center value chain)*
*Researched: 2026-07-19*
