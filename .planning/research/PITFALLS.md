# Pitfalls Research

**Domain:** Personal financial data tracking and equity screening tool (data center value chain, ~55 tickers, single user)
**Researched:** 2026-07-19
**Confidence:** MEDIUM-HIGH (SEC official docs and GitHub issue threads are HIGH; general valuation/scoring guidance is MEDIUM — no source cross-verified against a second independent source)

## Critical Pitfalls

### Pitfall 1: Treating yfinance as a dependable data source instead of a prototyping shim

**What goes wrong:**
yfinance is an unofficial scraper of undocumented Yahoo Finance endpoints, not a real API. Around November 2024, users found requests started failing after roughly 950 tickers in a run with `YFRateLimitError`, and rate-limit errors have continued across versions with no documented quota — some users get blocked at 4-5 requests/day, others run thousands. Errors are also reported as intermittent (works one day, fails cold the next) and IP-based blocking has been observed to affect even low-volume, well-behaved callers. Separately, Yahoo's terms of use are ambiguous about redistribution/automated access — "personal use only" language and no explicit "yes" for programmatic scraping puts any always-on service built on it in a legal gray zone (lower risk for a private, single-user tool; still not something to build a paid-tier or shared product on).

**Why it happens:**
yfinance is free, has zero setup, and "just works" in a notebook — so it's tempting to wire it directly into the refresh pipeline rather than treating it as a placeholder.

**How to avoid:**
Isolate all yfinance calls behind a single price-provider interface/adapter from day one, even in the MVP. Never call `yfinance` directly from application/screening code — only from one module with retry/backoff and circuit-breaking. This makes swapping to Financial Modeling Prep (already the planned $22/mo upgrade) a config change, not a rewrite. Build in per-ticker failure isolation (one ticker's 429 shouldn't abort the whole refresh run) and a "data as of" timestamp per ticker so stale prices are visible, not silent.

**Warning signs:**
Refresh script works fine locally with 10 tickers, then fails partway through all ~55 on the scheduled Coolify run; identical code succeeds one day and 429s the next; no per-ticker error isolation in the fetch loop.

**Phase to address:**
Data ingestion / price-pull phase — design the provider abstraction and per-ticker failure isolation before wiring the refresh script, not after yfinance breaks in production.

---

### Pitfall 2: Missing SEC EDGAR User-Agent / rate-limit compliance blocks the whole pipeline

**What goes wrong:**
Every request to `data.sec.gov` and `www.sec.gov` requires a `User-Agent` header identifying a real name/organization and contact email. A request without one, or with a generic HTTP-library default, gets a 403 and can get the calling IP soft-blocked for roughly 10 minutes. Separately, EDGAR's Fair Access Policy throttles any client exceeding ~10 requests/second — easy to hit accidentally if a "pull fundamentals for all 55 tickers" job fires requests in a tight loop without a delay.

**Why it happens:**
Standard HTTP client libraries and quick prototypes don't set a custom User-Agent, and a company-facts pull for 55 tickers looks small enough that rate limiting feels irrelevant — until the loop runs with no sleep and trips the limiter, or the wrong header format (e.g. no contact email) causes silent 403s that look like network errors.

**How to avoid:**
Hardcode a compliant `User-Agent: <AppName> <contact-email>` header in one shared EDGAR client module (never per-call). Rate-limit all EDGAR calls to ~8 req/sec with an explicit `sleep`/token-bucket, even though the universe is only ~55 tickers — the same client will later be reused for the emerging/watchlist names and any ETF holdings cross-check. Fail loudly and log the response body on 403/429 rather than silently returning empty data.

**Warning signs:**
EDGAR calls return 403 with no fetched data but the refresh script reports "success"; company-facts pulls work for the first ~8 tickers in a loop and then silently return nothing for the rest.

**Phase to address:**
Fundamentals ingestion (SEC EDGAR) phase — build the shared client with header + rate limiter as the very first EDGAR integration task, before pulling real company-facts data.

---

### Pitfall 3: CIK-to-ticker mapping drift silently breaks or mis-attributes fundamentals

**What goes wrong:**
The ticker → CIK lookup relies on EDGAR's `company_tickers.json`, a periodically-refreshed snapshot the SEC explicitly does not guarantee for accuracy or completeness. Ticker symbols get reused by different issuers over time, CIKs need manual zero-padding to 10 digits before use in other endpoints (the ticker-lookup response doesn't return them padded), and a ticker in the local `sectors.yaml` config can silently point to a stale or wrong CIK after a corporate action (spinoff, ticker change, relisting) if the mapping isn't re-verified periodically.

**Why it happens:**
The mapping file is treated as a one-time lookup during initial setup rather than something that needs periodic re-validation, and CIK zero-padding bugs are an easy off-by-one that only surface as a confusing 404 from a downstream endpoint.

**How to avoid:**
Store the resolved ticker→CIK mapping explicitly in the taxonomy config (not re-derived live each run), with a documented re-verification step on the same monthly cadence already planned for taxonomy review. Always zero-pad CIKs to 10 digits at the point of storage, not at call time. When a ticker fails to resolve or returns unexpected company name metadata, flag it in the refresh log rather than silently skipping it.

