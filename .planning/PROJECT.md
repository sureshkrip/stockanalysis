# Data Center Stocks

## What This Is

A personal research and tracking tool for the public-company "data center value chain" — the ~55 companies across chips, memory, networking, power, cooling, colocation REITs, hyperscalers, and construction/materials that make data centers happen. It pulls prices and fundamentals, groups everything by sub-sector, and runs relative-value screens so one company can be judged against its actual peers rather than against the whole market.

Built for one user (the owner) for personal investing decisions and to build a deeper understanding of how this sector fits together.

## Core Value

Seeing every company in the data center value chain grouped by sub-sector, with comparable metrics side by side — so relative value within a peer group is obvious at a glance.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Maintain a ticker → sub-sector → sub-sub-sector taxonomy as an editable config file
- [ ] Pull daily close prices for the full ticker universe
- [ ] Pull fundamentals (revenue, net income, market cap) from SEC EDGAR as the source of record
- [ ] Store prices and fundamentals locally with a refresh script that survives per-ticker failures
- [ ] Browse companies grouped by sub-sector in a sortable table (price, market cap, P/E, YTD %)
- [ ] View a single company's detail page with a price chart
- [ ] See a sector-level heatmap colored by return
- [ ] Compute valuation ratios (P/E, EV/EBITDA, revenue growth, gross margin trends) per company
- [ ] Run within-sub-sector relative-value screens (cheapest P/E in memory, fastest growth in networking, etc.)
- [ ] Rank companies by a composite score (growth + valuation + momentum)
- [ ] Deploy the stack to the owner's existing Coolify VPS via docker-compose

### Out of Scope

- **Automated buy/sell signals or alerts** — this is decision-support only; screens are inputs the owner reviews manually, never actions the system takes
- **Multi-user accounts / auth** — single personal user; auth only becomes relevant if the tool is ever shared
- **Real-time or intraday quotes** — daily EOD data is sufficient for the research cadence this supports
- **Backtesting engine** — scope creep past the tracking/screening goal; revisit only if the screens prove genuinely useful
- **Third-party PaaS hosting (Vercel/Fly.io/Railway)** — owner has a VPS with Coolify already running
- **Options, crypto, or non-equity instruments** — the universe is public-company equities in this value chain

## Context

**Sector universe.** ~55 tickers across 9 sub-sectors plus an emerging/picks-and-shovels watchlist. Seed list saved at `data-center-value-chain-tickers.md`. Reference ETFs (DTCR, AIPO, SRVR, GRID) are useful for cross-checking that the universe isn't missing obvious names.

The seed list was compiled from general sector knowledge as of early 2026 and has **not** been verified against live market data. Some entries may be stale — companies in this sector IPO, spin off, and get acquired frequently (SanDisk's 2025 spinoff from Western Digital is one example). Two known open questions: whether Cerebras has actually IPO'd and under what ticker, and whether the emerging/neocloud names are all still trading as listed. Verifying the universe against SEC EDGAR and ETF holdings is early work, not an assumption to build on.

**Sub-sector classification matters more than any individual ticker.** The taxonomy is the novel part of this project — the reason to build it rather than use an off-the-shelf screener. It lives in config so it can be edited as the sector shifts (plan to revisit roughly monthly).

**Data sourcing strategy.** Start entirely free: SEC EDGAR (fundamentals, official, unlimited under ~10 req/sec fair use), FRED (macro context), yfinance (prices — prototyping only; it's an unofficial Yahoo scraper that breaks without notice and is ToS-gray, so don't build production dependencies on it). Once the MVP proves useful, add Financial Modeling Prep's ~$22/mo Starter plan as the primary priced feed. SEC EDGAR stays the fundamentals source of record permanently — official and free.

**Open source leverage.** OpenBB Platform (AGPL — fine for personal/internal use) as the data-access layer over 100+ providers; FinanceToolkit (MIT) for ratio/valuation math. The taxonomy, screening rules, and dashboard are hand-written — that's where the actual value is.

**Data quality caveat.** Free sources have gaps and errors. Anything informing a real investing decision gets cross-checked against SEC filings directly.

## Constraints

- **Tech stack**: Python/FastAPI backend, Next.js (App Router, TypeScript) frontend — owner's choice; keeps data/analysis logic and dashboard cleanly separated
- **Storage**: SQLite for MVP, Postgres upgrade path — zero setup cost to start, but `DATABASE_URL` from env with SQLite fallback so the same codebase runs both ways
- **Deployment**: docker-compose stack on owner's existing Coolify VPS — Coolify deploys compose natively and handles reverse proxy, SSL, and git-push-to-deploy
- **Budget**: $0 through the MVP; ~$22/mo ceiling once a paid data feed is justified
- **Scheduling**: Coolify scheduled tasks over GitHub Actions — compute already exists, and it avoids exposing API keys to a third-party CI runner
- **Purpose**: research/tracking tool, not investment advice — no automated trading signals

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI + Next.js split | Data/analysis logic worth building before the frontend; clean API boundary lets each evolve independently | — Pending |
| SQLite first, Postgres later | Zero setup for MVP; `DATABASE_URL` env var makes the swap a config change, not a rewrite | — Pending |
| docker-compose from Phase 0 | Coolify deploys compose natively — building this way from the start avoids a restructure at deploy time | — Pending |
| Self-host on Coolify VPS | Owner already runs the infrastructure; no PaaS cost, no third-party key exposure | — Pending |
| Free data sources first (EDGAR + FRED + yfinance) | Prove the tool is useful before paying; EDGAR is official and free forever | — Pending |
| SEC EDGAR as fundamentals source of record | Official filings are ground truth; free sources drift and have gaps | — Pending |
| Sub-sector taxonomy in config, not code | Sector churns constantly (IPOs, spinoffs, M&A) — editing YAML beats editing code monthly | — Pending |
| Decision-support only, no automated signals | Personal investing tool where the owner's judgment is the point; auto-signals invite unearned trust | — Pending |
| OpenBB (data access) + FinanceToolkit (ratios) | Don't rebuild 100+ provider integrations or 150 ratio formulas; spend effort on the taxonomy and screens instead | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-19 after initialization*
