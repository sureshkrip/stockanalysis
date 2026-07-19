# Phase 1: Data Foundation — Taxonomy, Ingestion & Deployment - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Owner has a live, deployed data pipeline where every tracked ticker's prices and SEC EDGAR fundamentals are ingested with full provenance, and the taxonomy is editable without touching code — the foundation everything downstream is built on. Covers: taxonomy config (TAXO-01), price + fundamentals ingestion (INGEST-01, INGEST-02), local storage with per-ticker-resilient refresh (STORE-01, STORE-02), and docker-compose deployment to Coolify (DEPLOY-01) — including the actual scheduled daily refresh, not just the deploy wiring.

</domain>

<decisions>
## Implementation Decisions

### Ticker Universe Verification
- **D-01:** Seed ticker list verified against live market data on 2026-07-19 (web search). Cerebras IPO'd 2026-05-14 under ticker **CBRS** (Nasdaq) — added to `data-center-value-chain-tickers.md` under AI chips/accelerators. NBIS, CRWV, APLD, IREN, SMCI, GDS all confirmed still listed and actively trading — no removals. `data-center-value-chain-tickers.md` is now current as of 2026-07-19; use it as-is when building `sectors.yaml`.
- **D-02:** No automated ticker-liveness check in Phase 1 ingestion. Verification is a one-time manual pass (done above) that rides along with PROJECT.md's existing "revisit taxonomy roughly monthly" cadence. Per-ticker failure logging (STORE-02) is the safety net between reviews if a ticker goes stale/delists.
- **D-02a:** General delisting policy — delisted tickers are never auto-removed from `sectors.yaml`. They stay in the taxonomy permanently; ingestion just logs the per-ticker failure each run (per D-02's existing safety net) rather than removing the entry. Owner removes a ticker manually only if/when they choose to during a taxonomy review — not something the pipeline does on its own.

### Taxonomy Config Shape
- **D-03:** `sectors.yaml` uses flat sub-sector tagging — no sub-sub-sector nesting. Each ticker gets exactly one primary sub-sector. Straddling cases (e.g., Vertiv spans power/cooling) get a single primary assignment; no schema-level way to express dual membership in v1.
- **D-04:** "Emerging / picks-and-shovels" watchlist is a regular 10th sub-sector — no special `watchlist: true` flag or different treatment. If it needs different handling later (e.g., excluded from composite scoring), that's a Phase 4+ decision.
- **D-05:** Single `sectors.yaml` file (not split per sub-sector). ~56 tickers across 10 sub-sectors is small enough to edit in one sitting.
- **D-06:** Minimal per-ticker fields: ticker, company name, sub-sector only. No notes/alias field. CIK is resolved and cached by the ingestion pipeline itself, not hand-entered in the taxonomy.

### Ingestion Proof Surface
- **D-07:** Success criteria #2's proof surface is a real FastAPI endpoint, not a throwaway CLI script. It becomes part of the actual API surface Phase 2's frontend will consume — no separate CLI report needed.
- **D-08:** Single `GET /companies` endpoint returning a list, each item a nested payload: taxonomy (ticker/name/sub-sector), latest price with source + as-of date, and a fundamentals array (revenue/net income/market cap per filing period with `filed_date`/`accession_number`). No endpoint splitting (`/prices/{ticker}`, `/fundamentals/{ticker}`) in Phase 1 — Phase 2/3 can add purpose-built endpoints as the real API design settles.
- **D-09:** The fundamentals array returns the full ingested 3-5 year history per company, not just the latest period — proves INGEST-02's multi-year ingestion actually worked, and this same data serves v2's DEPTH-01 (trend charts) without re-ingestion.

### Scheduling & Deployment Scope
- **D-10:** Phase 1 wires up the actual Coolify scheduled task for the daily refresh — not deferred to a manual post-Phase-1 step. The phase goal is a "live, deployed data pipeline," and the marginal cost is small given DEPLOY-01 already requires configuring the Coolify deploy.
- **D-11:** Refresh runs once daily, after US market close (~9pm ET / 01:00 UTC) so closing prices are final and same-day EDGAR filings have processed. Exact UTC time and Coolify cron syntax are left to the planner/executor.
- **D-12:** Frontend scaffold in Phase 1 is a minimal health/status page — confirms the Next.js app can reach the backend (e.g., shows company count from `/companies`, or "API: healthy"). No real UI/table logic; Phase 2 builds the first real page from scratch. This proves full-stack wiring (frontend + backend + db, all deployed together) without throwaway UI.

### Claude's Discretion
- Exact Coolify cron time/syntax within "once daily, after market close" (D-11).
- Internal schema details not covered above (e.g., exact SQLAlchemy model field names, CIK caching mechanism) — these are researcher/planner territory, not user decisions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Ticker universe
- `data-center-value-chain-tickers.md` — seed ticker list for `sectors.yaml`, verified current as of 2026-07-19 (see D-01). Source of truth for the ~56-ticker universe across 10 sub-sectors.

### Project-level specs
- `.planning/PROJECT.md` — constraints (tech stack, storage, deployment, budget, scheduling), Key Decisions table, multi-sector-future context
- `.planning/REQUIREMENTS.md` — TAXO-01, INGEST-01, INGEST-02, STORE-01, STORE-02, DEPLOY-01 (this phase's requirements)
- `.planning/ROADMAP.md` — Phase 1 goal and success criteria
- `.planning/STATE.md` — Blockers/Concerns section flags research areas: SEC EDGAR filer-type branching (10-K vs 20-F), XBRL ifrs-full tag fallback for foreign private issuers (TSM, ASML, ARM, GDS, NBIS), yfinance rate-limit/backoff behavior, point-in-time fundamentals schema pattern, and CIK zero-padding/resolution conventions — flagged for a dedicated research pass during planning, not resolved in this discussion

No other external specs/ADRs exist yet — this is a greenfield repo.

</canonical_refs>

<code_context>
## Existing Code Insights

Greenfield repository — no existing code. Only `data-center-value-chain-tickers.md` and `.planning/`/`.claude/` scaffolding exist at the time of this discussion. No reusable assets, established patterns, or integration points to note.

</code_context>

<specifics>
## Specific Ideas

- `GET /companies` response shape (D-08): list of objects, each with nested `taxonomy` (ticker, name, sub_sector), `price` (value, source, as_of), and `fundamentals` (array of {revenue, net_income, market_cap, filed_date, accession_number} per filing period).
- Frontend scaffold (D-12): a single status page — company count pulled from `/companies` or a plain "API: healthy" message — nothing more elaborate.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope. (Automated ticker-liveness checking (D-02) and sub-sub-sector nesting (D-03) were considered and explicitly declined for Phase 1, not deferred as future work — revisit only if a real need emerges.)

</deferred>

---

*Phase: 1-Data Foundation — Taxonomy, Ingestion & Deployment*
*Context gathered: 2026-07-19*
