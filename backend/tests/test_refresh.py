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

from app.ingest.cik_resolver import CikNotFoundError
from app.ingest.fundamentals import FactRow, write_fundamentals
from app.ingest.prices import NoPriceDataError, PriceRow
from app.ingest.refresh import TickerFailure, _main, record_failure, run_refresh
from app.models import Fundamental, Price, RefreshLog


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


def _fake_resolve_cik(raise_for=None):
    """Build a resolve_cik replacement matching (session, ticker) -> cik.
    raise_for maps ticker -> exception instance."""
    raise_for = raise_for or {}

    def _resolve(session, ticker):
        if ticker in raise_for:
            raise raise_for[ticker]
        return f"CIK-{ticker}"

    return _resolve


def _synthetic_companyfacts(n_periods: int = 5) -> dict:
    """A synthetic us-gaap companyfacts payload with `n_periods` distinct
    annual filings (distinct fiscal_year + accession_number each), all
    within extract_fundamentals' default 5-year trailing history window
    so none are cut off by the cutoff boundary.
    """
    today = date.today()
    revenue_entries = []
    net_income_entries = []
    for i in range(n_periods):
        year = today.year - i
        end = date(year, 1, 28).isoformat()
        filed = date(year, 2, 25).isoformat()
        accn = f"0000000000-{year}-{i:06d}"
        entry_base = {
            "start": f"{year - 1}-01-29",
            "end": end,
            "accn": accn,
            "fy": year,
            "fp": "FY",
            "form": "10-K",
            "filed": filed,
        }
        revenue_entries.append({**entry_base, "val": 1_000_000 + i})
        net_income_entries.append({**entry_base, "val": 100_000 + i})

    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": revenue_entries}
                },
                "NetIncomeLoss": {"units": {"USD": net_income_entries}},
            }
        }
    }


def _fake_get_companyfacts(raise_for_cik=None, n_periods=5):
    """Build a get_companyfacts replacement. raise_for_cik maps cik ->
    exception instance; every other cik gets a synthetic multi-period
    companyfacts payload.
    """
    raise_for_cik = raise_for_cik or {}

    def _get(cik: str) -> dict:
        if cik in raise_for_cik:
            raise raise_for_cik[cik]
        return _synthetic_companyfacts(n_periods)

    return _get


@pytest.fixture(autouse=True)
def _mock_edgar_by_default(mocker):
    """Every test in this file must never make a live EDGAR call. All
    pre-existing tests only exercise the price stage, so give the CIK
    and fundamentals stages harmless default mocks here; tests that
    specifically exercise those stages re-patch these same targets with
    more specific behavior (the later patch wins).
    """
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch("app.ingest.refresh.get_companyfacts", side_effect=_fake_get_companyfacts())


def _fact_row(
    fiscal_year=2025,
    fiscal_period="FY",
    accession_number="0000000000-25-000001",
    **overrides,
) -> FactRow:
    defaults = dict(
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form="10-K",
        accession_number=accession_number,
        filed_date=date(2025, 2, 25),
        period_end=date(2025, 1, 28),
        revenue=1000.0,
        net_income=100.0,
        shares_outstanding=1_000_000.0,
        market_cap=None,
        taxonomy="us-gaap",
    )
    defaults.update(overrides)
    return FactRow(**defaults)


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


# --- write_fundamentals: point-in-time persistence (Pattern 4, D-09) ----


def test_write_fundamentals_twice_with_identical_rows_leaves_count_unchanged(db_session):
    row = _fact_row()

    write_fundamentals(db_session, "NVDA", [row])
    db_session.commit()
    write_fundamentals(db_session, "NVDA", [row])
    db_session.commit()

    assert db_session.query(Fundamental).count() == 1


def test_write_fundamentals_restatement_new_accession_inserts_additional_row(db_session):
    original = _fact_row(accession_number="0000000000-25-000001", revenue=1000.0)
    restated = _fact_row(accession_number="0000000000-25-000009", revenue=1050.0)

    write_fundamentals(db_session, "NVDA", [original])
    db_session.commit()
    write_fundamentals(db_session, "NVDA", [restated])
    db_session.commit()

    rows = db_session.query(Fundamental).all()
    assert len(rows) == 2
    assert {float(r.revenue) for r in rows} == {1000.0, 1050.0}


