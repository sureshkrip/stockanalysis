# API Coverage Matrix — Phase 1

**Generated:** 2026-07-19 (plan time)
**Detector note:** `api-coverage.cjs` returned `detected: false` when run at plan time, because no `PLAN.md` files existed yet and the ROADMAP phase text alone carries no trigger term. Phase 1 does integrate two external data APIs, and the plans now on disk will trip the detector at `verify:pre`. This matrix is produced deliberately rather than waiting for the gate to fail.

Baseline is **full coverage**. Every capability starts as `INTEGRATE`; this file is the subtraction record. Every `OPT-OUT` carries a reason.

---

## SEC EDGAR (`data.sec.gov` + `www.sec.gov/files`)

The public EDGAR surface relevant to this project is three JSON endpoints plus the bulk archives.

| capability | decision | reason |
|---|---|---|
| `company_tickers.json` (ticker → CIK mapping) | INTEGRATE | Plan 03, `cik_resolver.py` — required by D-06 (CIK is pipeline-resolved, never hand-entered) |
| `xbrl/companyfacts/CIK{cik}.json` (all facts for a company) | INTEGRATE | Plan 03/04, `fundamentals.py` — the primary INGEST-02 source |
| `us-gaap` taxonomy concept extraction | INTEGRATE | Plan 03 — domestic 10-K filers (~51 of 56 tickers) |
| `ifrs-full` taxonomy concept extraction | INTEGRATE | Plan 03 — foreign private issuers filing 20-F (TSM, ASML, ARM, GDS, NBIS) |
| `dei` namespace (`EntityCommonStockSharesOutstanding`) | INTEGRATE | Plan 04 — required input to the derived market cap |
| Revenue concept family | INTEGRATE | INGEST-02 |
| Net income concept family | INTEGRATE | INGEST-02 |
| Multi-year filing history (3-5 years) | INTEGRATE | D-09 — full history on first ingest, avoids a re-ingestion project for v2 trend charts |
| Provenance fields (`accn`, `filed`, `fy`, `fp`, `form`, `end`) | INTEGRATE | D-08/D-09 — the point-in-time key and the API's audit trail |
| `submissions/CIK{cik}.json` (filing index, form types, filing dates) | OPT-OUT | Not needed yet — companyfacts already carries the form type and filed date per fact. Required by v2's DATA-02 filings watcher, not by v1. |
| `xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json` (single-concept endpoint) | OPT-OUT | Redundant — companyfacts returns every concept in one request, and per-concept fetching would multiply request count against SEC's 10 req/sec limit for no gain. |
| `xbrl/frames/` (cross-company facts for one period) | OPT-OUT | Not needed — this project queries per-company and joins in its own database; frames solves the inverse problem. |
| `dei:EntityPublicFloat` | OPT-OUT | Explicitly rejected, not merely unused — reported once yearly as of a non-period-end date and excludes affiliate-held shares, so it is not market cap. Substituting it would skew every downstream valuation. |
| Balance-sheet concepts (assets, liabilities, equity, debt) | OPT-OUT | Not needed yet — Phase 3's valuation snapshot (BROWSE-02: P/B, ROE/ROIC, debt ratios) will need these. Phase 1's requirement set is revenue, net income, market cap only. |
| Cash-flow concepts | OPT-OUT | Not needed yet — no v1 requirement consumes cash-flow data. |
| Segment / dimensional facts | OPT-OUT | Not needed — sub-sector grouping comes from the owner's own `sectors.yaml` taxonomy, not from filer-reported segments. |
| Full-text search (`efts.sec.gov`) | OPT-OUT | Explicitly out of scope — automated filing discovery is v2 (DATA-02). |
| Bulk archives (`Archives/edgar/`, daily/quarterly index) | OPT-OUT | Not needed at this scale — 56 tickers via the JSON API is well inside the rate limit; bulk download is for universe-wide ingestion. |
| Rate-limit compliance (10 req/sec) | INTEGRATE | Plan 03 — `EDGAR_MIN_REQUEST_INTERVAL` pacing guard |
| Required `User-Agent` identification | INTEGRATE | Plan 03 — settings-sourced on a shared client; a generic UA returns 403 and risks an IP block |

## yfinance / Yahoo Finance

Scoped as prototyping-only per CLAUDE.md; FMP replaces it in v2 (DATA-01). The opt-outs below reflect that deliberately narrow scope.

| capability | decision | reason |
|---|---|---|
| `download()` daily OHLCV history | INTEGRATE | Plan 02 — the INGEST-01 source; batch call over the full ticker list |
| Daily close price | INTEGRATE | INGEST-01 |
| Trading-date (`as_of`) attribution | INTEGRATE | TRUST-02 groundwork — every price carries its source and as-of date |
| Open / high / low / volume | OPT-OUT | Not needed yet — no v1 requirement consumes intraday range or volume. Phase 3's price chart (BROWSE-02) may revisit; the same `download()` call already returns them if so. |
| Day % change, YTD % | OPT-OUT | Not needed yet — these are Phase 2 (BROWSE-01) display columns and will be computed from the stored price series rather than re-fetched. |
| `.info` / quote summary (sector, industry, employees, business summary) | OPT-OUT | Explicitly rejected as an access pattern — per-symbol `.info` in a loop is the direct cause of cascading 429s across a 55-ticker run. Taxonomy comes from the owner's `sectors.yaml`, not from the provider. |
| Trailing / forward P/E and other provider-computed ratios | OPT-OUT | Deliberately not sourced from the provider — ANALYSIS-01 computes ratios via FinanceToolkit from this project's own stored raw data, keeping SEC EDGAR the source of record. |
| Fundamentals (`financials`, `balance_sheet`, `cashflow`) | OPT-OUT | Explicitly rejected — SEC EDGAR is the locked source of record for fundamentals; a second, less authoritative source would create silent reconciliation conflicts. |
| Dividends and splits | OPT-OUT | Not needed yet — dividend yield appears in Phase 3's valuation snapshot (BROWSE-02); revisit there. |
| Corporate actions / adjusted-close handling | OPT-OUT | Not needed yet — `auto_adjust=False` keeps raw closes; no v1 requirement depends on split-adjusted series. |
| Options, crypto, futures, news, analyst ratings, holders | OPT-OUT | Explicitly out of scope per REQUIREMENTS.md — equities only, no sentiment or analyst aggregation. |
| Intraday / real-time quotes | OPT-OUT | Explicitly out of scope per REQUIREMENTS.md — daily EOD is sufficient and intraday carries licensing and cost implications outside budget. |
| Rate-limit resilience (429 backoff) | INTEGRATE | Plan 02 — `tenacity` bounded retry with exponential jitter |

---

**Summary:** 15 capabilities INTEGRATE, 20 OPT-OUT, every opt-out reasoned. Nothing is left undecided.

The opt-outs cluster into four honest categories: (1) needed by a later v1 phase and deliberately deferred to it (balance sheet, OHLV, dividends, day/YTD change); (2) explicitly out of v1 or v2 scope per REQUIREMENTS.md (options, intraday, sentiment, full-text search); (3) redundant given a capability already integrated (companyconcept, frames, submissions); (4) actively rejected because using them would be wrong (`EntityPublicFloat` as market cap, provider fundamentals competing with EDGAR, per-symbol `.info` loops).
