"""Tests for app.ingest.prices — INGEST-01.

The yfinance provider call is always mocked (respx/mocker/monkeypatch);
no test in this file makes a live network request.
"""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app.ingest.prices import (
    NoPriceDataError,
    PriceRow,
    fetch_price,
    fetch_prices,
    write_price,
)


def _multi_ticker_df(tickers: list[str], closes: list[float], dates: list[str]) -> pd.DataFrame:
    """Build a MultiIndex-column DataFrame mimicking yf.download() for
    multiple tickers: top level 'Close', second level ticker symbol.
    """
    idx = pd.to_datetime(dates)
    data = {("Close", t): [c] * len(dates) for t, c in zip(tickers, closes)}
    # last row carries the distinguishing close per ticker
    for i, t in enumerate(tickers):
        data[("Close", t)][-1] = closes[i]
    df = pd.DataFrame(data, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def _flat_df(close: float, dates: list[str]) -> pd.DataFrame:
    """Build a flat-column DataFrame mimicking yf.download() for a single
    ticker (the shape yfinance returns when passed one symbol).
    """
    idx = pd.to_datetime(dates)
    closes = [close] * len(dates)
    return pd.DataFrame({"Close": closes}, index=idx)


DATES = ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17"]


def test_fetch_prices_multi_ticker_returns_one_row_per_ticker(mocker):
    tickers = ["NVDA", "TSM", "AVGO"]
    df = _multi_ticker_df(tickers, [123.45, 210.10, 1500.00], DATES)
    mocker.patch("app.ingest.prices.yf.download", return_value=df)

    rows = fetch_prices(tickers)

    assert len(rows) == 3
    assert {r.ticker for r in rows} == set(tickers)
    for row in rows:
        assert row.source == "yfinance"
        assert row.as_of == date(2026, 7, 17)
        assert isinstance(row.close, Decimal)


def test_fetch_prices_single_ticker_matches_multi_shape(mocker):
    multi_df = _multi_ticker_df(["NVDA", "TSM", "AVGO"], [123.45, 210.10, 1500.00], DATES)
    flat_df = _flat_df(123.45, DATES)

    mocker.patch("app.ingest.prices.yf.download", return_value=multi_df)
    multi_rows = fetch_prices(["NVDA"])

    mocker.patch("app.ingest.prices.yf.download", return_value=flat_df)
    single_rows = fetch_prices(["NVDA"])

    assert len(multi_rows) == 1 == len(single_rows)
    assert multi_rows[0].ticker == single_rows[0].ticker == "NVDA"
    assert multi_rows[0].as_of == single_rows[0].as_of
    assert multi_rows[0].source == single_rows[0].source == "yfinance"
    assert isinstance(multi_rows[0].close, Decimal)
    assert isinstance(single_rows[0].close, Decimal)


def test_fetch_prices_empty_list_returns_empty_without_network_call(mocker):
    download_mock = mocker.patch("app.ingest.prices.yf.download")

    rows = fetch_prices([])

    assert rows == []
    download_mock.assert_not_called()


def test_fetch_prices_no_rows_for_window_raises_named_error(mocker):
    # ticker column present but every Close value is NaN -> no valid rows
    df = _flat_df(float("nan"), DATES)
    mocker.patch("app.ingest.prices.yf.download", return_value=df)

    with pytest.raises(NoPriceDataError) as exc_info:
        fetch_prices(["DELISTED"])

    assert exc_info.value.ticker == "DELISTED"
    assert "DELISTED" in str(exc_info.value)


def test_fetch_price_success(mocker):
    df = _flat_df(99.99, DATES)
    mocker.patch("app.ingest.prices.yf.download", return_value=df)

    row = fetch_price("NVDA")

    assert isinstance(row, PriceRow)
    assert row.ticker == "NVDA"
    assert row.source == "yfinance"
    assert row.as_of == date(2026, 7, 17)


def test_fetch_price_retries_transient_failure_then_succeeds(mocker):
    df = _flat_df(50.00, DATES)
    download_mock = mocker.patch(
        "app.ingest.prices.yf.download",
        side_effect=[ConnectionError("429 Too Many Requests"), df],
    )

    row = fetch_price("NVDA")

    assert row.ticker == "NVDA"
    assert download_mock.call_count == 2


def test_fetch_price_exhausts_retry_budget_bounded_at_3(mocker):
    download_mock = mocker.patch(
        "app.ingest.prices.yf.download",
        side_effect=ConnectionError("429 Too Many Requests"),
    )

    with pytest.raises(ConnectionError):
        fetch_price("NVDA")

    assert download_mock.call_count == 3


def test_write_price_upsert_same_ticker_date_leaves_one_row(db_session):
    row1 = PriceRow(ticker="NVDA", close=Decimal("100.00"), as_of=date(2026, 7, 17))
    row2 = PriceRow(ticker="NVDA", close=Decimal("105.50"), as_of=date(2026, 7, 17))

    write_price(db_session, row1)
    db_session.commit()
    write_price(db_session, row2)
    db_session.commit()

    from app.models import Price

    rows = db_session.query(Price).filter_by(ticker="NVDA").all()
    assert len(rows) == 1
    assert rows[0].close == Decimal("105.50")


def test_write_price_different_dates_leaves_two_rows(db_session):
    row1 = PriceRow(ticker="NVDA", close=Decimal("100.00"), as_of=date(2026, 7, 16))
    row2 = PriceRow(ticker="NVDA", close=Decimal("101.00"), as_of=date(2026, 7, 17))

    write_price(db_session, row1)
    db_session.commit()
    write_price(db_session, row2)
    db_session.commit()

    from app.models import Price

    rows = db_session.query(Price).filter_by(ticker="NVDA").all()
    assert len(rows) == 2


def test_write_price_preserves_decimal_precision(db_session):
    precise_close = Decimal("123.456789123")
    row = PriceRow(ticker="NVDA", close=precise_close, as_of=date(2026, 7, 17))

    write_price(db_session, row)
    db_session.commit()

    from app.models import Price

    persisted = db_session.query(Price).filter_by(ticker="NVDA").one()
    assert persisted.close == precise_close