def test_write_fundamentals_differing_fiscal_period_inserts_additional_row(db_session):
    q1 = _fact_row(fiscal_period="Q1", accession_number="0000000000-25-000002")
    q2 = _fact_row(fiscal_period="Q2", accession_number="0000000000-25-000003")

    write_fundamentals(db_session, "NVDA", [q1, q2])
    db_session.commit()

    assert db_session.query(Fundamental).count() == 2


# --- run_refresh: fundamentals stage wired into the resilient loop -----


def test_fundamentals_stage_isolated_middle_ticker_failure(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2", "TICK3"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch(
        "app.ingest.refresh.get_companyfacts",
        side_effect=_fake_get_companyfacts(raise_for_cik={"CIK-TICK2": ValueError("edgar down")}),
    )

    result = run_refresh(db_session, taxonomy_path)

    fundamentals_failures = [f for f in result.failures if f.stage == "fundamentals"]
    assert len(fundamentals_failures) == 1
    assert fundamentals_failures[0].ticker == "TICK2"

    tickers_with_fundamentals = {f.ticker for f in db_session.query(Fundamental).all()}
    assert tickers_with_fundamentals == {"TICK1", "TICK3"}


def test_price_failure_does_not_block_fundamentals(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1"])
    mocker.patch(
        "app.ingest.refresh.fetch_price",
        side_effect=_fake_fetch_price(raise_for={"TICK1": ValueError("price down")}),
    )
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch("app.ingest.refresh.get_companyfacts", side_effect=_fake_get_companyfacts())

    result = run_refresh(db_session, taxonomy_path)

    stages = {f.stage for f in result.failures}
    assert "price" in stages
    assert "fundamentals" not in stages

    assert db_session.query(Fundamental).filter_by(ticker="TICK1").count() > 0


def test_fundamentals_failure_does_not_block_price(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch(
        "app.ingest.refresh.get_companyfacts",
        side_effect=_fake_get_companyfacts(raise_for_cik={"CIK-TICK1": ValueError("edgar down")}),
    )

    result = run_refresh(db_session, taxonomy_path)

    stages = {f.stage for f in result.failures}
    assert stages == {"fundamentals"}
    assert db_session.query(Price).filter_by(ticker="TICK1").count() == 1


def test_cik_failure_records_stage_and_skips_only_fundamentals(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch(
        "app.ingest.refresh.resolve_cik",
        side_effect=_fake_resolve_cik(raise_for={"TICK1": CikNotFoundError("TICK1")}),
    )
    get_companyfacts_mock = mocker.patch("app.ingest.refresh.get_companyfacts")

    result = run_refresh(db_session, taxonomy_path)

    assert [(f.ticker, f.stage) for f in result.failures] == [("TICK1", "cik")]
    get_companyfacts_mock.assert_not_called()
    assert db_session.query(Price).filter_by(ticker="TICK1").count() == 1


def test_refresh_twice_produces_identical_fundamentals_row_count(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch("app.ingest.refresh.get_companyfacts", side_effect=_fake_get_companyfacts())

    run_refresh(db_session, taxonomy_path)
    count_after_first = db_session.query(Fundamental).count()

    run_refresh(db_session, taxonomy_path)
    count_after_second = db_session.query(Fundamental).count()

    assert count_after_second == count_after_first
    assert count_after_first > 2  # multi-period history, not one row per ticker


def test_history_grows_beyond_three_rows_for_at_least_one_ticker(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())
    mocker.patch(
        "app.ingest.refresh.get_companyfacts",
        side_effect=_fake_get_companyfacts(n_periods=5),
    )

    run_refresh(db_session, taxonomy_path)

    assert db_session.query(Fundamental).filter_by(ticker="TICK1").count() > 3


def test_interrupted_run_persists_completed_tickers_fundamentals(db_session, tmp_path, mocker):
    taxonomy_path = _write_taxonomy(tmp_path, ["TICK1", "TICK2", "TICK3"])
    mocker.patch("app.ingest.refresh.fetch_price", side_effect=_fake_fetch_price())
    mocker.patch("app.ingest.refresh.resolve_cik", side_effect=_fake_resolve_cik())

    def _get(cik: str) -> dict:
        if cik == "CIK-TICK3":
            raise KeyboardInterrupt()
        return _synthetic_companyfacts()

    mocker.patch("app.ingest.refresh.get_companyfacts", side_effect=_get)

    with pytest.raises(KeyboardInterrupt):
        run_refresh(db_session, taxonomy_path)

    tickers_with_fundamentals = {f.ticker for f in db_session.query(Fundamental).all()}
    assert tickers_with_fundamentals == {"TICK1", "TICK2"}