**Warning signs:**
A ticker in the taxonomy returns fundamentals for a company with an unexpected name field, or returns 404 that looks like "ticker retired" but is actually a padding bug; a fundamentals value for a ticker suddenly doesn't match what's on the company's actual filing.

**Phase to address:**
Taxonomy config phase (ticker → sub-sector → CIK mapping) — resolve and store CIKs explicitly as part of building the config, and revisit alongside the existing monthly taxonomy-review cadence.

---

### Pitfall 4: XBRL tag inconsistency produces wrong or missing values without erroring

**What goes wrong:**
The `companyfacts` API returns whatever us-gaap (or ifrs-full, for foreign filers) tag each company's accounting team chose — revenue alone might appear under `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, or a filer-specific custom extension tag, and a single company can switch tags between fiscal years without restating history under the new tag. A naive "get `us-gaap:Revenues`" call will return `None`/empty for companies that tag revenue differently — which looks like "no data" rather than "wrong tag," and a composite score or screen will silently drop or zero-out that company.

**Why it happens:**
XBRL taxonomy standardization has been mandatory for over a decade but enforcement of consistent element selection is weak; SEC comment letters flag it as a common filer error, meaning the underlying data genuinely is inconsistent, not a bug in the consuming code.

**How to avoid:**
Build a small tag-fallback list per financial concept (revenue, net income, total assets, etc.) tried in priority order, and log which tag actually resolved per company so gaps are visible rather than silent. Cross-check a handful of results (especially the REITs and foreign filers) against the actual filed statement during the fundamentals-ingestion phase, not after screens are built on top of bad data. Lean on FinanceToolkit's existing tag-mapping/normalization rather than hand-rolling this from scratch, since it already encodes a lot of this tag-fallback knowledge.

**Warning signs:**
A company shows `$0` or null revenue/net income in the browse table while its actual filings clearly report values; two companies in the same sub-sector show wildly different data completeness for the same metric.

**Phase to address:**
Fundamentals ingestion / ratio computation phase — build tag fallback and per-company data-completeness logging before trusting any derived ratio.

---

### Pitfall 5: Foreign private issuers (TSM, ASML, ARM, GDS, NBIS) break the "one uniform EDGAR pull" assumption

**What goes wrong:**
Six-plus tickers in this universe (TSM, ASML, ARM, GDS, NBIS, and potentially others) are foreign private issuers that file an annual **Form 20-F** instead of a 10-K, and file **Form 6-K** (not 10-Q) for interim updates — 6-Ks are irregular, often not machine-parseable in the same structured way, and foreign private issuers are explicitly exempt from the SEC's quarterly reporting rules. Companies using IFRS (rather than US-GAAP) file XBRL under an entirely separate `ifrs-full` taxonomy with different tag names than `us-gaap`, so a fundamentals pipeline hardcoded to `us-gaap` tags will return nothing for these names. On top of that, ADRs/ADSs represent a ratio of underlying ordinary shares (e.g. one GDS ADS = 8 Class A ordinary shares) — per-share and market-cap math must account for the ADS ratio, and dividend/currency figures in filings may be in the home-country currency, not USD.

**Why it happens:**
It's easy to design the fundamentals pipeline against a single US-domestic company's `companyfacts` JSON, verify it works, and assume it generalizes — the structural difference in foreign issuer filings only surfaces when one of these six tickers is actually pulled.

**How to avoid:**
Explicitly test the fundamentals pipeline against at least one foreign private issuer (e.g. TSM or ASML) early, not last. Detect filer type (look for 20-F vs 10-K in `submissions` API, and taxonomy prefix in `companyfacts`) and branch tag lookups (`ifrs-full` fallback alongside `us-gaap`). Expect and design for missing quarterly granularity on these names — a "QoQ revenue growth" screen should gracefully show annual-only data (or N/A) for foreign filers rather than erroring or silently omitting them from the whole sub-sector's screen. Track ADS ratio in the taxonomy config for any name where it isn't 1:1.

**Warning signs:**
TSM/ASML/ARM/GDS/NBIS rows are blank or throw errors in the fundamentals table while US-domiciled peers work fine; a per-share metric for GDS looks 8x off from expectations; a "growth" screen has systematically empty quarterly-cadence cells for the same subset of tickers every time.

**Phase to address:**
Fundamentals ingestion phase — build and test filer-type detection and IFRS tag fallback as part of the initial EDGAR integration, using one of these six tickers as a required test case, not an edge case discovered later.

---

### Pitfall 6: No point-in-time capture means restatements and refresh timing silently corrupt history

**What goes wrong:**
The EDGAR API returns whatever value was most recently filed for a given period — if a company restates a prior figure in a later filing, the API generally does not expose the original as-reported value alongside the restated one; older, superseded numbers for a period tend to just get overwritten by whatever the most recent filing said. If the local database stores "current fundamentals" without recording *which filing* and *as-of date* a value came from, a screen or historical chart quietly rewrites its own past — a company that looked cheap in Q1 based on Q1-filed numbers can retroactively "never have been cheap" once Q3's restated figures overwrite it in local storage.

