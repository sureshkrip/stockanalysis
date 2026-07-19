"""Filer-type branching and multi-year fundamentals extraction (INGEST-02).

This is the phase's highest-risk logic (STATE.md, RESEARCH.md): SEC
EDGAR's companyfacts response is NOT one schema. Foreign private issuers
in this ticker universe (TSM, ASML, ARM, GDS, NBIS) file Form 20-F and
report under the `ifrs-full` XBRL taxonomy with entirely different
concept names than the `us-gaap` taxonomy domestic 10-K filers use. The
shortcut of assuming every company files under us-gaap looks fine on the
45+ domestic tickers and silently produces empty fundamentals for the
foreign-issuer subset.

CONCEPT_MAP below is transcribed exactly from RESEARCH.md Pattern 2,
which was derived from live-fetched companyfacts responses for both
filer types, not from memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

CONCEPT_MAP: dict[str, dict[str, list[str]]] = {
    "us-gaap": {
        "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
        "net_income": ["NetIncomeLoss"],
        "shares_outstanding": ["CommonStockSharesOutstanding"],
    },
    "ifrs-full": {
        "revenue": ["Revenue"],
        "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
        # Foreign filers use the dei namespace's EntityCommonStockSharesOutstanding
        # instead — see _extract_shares.
        "shares_outstanding": [],
    },
}

DEI_SHARES_CONCEPT = "EntityCommonStockSharesOutstanding"


class UnknownTaxonomyError(Exception):
    """Raised when a companyfacts response contains neither us-gaap nor
    ifrs-full — names the taxonomies actually present rather than a bare
    KeyError deep in extraction.
    """

    def __init__(self, present_keys: list[str]) -> None:
        self.present_keys = present_keys
        super().__init__(
            f"no known taxonomy (us-gaap or ifrs-full) in companyfacts response; "
            f"present keys: {present_keys!r}"
        )


@dataclass
class FactRow:
    fiscal_year: int
    fiscal_period: str
    form: str
    accession_number: str
    filed_date: date
    period_end: date
    revenue: float | None
    net_income: float | None
    shares_outstanding: float | None
    market_cap: Decimal | None
    taxonomy: str


def pick_taxonomy(facts: dict) -> str:
    """Detect which XBRL taxonomy a companyfacts response's `facts`
    sub-object uses.

    Every company in this ticker universe reports under exactly one of
    us-gaap or ifrs-full. Never index the response with a hardcoded
    "us-gaap" key — five tickers (TSM, ASML, ARM, GDS, NBIS) file under
    ifrs-full and would produce a KeyError or a silent empty extraction
    that looks like a healthy run with missing data (T-01-13).
    """
    if "us-gaap" in facts:
        return "us-gaap"
    if "ifrs-full" in facts:
        return "ifrs-full"
    raise UnknownTaxonomyError(present_keys=list(facts.keys()))


def extract_concept(facts: dict, taxonomy: str, field: str, unit: str = "USD") -> list[dict]:
    """Return the first matching concept's entries for the requested unit,
    walking CONCEPT_MAP[taxonomy][field]'s candidate names in order.

    The candidate list is an ordered fallback chain, not a set of
    alternatives — this is what handles a company whose concept name
    changed across its own filing history. Filters to the requested unit
    explicitly rather than taking the first key of the `units` dict: TSM's
    Revenue concept reports in both TWD and USD, and taking whichever unit
    happens to come first would silently store New Taiwan Dollar revenue
    as USD (T-01-13).
    """
    for concept_name in CONCEPT_MAP.get(taxonomy, {}).get(field, []):
        concept = facts.get(taxonomy, {}).get(concept_name)
        if concept and unit in concept.get("units", {}):
            return concept["units"][unit]
    return []


def _extract_shares(facts: dict, taxonomy: str) -> list[dict]:
    """dei:EntityCommonStockSharesOutstanding first (used by both filer
    types, reported per filing as of a cover-page date); fall back to the
    us-gaap CONCEPT_MAP entry only if dei is absent.
    """
    dei_entries = facts.get("dei", {}).get(DEI_SHARES_CONCEPT, {}).get("units", {}).get("shares", [])
    if dei_entries:
        return dei_entries
    return extract_concept(facts, taxonomy, "shares_outstanding", unit="shares")


def find_nearest_close(session: Session, ticker: str, as_of: date) -> Decimal | None:
    """Return the ingested Price closest in calendar days to `as_of` for
    `ticker`, or None when the ticker has no price rows at all.

    Pushes the ordering into two bounded queries — the nearest row on-or-
    after `as_of` and the nearest row strictly before it — rather than
    loading the ticker's full price history into Python and scanning it.
    At most two rows ever cross the wire; the final nearest-of-two
    comparison is a trivial Python min() over that pair.
    """
    from app.models import Price

    on_or_after = session.scalars(
        select(Price)
        .where(Price.ticker == ticker, Price.as_of >= as_of)
        .order_by(Price.as_of.asc())
        .limit(1)
    ).one_or_none()

    before = session.scalars(
        select(Price)
        .where(Price.ticker == ticker, Price.as_of < as_of)
        .order_by(Price.as_of.desc())
        .limit(1)
    ).one_or_none()

    candidates = [p for p in (on_or_after, before) if p is not None]
    if not candidates:
        return None

    nearest = min(candidates, key=lambda p: abs((p.as_of - as_of).days))
    return Decimal(nearest.close)


def compute_market_cap(shares_entry: dict, session: Session, ticker: str) -> Decimal | None:
    """shares_outstanding x closing_price_nearest(as_of_date) — Pattern 3.

    There is no MarketCap XBRL concept in either taxonomy (verified live
    against NVDA's companyfacts). `shares_entry["end"]` is the as-of date
    the shares figure was reported for; the nearest ingested close to that
    date stands in for "the market cap as of that filing".

    Returns None — never 0 — when no close is available for `ticker`. A
    null market cap is an honest "we could not compute this"; a zero
    would make the company look free in every downstream relative-value
    screen, which is a far worse failure than a visible gap.

    Multiplication is performed entirely in Decimal (never float): share
    counts reach the tens of billions (NVDA's verified entry is
    24,300,000,000) and prices carry fractional cents, so a binary float
    product would introduce drift in low-order digits of a figure later
    phases rank companies against. No rounding is applied — the stored
    value is the full-precision product.
    """
    as_of = date.fromisoformat(shares_entry["end"])
    nearest_close = find_nearest_close(session, ticker, as_of)
    if nearest_close is None:
        return None

    shares = Decimal(str(shares_entry["val"]))
    return shares * nearest_close


def _nearest_shares_entry(shares_entries: list[dict], period_end: date) -> dict | None:
    """Fallback shares-entry lookup when a filing has no shares entry
    sharing its own (fy, fp, accn) key: pick the raw shares entry whose
    `end` is nearest the filing's period_end, across the ticker's full
    shares-entry history.
    """
    if not shares_entries:
        return None
    return min(
        shares_entries,
        key=lambda entry: abs((date.fromisoformat(entry["end"]) - period_end).days),
    )


def _reduce_to_headline_per_filing(entries: list[dict]) -> dict[tuple, dict]:
    """Reduce a concept's raw entry list to one entry per (fy, fp, accn).

    A single accession can carry many duration facts for the same concept
    — quarterly breakdowns and prior-year comparatives shown alongside the
    filing's own headline figure, all sharing the same fy/fp/accn context
    (this is real, verified EDGAR behavior, not a fixture artifact). Within
    one filing, the entry with the latest `end` date is that filing's own
    headline period (whether an annual 10-K/20-F total or a 10-Q's current
    quarter) — comparative/quarterly entries always have an earlier `end`.

    Entries missing fy, fp, or accn are skipped: FactRow's provenance
    fields must be non-empty (every extracted fact must trace back to a
    specific filing), and an entry without a usable fiscal-year/period tag
    cannot satisfy that.
    """
    reduced: dict[tuple, dict] = {}
    for entry in entries:
        fy, fp, accn = entry.get("fy"), entry.get("fp"), entry.get("accn")
        if fy is None or fp is None or not accn:
            continue
        key = (fy, fp, accn)
        existing = reduced.get(key)
        if existing is None or entry["end"] > existing["end"]:
            reduced[key] = entry
    return reduced


def extract_fundamentals(
    facts: dict, session: Session, ticker: str, years: int = 5
) -> list[FactRow]:
    """Extract revenue, net income, shares outstanding, and derived market
    cap across the trailing `years` of filing history, one FactRow per
    filing.

    Detects the taxonomy once, then extracts each concept and reduces it
    to one headline entry per (fiscal_year, fiscal_period, accession
    number) filing. Revenue and net income are per-concept lists that are
    NOT guaranteed to be the same length or order, so they are joined on
    that key rather than zipped positionally.

    Market cap needs database access for the price lookup (Pattern 3),
    so `session` is passed in rather than opened inside this module —
    the caller owns transaction scope and this function stays testable
    against an injected session. The shares entry is matched to each
    filing by its own (fiscal_year, fiscal_period, accession_number) key
    first; when no shares entry shares that exact filing key, the shares
    entry nearest the filing's period_end is used instead so market cap
    can still be derived for a filing whose shares figure was reported
    under a different accession.

    The history cutoff is today minus `years` years; a filing's `end`
    (period_end) must be >= the cutoff to be included — the boundary is
    closed at the cutoff, not open.

    Results are sorted ascending by (period_end, filed_date,
    accession_number) so equal-period entries never reorder between runs.
    """
    taxonomy = pick_taxonomy(facts)

    revenue_by_key = _reduce_to_headline_per_filing(extract_concept(facts, taxonomy, "revenue"))
    net_income_by_key = _reduce_to_headline_per_filing(
        extract_concept(facts, taxonomy, "net_income")
    )
    shares_entries = _extract_shares(facts, taxonomy)
    shares_by_key = _reduce_to_headline_per_filing(shares_entries)

    cutoff = _years_ago(date.today(), years)

    rows: list[FactRow] = []
    for key in set(revenue_by_key) | set(net_income_by_key):
        fiscal_year, fiscal_period, accession_number = key
        # Prefer revenue's own record for the shared provenance fields
        # (filed/form/end) since revenue is present slightly more often
        # than net income across real filing history; fall back to net
        # income's record when revenue is absent for this filing.
        anchor = revenue_by_key.get(key) or net_income_by_key[key]

        period_end = date.fromisoformat(anchor["end"])
        if period_end < cutoff:
            continue

        shares_entry = shares_by_key.get(key) or _nearest_shares_entry(shares_entries, period_end)
        market_cap = (
            compute_market_cap(shares_entry, session, ticker) if shares_entry is not None else None
        )

        rows.append(
            FactRow(
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                form=anchor["form"],
                accession_number=accession_number,
                filed_date=date.fromisoformat(anchor["filed"]),
                period_end=period_end,
                revenue=revenue_by_key[key]["val"] if key in revenue_by_key else None,
                net_income=net_income_by_key[key]["val"] if key in net_income_by_key else None,
                shares_outstanding=shares_entry["val"] if shares_entry is not None else None,
                market_cap=market_cap,
                taxonomy=taxonomy,
            )
        )

    rows.sort(key=lambda r: (r.period_end, r.filed_date, r.accession_number))
    return rows


def _years_ago(today: date, years: int) -> date:
    """today minus `years` calendar years, defensively handling a Feb 29
    `today` on a non-leap target year.
    """
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        # today is Feb 29 and (today.year - years) is not a leap year
        return today.replace(month=2, day=28, year=today.year - years)


def write_fundamentals(session: Session, ticker: str, rows: list[FactRow]) -> None:
    """Persist FactRows with insert-or-ignore semantics on the four-column
    `uq_fundamental_period_filing` key (ticker, fiscal_year,
    fiscal_period, accession_number) — Pattern 4 / D-09.

    Deliberately insert-or-ignore, never upsert-by-ticker and never
    on-conflict-update. RESEARCH.md Pitfall 5: "just update the row for
    this ticker" is the natural instinct for a refresh script and is
    correct for prices, but wrong here — it replaces prior periods on
    every run and eventually leaves a single row per company, silently
    violating D-09's full-history requirement. When SEC later posts a
    restatement it arrives under a new accession_number, so it inserts
    as an additional row and both the original and the restated figures
    survive; on-conflict-update would destroy the original.

    The dialect-appropriate on-conflict construct is selected from the
    bound engine so the same code path works unmodified on both SQLite
    and Postgres (STORE-01's DATABASE_URL-swap premise).
    """
    from app.models import Fundamental

    if not rows:
        return

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

    values = [
        {
            "ticker": ticker,
            "fiscal_year": row.fiscal_year,
            "fiscal_period": row.fiscal_period,
            "form": row.form,
            "accession_number": row.accession_number,
            "filed_date": row.filed_date,
            "period_end": row.period_end,
            "revenue": row.revenue,
            "net_income": row.net_income,
            "market_cap": row.market_cap,
            "taxonomy": row.taxonomy,
        }
        for row in rows
    ]

    stmt = dialect_insert(Fundamental).values(values)
    # index_elements (not a bare constraint name) is the one conflict-target
    # spelling both the sqlite and postgresql dialects accept identically —
    # sqlite's on_conflict_do_nothing() has no `constraint=` kwarg at all.
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["ticker", "fiscal_year", "fiscal_period", "accession_number"]
    )
    session.execute(stmt)
