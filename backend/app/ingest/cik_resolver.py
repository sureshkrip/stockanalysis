"""CIK resolution with zero-padding and a persistent cache (D-06).

A ticker's CIK is resolved from SEC's published `company_tickers.json`
mapping, zero-padded to exactly 10 digits, and cached in the
`ticker_ciks` table so subsequent runs make no network call for it.
CIK is never hand-entered in sectors.yaml — it is pipeline-resolved.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.edgar_client import edgar_get
from app.models import TickerCik

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class CikNotFoundError(Exception):
    """Raised when a ticker is absent from SEC's company_tickers.json
    mapping.

    This is a legitimate per-ticker outcome (e.g. a very recent IPO not
    yet indexed) — the caller must treat it as a per-ticker failure
    (STORE-02) and continue the run, never abort on it.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"CIK not found for ticker {ticker!r} in SEC's company_tickers.json")


def fetch_company_tickers_json() -> dict:
    """Fetch SEC's ticker->CIK mapping.

    Shape: {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "..."},
    ...} — note cik_str is a plain integer despite its name.
    """
    response = edgar_get(COMPANY_TICKERS_URL)
    return response.json()


@lru_cache
def _build_ticker_to_cik_map() -> dict[str, str]:
    """Fetch the mapping once and zero-pad every CIK to 10 digits,
    caching in-memory for the duration of this run (a cold 56-ticker
    run issues one mapping request, not 56). Call
    `_build_ticker_to_cik_map.cache_clear()` between test runs so one
    test's mocked mapping never leaks into the next.
    """
    raw = fetch_company_tickers_json()
    return {entry["ticker"]: str(entry["cik_str"]).zfill(10) for entry in raw.values()}


def persist_cik_cache(session: Session, ticker: str, cik: str) -> None:
    """Insert a TickerCik row recording when this ticker's CIK was
    resolved, so a second resolve_cik() call is a cache hit with zero
    network calls.
    """
    session.add(TickerCik(ticker=ticker, cik=cik, resolved_at=datetime.now(timezone.utc)))


def resolve_cik(session: Session, ticker: str) -> str:
    """Resolve a ticker's zero-padded 10-digit CIK.

    Checks the ticker_ciks cache first — a hit returns with zero network
    calls. On a miss, fetches (or reuses the in-run cached) mapping,
    zero-pads via str(cik_str).zfill(10) (Pitfall 1 — the unpadded form
    404s at URL-construction time even though the CIK value itself is
    valid), persists the cache row, and returns it.

    Raises CikNotFoundError for a ticker absent from the mapping —
    never produces a malformed URL from a None CIK, and never aborts
    the caller's run.
    """
    cached = session.scalars(select(TickerCik).where(TickerCik.ticker == ticker)).one_or_none()
    if cached is not None:
        return cached.cik

    mapping = _build_ticker_to_cik_map()
    cik = mapping.get(ticker)
    if cik is None:
        raise CikNotFoundError(ticker)

    persist_cik_cache(session, ticker, cik)
    return cik