**Why it happens:**
It's simpler to store "latest known value per metric per period" than to version every fact by filing date, and for a single-user tool this discipline feels like overkill — until a restatement (common in this sector: e.g., large capex reclassifications, revenue recognition changes) changes a value the owner already made a decision against.

**How to avoid:**
Store fundamentals with the source filing's accession number and filed-date alongside the value, not just "period end + value." This is cheap to add now (schema decision) and expensive to retrofit later. It doesn't require building point-in-time infrastructure or a full bitemporal model for the MVP — just don't overwrite without keeping provenance.

**Warning signs:**
A metric for a past period changes value between two refresh runs with no visible explanation; there's no way to answer "what did this look like when I actually looked at it."

**Phase to address:**
Storage schema design phase — add `filed_date`/`accession_number` columns to the fundamentals table from the first migration, before any data is loaded.

---

### Pitfall 7: Hardcoded ticker list rot — spinoffs, M&A, and delistings silently invalidate the universe

**What goes wrong:**
The seed universe already documents SanDisk's 2025 spinoff from Western Digital as a live example — WDC's historical price/fundamentals data pre-spinoff reflects a different company than WDC post-spinoff (it no longer includes the flash/storage business SanDisk now holds separately), and SanDisk (SNDK) as a distinct filer only has SEC history from its spinoff date forward. This pattern recurs constantly in a sector this active: M&A removes a ticker entirely, delistings leave a ticker returning errors instead of an explicit "delisted" status, and a company's ticker can be reused by an unrelated entity years later. A screener that silently returns null/error for a delisted or spun-off ticker (rather than flagging it) creates survivorship bias — the sub-sector view quietly stops accounting for whatever happened, without the owner ever being told the universe shifted under them.

**Why it happens:**
A static YAML ticker list feels "done" once it's populated, and there's no built-in signal that a company underwent a corporate action unless someone notices a metric go blank or reads the news independently.

**How to avoid:**
This is explicitly the reason the taxonomy lives in config with a monthly review cadence (per PROJECT.md) — but the review needs a concrete checklist, not just "eyeball it": (1) does every ticker in config still resolve to an active CIK on EDGAR, (2) does the exchange/listing status in `company_tickers_exchange.json` still show it as listed, (3) cross-check against the reference ETFs (DTCR, AIPO, SRVR, GRID) holdings for names that entered/exited. Treat a ticker that stops returning fresh data as "needs investigation," not "silently drop from the table." When a company splits (e.g., WDC/SNDK), record the split/spinoff date and pre/post relationship in the taxonomy config so historical price charts don't imply continuity that doesn't exist.

**Warning signs:**
A ticker's price/fundamentals data simply stops updating and nothing surfaces that; a sub-sector table shows fewer companies than last month with no note why; a company chart shows a huge, unexplained price/fundamentals discontinuity around a known corporate-action date.

**Phase to address:**
Taxonomy config phase for the initial validation pass (verify the seed list before building on it, since PROJECT.md already flags it as unverified); refresh-script phase for ongoing "ticker stopped resolving" alerting.

---

### Pitfall 8: Comparing raw P/E and similar ratios across incomparable sub-sectors produces nonsense rankings

**What goes wrong:**
Three distinct distortions collide in this exact universe if ratios are computed generically and compared without sub-sector awareness:

1. **REITs (DLR, EQIX, IRM):** GAAP net income for a REIT is dominated by large non-cash real-estate depreciation (27.5-39 year schedules) that doesn't reflect real economic decline the way it would for equipment — so REIT P/E is structurally understated-cash-flow-looking and not comparable to a non-REIT's P/E at all. The correct sector-native multiple is P/FFO or P/AFFO, not P/E.
2. **Cyclical semis (the whole chips/foundry/equipment/memory block — NVDA, AMD, TSM, ASML, AMAT, MU, etc.):** trailing P/E looks artificially cheap right at a cycle peak because trailing EPS is inflated by boom-year earnings — buying the "cheapest P/E in the sub-sector" at a cyclical top is the textbook value trap. Mid-cycle/normalized earnings (averaged over 3-5 years) are the sector-appropriate lens, not raw trailing P/E.
3. **Negative-earnings names (common among the emerging/neocloud watchlist — CRWV, APLD, IREN, SMCI-adjacent, and possibly others as they scale):** P/E is mathematically undefined or nonsensical for a loss-making company; a naive ranking either has to exclude them (silently, which itself misleads) or sorts them arbitrarily if the code doesn't explicitly guard against negative/zero denominators.

If the composite score treats P/E identically across REITs, cyclical semis, and unprofitable growth names, the "cheapest in sub-sector" screen will produce misleading or actively wrong answers — exactly the failure mode this tool exists to avoid (comparing a company to its actual peers).

