"""Tests for app.ingest.refresh — STORE-02 per-ticker failure isolation.

The price fetcher is always mocked (mocker.patch on app.ingest.refresh's
imported fetch_price) so failures are injectable deterministically and no
test makes a live network call.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.ingest.prices import NoPriceDataError, PriceRow
from app.ingest.refresh import TickerFailure, _main, record_failure, run_refresh
from app.models import Price, RefreshLog


def _write_taxonomy(tmp_path: Path, tickers: list[str]) -> Path:
    path = tmp_path / "sectors.yaml"
    companies = [{"ticker": t, "name": f"{t} Inc.", "sub_sector": "test-sector"} for t in tickers]
    path.write_text(yaml.safe_dump({"companies": companies}))
    return path


def _fake_fetch_price(row_by_ticker=None, raise_for=None):
    """Build a fetch_price replacement. raise_for maps ticker -> exception instance."""
    row_by_ticker = row_by_ticker or {}
    raise_for = raise_for or {}

    def _fetch(ticker: str) -> PriceRow:
        if ticker in raise_for:
            raise raise_for[ticker]
        return row_by_ticker.get(
            ticker, PriceRow(ticker=ticker, close=Decimal("10.00"), as_of=date(2026, 7, 17))
        )

    return _fetch


def test_partial_failure_continues(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2", "TICK3"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(raise_for={"TICK2": ValueError("no data")}),
    )

    result = run_refresh(db_session, taxonomy_path)

    assert result.tickers_attempted == 3
    assert result.failure_count == 1
    assert [f.ticker for f in result.failures] == ["TICK2"]

    prices = db_session.query(Price).all()
    assert {p.ticker for p in prices} == {"TICK1", "TICK3"}

    logs = db_session.query(RefreshLog).all()
    assert len(logs) == 1
    assert logs[0].failure_count == 1


def test_all_tickers_fail_still_completes(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(
            raise_for={"TICK1": ValueError("boom"), "TICK2": ValueError("boom")}
        ),
    )

    result = run_refresh(db_session, taxonomy_path)

    assert result.tickers_attempted == 2
    assert result.failure_count == 2
    assert db_session.query(Price).count() == 0
    log = db_session.query(RefreshLog).one()
    assert log.failure_count == 2


def test_all_succeed_writes_clean_refresh_log(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())

    result = run_refresh(db_session, taxonomy_path)

    assert result.failure_count == 0
    assert result.failures == []
    log = db_session.query(RefreshLog).one()
    assert log.failure_count == 0
    assert log.failures == []


def test_empty_taxonomy_completes_with_zero_attempted(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, [])
    fetch_mock = mocker.patch("app.ingest.refresh.fetch_price")

    result = run_refresh(db_session, taxonomy_path)

    assert result.tickers_attempted == 0
    assert result.failures == []
    fetch_mock.assert_not_called()
    log = db_session.query(RefreshLog).one()
    assert log.tickers_attempted == 0
    assert db_session.query(Price).count() == 0


def test_duplicate_stage_failures_not_merged(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2", "TICK3"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(
            raise_for={"TICK1": ValueError("rate limited"), "TICK3": ValueError("rate limited")}
        ),
    )

    result = run_refresh(db_session, taxonomy_path)

    assert result.failure_count == 2
    assert len(result.failures) == 2
    assert result.failures[0] is not result.failures[1]


def test_failure_order_matches_taxonomy_order(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["AAA", "BBB", "CCC", "DDD"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(raise_for={"BBB": ValueError("x"), "DDD": ValueError("y")}),
    )

    result = run_refresh(db_session, taxonomy_path)

    assert [f.ticker for f in result.failures] == ["BBB", "DDD"]


def test_no_price_data_error_recorded_with_reason(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["DELISTED"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(raise_for={"DELISTED": NoPriceDataError("DELISTED")}),
    )

    result = run_refresh(db_session, taxonomy_path)

    assert result.failure_count == 1
    failure = result.failures[0]
    assert failure.ticker == "DELISTED"
    assert "DELISTED" in failure.error


def test_interrupted_run_persists_completed_tickers(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2", "TICK3"])

    def _fetch(ticker: str) -> PriceRow:
        if ticker == "TICK3":
            raise KeyboardInterrupt()
        return PriceRow(ticker=ticker, close=Decimal("10.00"), as_of=date(2026, 7, 17))

    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fetch)

    with pytest.raises(KeyboardInterrupt):
        run_refresh(db_session, taxonomy_path)

    prices = db_session.query(Price).all()
    assert {p.ticker for p in prices} == {"TICK1", "TICK2"}


def test_module_entrypoint_exits_0_with_partial_failures(tmp_path, mocker, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from app.config import get_settings
    from app.db import get_engine, get_session_factory
    from app.models import Base

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = get_engine()
    Base.metadata.create_all(engine)

    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "BADTICK"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(raise_for={"BADTICK": ValueError("no data")}),
    )

    exit_code = _main([str(taxonomy_path)])

    assert exit_code == 0

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_record_failure_appends_without_deduplicating():
    failures: list[TickerFailure] = []
    record_failure(failures, "AAA", "price", ValueError("x"))
    record_failure(failures, "AAA", "price", ValueError("x"))

    assert len(failures) == 2
