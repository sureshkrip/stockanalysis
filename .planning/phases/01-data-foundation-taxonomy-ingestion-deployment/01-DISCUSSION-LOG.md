# Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-19
**Phase:** 1-Data Foundation — Taxonomy, Ingestion & Deployment
**Areas discussed:** Ticker universe verification, Taxonomy config shape, Ingestion proof surface, Scheduling scope

---

## Ticker Universe Verification

| Option | Description | Selected |
|--------|-------------|----------|
| Quick manual check now | Look up unresolved tickers now and update the seed file before researcher/planner start | ✓ |
| Automated EDGAR/ETF cross-check in Phase 1 | Build a verification step into the ingestion pipeline itself | |
| Ingest as-is, let failures surface it | Don't pre-verify; rely on per-ticker failure handling | |

**User's choice:** Quick manual check now
**Notes:** Performed the check live via web search during discussion. Cerebras confirmed IPO'd 2026-05-14 under ticker CBRS (Nasdaq); NBIS, CRWV, APLD, IREN, SMCI, GDS all confirmed still trading. Updated `data-center-value-chain-tickers.md` directly: added CBRS to AI chips/accelerators, replaced the "Unverified" banner with a "Verified 2026-07-19" note.

| Option | Description | Selected |
|--------|-------------|----------|
| One-time now, revisit manually later | Rides along with PROJECT.md's existing monthly taxonomy review | ✓ |
| Build an automated liveness check into ingestion | Every refresh run flags unresolvable tickers as an early-warning signal | |

**User's choice:** One-time now, revisit manually later
**Notes:** Per-ticker failure logging (STORE-02) already provides a safety net between monthly reviews — no separate liveness-check feature needed.

---

## Taxonomy Config Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Flat sub-sector only, one primary tag per ticker | Matches the seed list as-is; straddling cases get a primary assignment | ✓ |
| Sub-sector + optional sub-sub-sector depth | Optional third nesting level for future granularity | |

**User's choice:** Flat sub-sector only, one primary tag per ticker

| Option | Description | Selected |
|--------|-------------|----------|
| Regular sub-sector, no special flag | Emerging watchlist treated as a 10th sub-sector like any other | ✓ |
| Same list but tagged as speculative | Add a `watchlist: true` field for optional different treatment later | |

**User's choice:** Regular sub-sector, no special flag

| Option | Description | Selected |
|--------|-------------|----------|
| Single sectors.yaml | One file, ~56 tickers across 10 sub-sectors | ✓ |
| One YAML file per sub-sector | 10 small files under a sectors/ directory | |

**User's choice:** Single sectors.yaml

| Option | Description | Selected |
|--------|-------------|----------|
| Just ticker, company, sub-sector | Minimal fields; CIK resolved by ingestion pipeline, not hand-entered | ✓ |
| Add an optional notes/alias field | Free-text field for straddling cases or name changes | |

**User's choice:** Just ticker, company, sub-sector

---

## Ingestion Proof Surface

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI endpoint | Real GET endpoint, doubles as the actual API surface Phase 2 will consume | ✓ |
| CLI report script | Standalone script printing a formatted table to stdout | |
| Both | CLI for quick sanity-checks plus the FastAPI endpoint | |

**User's choice:** FastAPI endpoint

| Option | Description | Selected |
|--------|-------------|----------|
| One /companies endpoint, full nested payload | Single endpoint with taxonomy + price + fundamentals array nested | ✓ |
| Split endpoints: /companies, /prices/{ticker}, /fundamentals/{ticker} | Purpose-built endpoints per concern from day one | |

**User's choice:** One /companies endpoint, full nested payload

| Option | Description | Selected |
|--------|-------------|----------|
| Return full ingested history (3-5 years) | Proves INGEST-02's multi-year ingestion worked; feeds v2 DEPTH-01 | ✓ |
| Return only latest fundamentals, full history stays in DB only | Smaller payload; full history stored but not exposed yet | |

**User's choice:** Return full ingested history (3-5 years)

---

## Scheduling Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Wire up the actual Coolify scheduled task | Configure the daily cron alongside the required Coolify deploy | ✓ |
| Ship the script, defer Coolify cron config to a manual follow-up | Refresh script proven to work; scheduling clicked through manually later | |

**User's choice:** Wire up the actual Coolify scheduled task

| Option | Description | Selected |
|--------|-------------|----------|
| Once daily, after US market close | ~9pm ET / 01:00 UTC, after prices and same-day filings settle | ✓ |
| You decide exact time during planning | Lock cadence now, precise time left to planner/executor | |

**User's choice:** Once daily, after US market close
**Notes:** Precise UTC time and Coolify cron syntax deferred to planner/executor (Claude's discretion).

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal health/status page | Confirms Next.js can reach the backend; no real UI logic | ✓ |
| No frontend page yet, just the Next.js app shell deployed | Zero frontend logic, deployment wiring only | |

**User's choice:** Minimal health/status page

---

## Claude's Discretion

- Exact Coolify cron time/syntax within "once daily, after market close"
- Internal schema details not covered in discussion (SQLAlchemy model field names, CIK caching mechanism) — researcher/planner territory

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