**Why it happens:**
Off-the-shelf ratio libraries (including FinanceToolkit) compute the ratio formula correctly but don't know which ratio is *appropriate* for which sub-sector — that domain judgment is exactly the "novel part" PROJECT.md says the taxonomy is for, so it has to be encoded explicitly rather than assumed to fall out of a generic formula.

**How to avoid:**
Encode sector-appropriate primary valuation metrics in the sub-sector taxonomy itself: REITs get P/FFO or P/AFFO as the primary multiple (P/E shown only as a secondary/reference figure, clearly labeled as REIT-distorted); cyclical semis get trailing P/E flagged with a "cycle position" caveat or a normalized/multi-year-average earnings variant if feasible; any company with negative or near-zero earnings gets P/E explicitly rendered as N/A (never a synthetic negative number) and excluded from P/E-based rankings with a visible reason, falling back to EV/Revenue or EV/EBITDA-style metrics that remain defined. Don't let one generic ratio engine silently apply to every row uniformly.

**Warning signs:**
The "cheapest P/E in sub-sector" screen ranks a REIT or a name at cycle-peak earnings as the top pick; a loss-making company shows a large negative P/E number sorted as if it were a legitimate low value; composite score results "feel wrong" to the owner relative to their own domain knowledge of the sector.

**Phase to address:**
Ratio/valuation computation phase — define per-sub-sector primary metrics as part of the taxonomy schema, not as an afterthought bolted onto a generic ratio engine; screening/ranking phase — guard all ratio-based sorts against undefined/negative denominators explicitly.

---

### Pitfall 9: Composite scoring breaks silently with unnormalized inputs and tiny peer groups

**What goes wrong:**
Equal-weighting raw metric values (rather than normalized scores) means a metric with a naturally huge numeric range (e.g., market cap in billions) can dominate a composite score purely due to units, not intended importance. Z-score normalization assumes something resembling a normal distribution and is itself distorted by outliers — a single extreme value in a metric can drag the mean and inflate the standard deviation enough that the *rest* of the peer group gets compressed into a narrow, meaningless z-score band (documented failure mode: a 75th-percentile company can end up with a near-zero or even negative z-score purely because of one outlier elsewhere in the set). Percentile ranking avoids the outlier-distortion problem but needs a reasonably large sample to be meaningful — several sub-sectors in this universe (DC REITs: 3 names; cooling/thermal: 4 names) are far too small for percentile ranking to say anything statistically meaningful; with n=3, "top tercile" is one company by definition, not a signal.

**Why it happens:**
Composite scoring formulas (weight × normalized metric, summed) are simple to implement and look reasonable in a spreadsheet, but the normalization method choice and peer-group size are exactly the details that make or break whether the resulting number means anything — and both are easy to skip when the goal is "get a ranking on screen."

**How to avoid:**
Use a robust normalization (median + median absolute deviation, i.e. a modified z-score) rather than plain mean/stddev z-scores, since the metric distributions here (P/E, growth rates) are known to have outliers (cyclical peaks/troughs, negative-earnings names). For sub-sectors with very small n (DC REITs at 3, cooling at 4), either widen the peer group intentionally (e.g., compare DC REITs against a broader data-center-adjacent REIT set, not just the 3 in this taxonomy) or visibly flag composite scores in tiny sub-sectors as low-confidence/directional-only rather than presenting them with the same authority as a 6-7 company sub-sector's ranking. Always normalize before weighting — never sum raw heterogeneous-unit metrics.

**Warning signs:**
A composite score ranking flips dramatically when one company's data updates, out of proportion to how much that company's actual metrics changed; the DC REIT or cooling/thermal sub-sector ranking looks suspiciously decisive (a clean 1-2-3) despite having only 3-4 companies to rank.

**Phase to address:**
Composite scoring phase — choose and document the normalization method (modified z-score, not naive z-score) and explicitly design for small-n sub-sectors before shipping the ranking feature; this is squarely a "prove it's useful before over-building" candidate given PROJECT.md's stated scope caution.

---

### Pitfall 10: Stale or partial data displayed with no visible staleness indicator erodes trust

