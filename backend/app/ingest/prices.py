"""Price fetcher (INGEST-01) — bounded retry + normalized single-vs-multi
ticker handling.

fetch_prices() uses yfinance.download() over the requested ticker list in
one batched call. It never loops a per-symbol Ticker metadata lookup —
RESEARCH.md's Anti-Patterns section and Pitfall 4 both identify that
pattern as the direct cause of cascading 429s across a 55-ticker run,
where later tickers fail even though earlier ones succeeded. A 5-day
window (not 1-day) guarantees at least one trading day is present even
when the run fires on a weekend or a market holiday.

fetch_price() is the per-ticker path the orchestrator (refresh.py) calls
inside its own try/except for STORE-02 isolation; it wraps a single-
element fetch_prices() call with bounded, jittered retry (T-01-06/T-01-07).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


class NoPriceDataError(Exception):
    """Raised when a ticker's provider response has no rows for the
    requested window.

    This is a real per-ticker failure the owner needs surfaced in the
    refresh log — writing a null close instead would make a delisted or
    mistyped ticker indistinguishable from a healthy one at the API layer.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"No price data returned for {ticker!r} in the requested window")


@dataclass
class PriceRow:
    ticker: str
    close: Decimal
    as_of: date
    source: str = "yfinance"


def _to_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _extract_row(df: pd.DataFrame, ticker: str) -> PriceRow:
    """Pull the most recent non-null Close for one ticker out of a
    yfinance.download() result.

    yfinance.download() returns a differently-shaped DataFrame for a
    single ticker (flat columns) than for multiple tickers (MultiIndex
    columns keyed by ticker) — both shapes are normalized here into the
    same per-ticker PriceRow so a taxonomy pared down to one ticker does
    not silently produce a different row shape than the full universe.
    """
    if isinstance(df.columns, pd.MultiIndex):
        top_level = df.columns.get_level_values(0)
        close_field = "Close" if "Close" in top_level else "Adj Close"
        if close_field not in top_level or ticker not in df[close_field].columns:
            raise NoPriceDataError(ticker)
        close_series = df[close_field][ticker].dropna()
    else:
        close_field = "Close" if "Close" in df.columns else "Adj Close"
        if close_field not in df.columns:
            raise NoPriceDataError(ticker)
        close_series = df[close_field].dropna()

    if close_series.empty:
        raise NoPriceDataError(ticker)

    as_of = _to_date(close_series.index[-1])
    # Convert via str() rather than passing the binary float directly, so
    # full source precision reaches the Numeric column with no rounding or
    # truncation at ingest time. Display rounding is a later concern.
    close = Decimal(str(close_series.iloc[-1]))
    return PriceRow(ticker=ticker, close=close, as_of=as_of, source="yfinance")


def fetch_prices(tickers: list[str]) -> list[PriceRow]:
    """Fetch the most recent close for each ticker in one batched call.

    An empty ticker list returns an empty list without issuing any
    network call.
    """
    if not tickers:
        return []

    # Batch yf.download() over the full list — not a per-symbol Ticker
    # metadata loop, which cascades 429s across a multi-ticker run.
    # multi_level_index=False is what actually produces the differing
    # single-ticker (flat columns) vs multi-ticker (MultiIndex columns)
    # shapes on the installed yfinance 1.x line — verified live against
    # 1.5.1, since 1.x's default (multi_level_index=True) returns
    # MultiIndex columns for a 1-item list too.
    df = yf.download(
        tickers,
        period="5d",
        auto_adjust=False,
        progress=False,
        timeout=10,
        multi_level_index=False,
    )

    return [_extract_row(df, ticker) for ticker in tickers]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    reraise=True,
)
def fetch_price(ticker: str) -> PriceRow:
    """Per-ticker path used by the orchestrator's isolated error handling.

    Bounded at 3 attempts with jittered exponential backoff so 55 tickers
    retrying in lockstep against a rate-limited endpoint desynchronize
    rather than forming a thundering herd (T-01-07). reraise=True so the
    underlying error reaches refresh.py's except block undisguised by
    tenacity's own RetryError.
    """
    return fetch_prices([ticker])[0]


def write_price(session: Session, row: PriceRow) -> None:
    """Insert-or-update keyed on the uq_price_ticker_date constraint.

    Prices are correctly update-on-conflict — re-running the refresh on
    the same trading day refreshes that day's close rather than colliding
    or duplicating. (Unlike fundamentals, where plan 04 must use
    insert-or-ignore to preserve filing history.)
    """
    from app.models import Price

    existing = session.scalars(
        select(Price).where(Price.ticker == row.ticker, Price.as_of == row.as_of)
    ).one_or_none()

    if existing is None:
        session.add(Price(ticker=row.ticker, close=row.close, as_of=row.as_of, source=row.source))
    else:
        existing.close = row.close
        existing.source = row.source