**What goes wrong:**
When a per-ticker refresh fails silently (yfinance rate-limited, EDGAR 403'd, a ticker delisted), the natural failure mode of "just show the last known value" without any visible timestamp or staleness flag means the owner can't tell fresh data from data that's days or weeks old — and for a personal decision-support tool, the entire value proposition depends on trusting what's on screen. This is worse than an obvious error: a broken page is visibly broken, but subtly stale data looks identical to fresh data and gets acted on as if current.

**Why it happens:**
Per-ticker failure isolation (needed anyway, per Pitfall 1) naturally produces partial refresh runs; showing "last known good value" is the easy default, but doing so *without* a visible "as of [date]" per data point turns a resilience feature into a silent trust hazard.

**How to avoid:**
Every displayed price and fundamental value should carry (and optionally surface in the UI) the timestamp/filing-date it was last successfully refreshed. Build a simple "data health" indicator per ticker (or a dashboard-level banner) showing how many tickers failed to refresh in the last run and how old the oldest stale data point is. This is cheap to add at the refresh-script/storage layer and expensive to retrofit once the dashboard already assumes uniform freshness.

**Warning signs:**
No column or indicator anywhere in the schema/UI answers "when was this last updated"; the owner makes a screening decision based on a number that turns out to be three weeks stale with no way to have known.

**Phase to address:**
Storage/refresh phase — add `last_updated`/`as_of` fields to the schema from the start; browse/dashboard phase — surface staleness visibly, not just store it invisibly in the database.

---

## Moderate Pitfalls

### Look-ahead bias in "current" fundamentals

**What goes wrong:**
Even without formal backtesting, a "growth screen" that pulls Q3-end fundamentals the moment the period ends (rather than when the filing was actually made public, typically 30-45+ days later for a 10-Q) implies knowledge that wasn't actually available at that date. This matters less for a live daily-refresh tool than for backtesting, but it still distorts any historical comparison ("what did this screen show a month ago") if fundamentals are keyed by period-end date rather than the date they became known.

**How to avoid:**
Key stored fundamentals by both period-end date and filed/available date (same schema change as Pitfall 6's provenance fix handles this for free). Don't build a backtesting feature at all in the MVP — PROJECT.md already scopes this out — but don't let the schema make it impossible to do correctly later either.

**Phase to address:** Storage schema design phase (same change as Pitfall 6).

---

### Timezone and market-calendar mishandling in daily bars and YTD

**What goes wrong:**
"YTD return" has two commonly-confused formulas — a cumulative sum (for flow metrics like revenue) versus a percentage change from a fixed starting price (for the stock itself) — and mixing them up produces a nonsensical percentage. Separately, using unadjusted close prices for YTD ignores split/dividend adjustments, market-holiday gaps get mishandled if a "previous close" naively looks back one calendar day instead of one trading day (breaking around long weekends/holidays), and pulling data across US markets, TSM/ASML/ARM's home exchanges, and the tool's own server timezone without pinning everything to US market timezone (America/New_York) for "trading day" boundaries can shift a day's close into the wrong calendar year at year boundaries.

**How to avoid:**
Always use split/dividend-adjusted close prices for return calculations. Anchor "trading day" boundaries to the US market calendar/timezone regardless of server or data-source timezone. Compute YTD as `(latest_close / last_trading_day_of_prior_year_close) - 1`, using an actual market-calendar lookup (not "Jan 1 minus N days") to find the correct prior-year-end trading day. Exclude the current/in-progress trading day from any "as of" YTD figure if the market hasn't closed yet.

**Phase to address:** Price ingestion / ratio computation phase — pick and test one market-calendar library convention (e.g., `pandas_market_calendars` or equivalent) rather than hand-rolling holiday logic.

---

### ADR/foreign-currency reporting quirks for TSM, ASML, ARM, GDS, NBIS

**What goes wrong:**
Beyond the 20-F/6-K filing-cadence issue (Pitfall 5), foreign filers' underlying financials may be reported in a home currency (TWD for TSM, EUR for ASML) even though the ADR trades in USD — a naive "revenue growth %" computed straight from filed figures is currency-neutral (fine), but any cross-currency comparison (e.g., comparing TSM's absolute revenue to a USD-reporting peer) needs an explicit FX conversion, and ADR/ADS ratios (GDS: 1 ADS = 8 ordinary shares) mean per-share metrics computed naively from a share count in the filing will be off by that ratio unless corrected.

**How to avoid:**
Store each foreign filer's reporting currency and ADS ratio explicitly in the taxonomy config. Prefer currency-neutral ratios (margins, growth rates, P/E, EV/EBITDA) for cross-sub-sector comparison over absolute dollar figures where currency conversion would be required; when absolute figures are shown, convert at a documented FX rate (and mark it as converted, not native).

**Phase to address:** Taxonomy config / fundamentals ingestion phase — capture currency and ADS ratio per ticker where non-1:1 or non-USD, at the same time CIKs are resolved (Pitfall 3).

---

### Over-engineering before the screens prove useful

**What goes wrong:**
PROJECT.md already explicitly scopes out backtesting and flags composite scoring/ranking as something to prove out incrementally — the risk is building sophisticated infrastructure (point-in-time bitemporal storage, statistically rigorous small-sample handling, multi-provider failover) before confirming the underlying taxonomy and screens are even useful to look at day-to-day. For a single-user personal tool, the fastest path to learning whether the sub-sector screens deliver value is a simple, honest MVP — not a maximally correct one.

**How to avoid:**
Apply the "cheap now, expensive later" filter from this document only to schema/data-provenance decisions (filed_date, as_of timestamps, CIK/ADS-ratio storage) — these cost almost nothing to add now and a lot to retrofit. Defer anything genuinely complex (normalized through-cycle earnings, modified z-scores with careful small-n handling, full point-in-time backtesting) until after the MVP screens are used for a few real decisions and prove worth refining. The taxonomy and screening rules are explicitly called out as "where the actual value is" — spend the deep engineering effort there, not on infrastructure hardening for a single-user tool with no uptime SLA.

**Phase to address:** Roadmap-level sequencing — order phases so a working (if imperfect) end-to-end screen ships before deeper correctness work on scoring/normalization.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|--------------------|-----------------|------------------|
| Calling yfinance directly from screening code (no adapter layer) | Faster to prototype | Full rewrite when swapping to FMP or when Yahoo breaks the scraper again | Never — the adapter costs almost nothing to add upfront |
| Storing "latest fundamentals value" with no filed-date/accession-number provenance | Simpler schema | Restatements silently rewrite history; can't audit "what did I see when" | Never for a financial tool — add the columns even if unused at first |
| Generic ratio engine applied uniformly across all sub-sectors | One code path, less initial work | REIT/cyclical/negative-earnings rankings are actively misleading | Never for the ranking/screen features; acceptable only for a raw "reference numbers" table clearly labeled as not sub-sector-adjusted |
| Naive z-score normalization (mean/stddev) for composite scoring | Simple, well-known formula | Single outlier distorts the whole peer group's ranking | Acceptable only as a first pass with a visible caveat, before the modified z-score / percentile decision is made deliberately |
| Skipping ticker delisting/spinoff detection in the refresh script | Less code in MVP | Universe silently rots; survivorship bias creeps in unnoticed | Acceptable for the very first working version, but must be added before the monthly taxonomy-review cadence is relied on |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|------------------|--------------------|
| yfinance | Calling it directly throughout the codebase; no retry/backoff; assuming stable rate limits | Isolate behind one provider-adapter module with retry, backoff, and per-ticker failure isolation; treat as swappable/prototype-only |
| SEC EDGAR (companyfacts/submissions) | Missing or generic User-Agent header; tight request loops with no delay; assuming `us-gaap` tags apply to all filers | Shared client with compliant User-Agent + ~8 req/sec throttle; branch on filer type (10-K vs 20-F) and taxonomy (`us-gaap` vs `ifrs-full`) |
| EDGAR ticker→CIK mapping | Treating `company_tickers.json` as a one-time, always-accurate lookup; not zero-padding CIKs | Store resolved CIKs explicitly in config; re-verify on the monthly taxonomy review; zero-pad at storage time |
| OpenBB Platform | Assuming every provider behind it has uniform data completeness/freshness across all ~55 tickers | Spot-check data completeness per sub-sector during ingestion, especially for foreign filers and small-cap emerging names |
| FinanceToolkit | Assuming its default ratio formulas are sub-sector-appropriate out of the box (e.g., P/E for REITs) | Override/supplement with sector-aware primary metrics (P/FFO for REITs, normalized earnings flag for cyclicals) rather than accepting generic output uncritically |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Sequential, unthrottled per-ticker API loop with no concurrency control | Refresh script takes increasingly long or starts hitting 429s | Rate-limit explicitly (token bucket) rather than relying on natural loop slowness; add jittered backoff | As soon as rate limits tighten (yfinance) or the universe grows past ~50-60 tickers |
| SQLite with no indexing on (ticker, date) for price history | Dashboard queries slow down as history accumulates | Index on ticker+date from the first migration; this is cheap now, expensive to add under load later | After a year or two of daily bars across 55+ tickers — small in absolute terms, but easy to get wrong from day one |
| Recomputing composite scores and ratios on every page load instead of caching at refresh time | Dashboard feels sluggish as computed-metric complexity grows | Compute and store derived ratios/scores at refresh time, not request time | As soon as normalization (Pitfall 9) requires cross-company aggregation per request |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing any paid data-provider API key (FMP) in code or committed config rather than environment/secrets | Key leaks via git history or Coolify build logs | Use env vars per the existing `DATABASE_URL` pattern; never commit `.env` |
| Exposing the FastAPI backend directly to the internet without the Next.js frontend as the only public surface | Unauthenticated API becomes a scraping target or DoS vector for a personal tool with no auth layer (correctly out of scope per PROJECT.md) | Keep the API bound to the internal Coolify network / reverse-proxy only the frontend, since multi-user auth is explicitly out of scope |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|--------------|-------------------|
| Displaying stale/partial data with no "as of" indicator (Pitfall 10) | Owner acts on outdated numbers without knowing it | Timestamp every data point; surface a refresh-health indicator |
| Showing raw P/E for REITs and cyclical semis without a sub-sector-appropriate caveat (Pitfall 8) | Owner draws wrong conclusions from a technically-correct-but-misleading number | Label metrics with the sub-sector-appropriate primary valuation lens; show generic P/E only as secondary reference |
| Presenting a composite score for a 3-4 company sub-sector with the same visual authority as a 6-7 company one (Pitfall 9) | Owner over-trusts a ranking that isn't statistically meaningful at that sample size | Visually flag small-n rankings as directional/low-confidence |
| Silently dropping a delisted/spun-off ticker from a sub-sector view (Pitfall 7) | Owner doesn't realize the universe shifted and may miss a name that needs following up (e.g., tracking SNDK post-spinoff) | Explicitly flag "ticker no longer resolves" rather than silent omission |

## "Looks Done But Isn't" Checklist

- [ ] **EDGAR fundamentals ingestion:** Often missing filer-type branching — verify it correctly returns data for at least one foreign private issuer (TSM/ASML/ARM/GDS/NBIS), not just US-domestic 10-K filers
- [ ] **Ticker taxonomy config:** Often missing CIK resolution/zero-padding and delisting detection — verify every ticker resolves to an active CIK and the config records ADS ratio/currency for non-USD, non-1:1 filers
- [ ] **Refresh script:** Often missing per-ticker failure isolation and staleness timestamps — verify one ticker's failure doesn't abort the run and every displayed value has an "as of" date
- [ ] **Ratio/valuation computation:** Often missing negative-earnings guards and sub-sector-aware metric selection — verify P/E renders as N/A (not a negative number) for loss-making names, and REITs show P/FFO as the primary multiple
- [ ] **Composite scoring:** Often missing normalization-method justification and small-n handling — verify the DC REIT (3 names) and cooling/thermal (4 names) sub-sectors are visibly flagged as low-confidence rankings, not presented identically to larger sub-sectors
- [ ] **Fundamentals storage schema:** Often missing filed-date/accession-number provenance — verify a restated historical value doesn't silently overwrite the as-reported value with no trace

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|------------------|
| No provenance/filed-date on stored fundamentals (Pitfall 6) | MEDIUM | Add columns via migration; historical gaps before the fix can't be recovered retroactively, but all data from the fix forward is correct |
| Hardcoded ticker list has rotted (delistings/spinoffs unnoticed) (Pitfall 7) | LOW | Run the CIK-resolution/exchange-status check against the full taxonomy once, manually reconcile against reference ETF holdings, update config |
| Composite score built on naive z-scores, now known to be outlier-distorted (Pitfall 9) | LOW | Swap normalization function (median/MAD) at the computation layer; no schema change needed since raw metrics are still stored |
| yfinance wired directly into screening code, now breaking under rate limits (Pitfall 1) | MEDIUM-HIGH | Requires introducing the adapter layer retroactively and auditing every call site — exactly the rewrite the adapter pattern was meant to avoid |
| Generic P/E-only ranking shipped without sub-sector awareness (Pitfall 8) | MEDIUM | Add sub-sector-primary-metric field to taxonomy config, branch the ranking logic; existing stored ratios are still usable, just need a new selection layer on top |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|--------------------|----------------|
| yfinance as unreliable primary source (P1) | Price ingestion phase | Provider logic lives in exactly one adapter module; swapping to FMP requires editing only that module |
| Missing EDGAR User-Agent/rate limiting (P2) | Fundamentals ingestion phase | A full 55-ticker company-facts pull completes with zero 403s and a bounded, throttled request rate |
| CIK/ticker mapping drift (P3) | Taxonomy config phase | Every ticker in config has an explicitly stored, zero-padded CIK verified against a live EDGAR lookup |
| XBRL tag inconsistency (P4) | Fundamentals ingestion phase | Revenue/net income/assets resolve (non-null) for a sample spanning at least one REIT, one cyclical semi, and one foreign filer |
| Foreign private issuer filing differences (P5) | Fundamentals ingestion phase | TSM, ASML, ARM, GDS, and NBIS each return non-empty fundamentals with correct filer-type/taxonomy branching |
| No point-in-time provenance (P6) | Storage schema design phase | Fundamentals table includes filed_date/accession_number columns before first data load |
| Hardcoded ticker list rot / survivorship bias (P7) | Taxonomy config phase (initial validation) + refresh phase (ongoing) | Seed list cross-checked against EDGAR + reference ETF holdings before first use; refresh script flags any ticker that stops resolving |
| Cross-sub-sector ratio nonsense (P8) | Ratio/valuation computation phase | REITs show P/FFO as primary metric; cyclical semis show a cycle-position caveat; negative-earnings names show P/E as N/A, never a negative sort value |
| Composite scoring normalization/small-n (P9) | Composite scoring phase | Normalization method documented and justified; DC REIT and cooling/thermal sub-sectors visibly flagged as small-sample |
| Stale data shown as fresh (P10) | Storage/refresh phase + dashboard phase | Every displayed value has a visible "as of" date; a refresh-health view shows failed/stale tickers |
| Look-ahead bias in stored fundamentals | Storage schema design phase | Fundamentals keyed by both period-end and filed/available date |
| Timezone/market-calendar/YTD errors | Price ingestion / ratio computation phase | YTD computed against actual prior-year-end trading day via a market-calendar library, using adjusted close prices |
| ADR/currency/ADS-ratio handling | Taxonomy config phase | Non-USD, non-1:1 ADR tickers have currency and ADS ratio explicitly stored and applied in per-share math |
| Over-engineering before proven useful | Roadmap-level sequencing | A working end-to-end screen ships before deep normalization/backtesting infrastructure is built |

## Sources

- GitHub — [ranaroussi/yfinance rate-limiting issues #2128, #2422, #2411, #2289, #2125, discussion #2431](https://github.com/ranaroussi/yfinance/issues/2128) (HIGH — primary issue tracker)
- [Yahoo Finance API guide, ToS ambiguity discussion — scrapfly.io](https://scrapfly.io/blog/posts/guide-to-yahoo-finance-api) (MEDIUM)
- [Yahoo Developer API Terms of Use — legal.yahoo.com](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) (HIGH — primary source)
- [SEC EDGAR Rate Limits: 10 Requests/Second Rule — dealcharts.org](https://dealcharts.org/blog/edgar-scraping-rate-limits-explained) (MEDIUM)
- [SEC Rate Limits & Compliance — EdgarTools docs](https://edgartools.readthedocs.io/en/stable/resources/sec-compliance/) (MEDIUM-HIGH)
- [SEC.gov — Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) (HIGH — official)
- [SEC.gov — New rate control limits to EDGAR websites](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) (HIGH — official)
- [XBRL Tagging Errors That Trigger SEC Review — finrep.ai](https://www.finrep.ai/blog/xbrl-tagging-errors-that-trigger-sec-review) (MEDIUM)
- [XBRL US — Approved Validation Rules](https://xbrl.us/home/priorities/data-quality/rules-guidance/) (HIGH — standards body)
- [SEC EDGAR API guide — thefullstackaccountant.com](https://www.thefullstackaccountant.com/blog/intro-to-edgar) (MEDIUM — includes frames/restatement handling detail)
- [SEC.gov — IFRS Taxonomy for Foreign Private Issuers](https://www.sec.gov/data-research/standard-taxonomies/ifrs-taxonomy) (HIGH — official)
- [SEC Financial Reporting Manual — Foreign Private Issuers, Topic 6](https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual/frm-topic-6) (HIGH — official)
- [GDS Holdings Form 20-F FY2024 — ADS ratio disclosure](https://www.sec.gov/Archives/edgar/data/1526125/000141057825000935/gds-20241231x20f.htm) (HIGH — primary filing)
- [Nebius Group N.V. Form 20-F — foreign private issuer status](https://www.sec.gov/Archives/edgar/data/0001513845/000110465926052948/nbis-20251231x20f.htm) (HIGH — primary filing)
- [A Primer on Survivorship Bias — QuantRocket](https://www.quantrocket.com/blog/survivorship-bias/) (MEDIUM)
- [Dealing with Delistings: A Critical Aspect for Stock-Selection Research — Alpha Architect](https://alphaarchitect.com/dealing-with-delistings-a-critical-aspect-for-stock-selection-research/) (MEDIUM)
- [How to Evaluate a REIT: FFO, AFFO & NAV — Baker 1031](https://www.baker1031.com/insights/how-to-evaluate-a-reit-ffo-affo-and-nav/) (MEDIUM)
- [Real Estate and REIT Valuation: NAV, FFO, AFFO, and Cap Rates](https://ibinterviewquestions.com/guides/valuation-investment-banking/real-estate-reit-valuation-nav-ffo-affo-cap-rates) (MEDIUM)
- [Traps in Valuing Cyclical Stocks — Pomegra Learn Library](https://pomegra.io/learn/library/track-b-stock-market-core/stock-valuation/chapter-02-relative-valuation/cyclical-valuation-traps) (MEDIUM)
- [Negative P/E Ratio Explained — Ziggma](https://ziggma.com/post/negative-pe-ratio) (MEDIUM)
- [Demystifying the P/E Ratio: Pitfalls — Financial Modeling Prep](https://site.financialmodelingprep.com/education/financial-ratios/pricetoearnings-ratio-calculation-use-cases-and-pitfalls) (MEDIUM)
- [Z-Score vs Modified Z-Score vs Percentile anomaly detection — Medium](https://medium.com/@nandrajog.aakash/z-score-vs-modified-z-score-vs-percentile-which-anomaly-detection-method-should-you-use-13158e7f8a25) (MEDIUM)
- [Introducing z-score normalization for hybrid search — OpenSearch blog](https://opensearch.org/blog/introducing-the-z-score-normalization-technique-for-hybrid-search/) (MEDIUM — cross-domain but directly applicable normalization pitfalls)
- [Look-ahead bias in backtesting — pfolio academy](https://www.pfolio.io/academy/look-ahead-bias) (MEDIUM)
- [A Taxonomy of Backtest Lies: Survival Bias, Lookahead Bias — susanpotter.net](https://www.susanpotter.net/quant/backtest-bias-taxonomy/) (MEDIUM)
- [YTD, YoY, MTD & MoM Explained — ClicData](https://www.clicdata.com/blog/reporting-acronyms-ytd-yoy-mtd-mom-explained/) (MEDIUM)
- [Understanding American Depositary Receipts — Fidelity](https://www.fidelity.com/learning-center/investment-products/stocks/understanding-american-depositary-receipts) (MEDIUM-HIGH)
- Project context: `.planning/PROJECT.md` and `data-center-value-chain-tickers.md` (primary — defines the actual ticker universe and known open questions this research addresses)

---
*Pitfalls research for: Personal financial data tracking and equity screening tool*
*Researched: 2026-07-19*
