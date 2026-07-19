"""Phase 1 Wave 0 end-to-end test: sectors.yaml -> DB -> GET /companies.

This test is intentionally written before app.main / app.ingest.taxonomy
exist (RED state). Task 2 makes it pass (GREEN state).

Plan 01-02 (Task 3) adds price-block coverage below the original test,
which is left unmodified per that plan's own acceptance criteria.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

SECTORS_YAML = Path(__file__).parent.parent / "sectors.yaml"


def test_companies_returns_full_taxonomy(tmp_path, monkeypatch):
    db_path = tmp_path / "e2e.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EDGAR_USER_AGENT", "DataCenterStocks sureshkrip@gmail.com")

    from app.config import get_settings
    from app.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from app.ingest.taxonomy import load_taxonomy, sync_taxonomy
    from app.main import app
    from app.models import Base

    engine = create_engine(get_settings().database_url)
    Base.metadata.create_all(engine)

    config = load_taxonomy(SECTORS_YAML)
    with Session(engine) as session:
        sync_taxonomy(session, config)
        session.commit()

    client = TestClient(app)
    response = client.get("/companies")

    assert response.status_code == 200
    body = response.json()

    assert len(body) == len(config.companies)

    for item in body:
        taxonomy = item["taxonomy"]
        assert taxonomy["ticker"]
        assert taxonomy["name"]
        assert taxonomy["sub_sector"]

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _setup_seeded_app(tmp_path, monkeypatch):
    """Shared setup for the price-block tests below: a fresh SQLite DB
    with the full sectors.yaml taxonomy synced in, plus the app/engine
    to run further seeding and requests against.
    """
    db_path = tmp_path / "e2e.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EDGAR_USER_AGENT", "DataCenterStocks sureshkrip@gmail.com")

    from app.config import get_settings
    from app.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from app.ingest.taxonomy import load_taxonomy, sync_taxonomy
    from app.main import app
    from app.models import Base

    engine = create_engine(get_settings().database_url)
    Base.metadata.create_all(engine)

    config = load_taxonomy(SECTORS_YAML)
    with Session(engine) as session:
        sync_taxonomy(session, config)
        session.commit()

    return app, engine, config


def _reset_caches():
    from app.config import get_settings
    from app.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_companies_returns_later_price_when_two_rows_exist(tmp_path, monkeypatch):
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)
    from app.models import Price

    with Session(engine) as session:
        session.add(
            Price(ticker="NVDA", close=Decimal("100.00"), as_of=date(2026, 7, 16), source="yfinance")
        )
        session.add(
            Price(ticker="NVDA", close=Decimal("105.50"), as_of=date(2026, 7, 17), source="yfinance")
        )
        session.commit()

    client = TestClient(app)
    response = client.get("/companies")
    assert response.status_code == 200

    body = response.json()
    nvda = next(item for item in body if item["taxonomy"]["ticker"] == "NVDA")

    assert nvda["price"] is not None
    assert nvda["price"]["as_of"] == "2026-07-17"
    assert nvda["price"]["value"] == 105.50
    assert nvda["price"]["source"] == "yfinance"

    _reset_caches()


def test_companies_price_null_when_no_price_row_taxonomy_still_populated(tmp_path, monkeypatch):
    app, engine, config = _setup_seeded_app(tmp_path, monkeypatch)

    client = TestClient(app)
    response = client.get("/companies")
    assert response.status_code == 200

    body = response.json()
    assert len(body) == len(config.companies)

    for item in body:
        assert item["price"] is None
        assert item["taxonomy"]["ticker"]
        assert item["taxonomy"]["name"]
        assert item["taxonomy"]["sub_sector"]

    _reset_caches()


def test_companies_endpoint_query_count_is_bounded(tmp_path, monkeypatch):
    """No N+1: the price join must be a fixed number of round-trips
    regardless of how many tickers the taxonomy holds (54 here)."""
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)
    from app.models import Price

    with Session(engine) as session:
        session.add(
            Price(ticker="NVDA", close=Decimal("100.00"), as_of=date(2026, 7, 17), source="yfinance")
        )
        session.commit()

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        client = TestClient(app)
        response = client.get("/companies")
        assert response.status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(statements) <= 3

    _reset_caches()


def _fundamental_row(ticker: str, fiscal_year: int, fiscal_period: str, accession_number: str, **overrides):
    from app.models import Fundamental

    defaults = dict(
        ticker=ticker,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form="10-K",
        accession_number=accession_number,
        filed_date=date(fiscal_year, 2, 25),
        period_end=date(fiscal_year, 1, 28),
        revenue=Decimal("1000.00"),
        net_income=Decimal("100.00"),
        market_cap=Decimal("5000.00"),
        taxonomy="us-gaap",
    )
    defaults.update(overrides)
    return Fundamental(**defaults)


def test_companies_returns_full_multi_year_fundamentals_history(tmp_path, monkeypatch):
    """D-09 proof: 8 seeded rows across 3 fiscal years for one ticker
    come back as 8 entries, not just the latest."""
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)

    periods_by_year = {2023: ("Q1", "Q2", "Q3"), 2024: ("Q1", "Q2", "Q3"), 2025: ("Q1", "Q2")}
    with Session(engine) as session:
        for fy, periods in periods_by_year.items():
            for period in periods:
                session.add(
                    _fundamental_row("NVDA", fy, period, f"0001045810-{fy}-{period}")
                )
        session.commit()

    client = TestClient(app)
    response = client.get("/companies")
    assert response.status_code == 200

    body = response.json()
    nvda = next(item for item in body if item["taxonomy"]["ticker"] == "NVDA")
    assert len(nvda["fundamentals"]) == 8

    _reset_caches()


def test_companies_fundamentals_entries_carry_provenance(tmp_path, monkeypatch):
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)

    with Session(engine) as session:
        session.add(_fundamental_row("NVDA", 2025, "FY", "0001045810-25-000001"))
        session.commit()

    client = TestClient(app)
    response = client.get("/companies")
    body = response.json()
    nvda = next(item for item in body if item["taxonomy"]["ticker"] == "NVDA")

    assert len(nvda["fundamentals"]) == 1
    entry = nvda["fundamentals"][0]
    assert entry["accession_number"]
    assert entry["filed_date"]

    _reset_caches()


def test_companies_empty_fundamentals_array_when_uningested(tmp_path, monkeypatch):
    app, engine, config = _setup_seeded_app(tmp_path, monkeypatch)

    client = TestClient(app)
    response = client.get("/companies")
    body = response.json()

    assert len(body) == len(config.companies)
    for item in body:
        assert item["fundamentals"] == []
        assert item["taxonomy"]["ticker"]
        assert item["taxonomy"]["name"]
        assert item["taxonomy"]["sub_sector"]

    _reset_caches()


def test_companies_fundamentals_order_stable_across_requests(tmp_path, monkeypatch):
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)

    with Session(engine) as session:
        session.add(_fundamental_row("NVDA", 2024, "FY", "0001045810-24-000001"))
        session.add(_fundamental_row("NVDA", 2025, "FY", "0001045810-25-000001"))
        session.add(_fundamental_row("NVDA", 2023, "FY", "0001045810-23-000001"))
        session.commit()

    client = TestClient(app)
    body1 = client.get("/companies").json()
    body2 = client.get("/companies").json()

    nvda1 = next(item for item in body1 if item["taxonomy"]["ticker"] == "NVDA")["fundamentals"]
    nvda2 = next(item for item in body2 if item["taxonomy"]["ticker"] == "NVDA")["fundamentals"]

    assert nvda1 == nvda2
    assert [e["fiscal_year"] for e in nvda1] == [2023, 2024, 2025]

    _reset_caches()


def test_companies_restatement_disambiguated_in_deterministic_order(tmp_path, monkeypatch):
    app, engine, _config = _setup_seeded_app(tmp_path, monkeypatch)

    with Session(engine) as session:
        session.add(
            _fundamental_row(
                "NVDA", 2025, "FY", "0001045810-25-000001",
                period_end=date(2025, 1, 28), filed_date=date(2025, 2, 25), revenue=Decimal("1000.00"),
            )
        )
        session.add(
            _fundamental_row(
                "NVDA", 2025, "FY", "0001045810-25-000009",
                period_end=date(2025, 1, 28), filed_date=date(2025, 4, 1), revenue=Decimal("1050.00"),
            )
        )
        session.commit()

    client = TestClient(app)
    response = client.get("/companies")
    body = response.json()
    nvda = next(item for item in body if item["taxonomy"]["ticker"] == "NVDA")["fundamentals"]

    assert len(nvda) == 2
    assert [e["accession_number"] for e in nvda] == [
        "0001045810-25-000001",
        "0001045810-25-000009",
    ]

    _reset_caches()


def test_companies_endpoint_has_exactly_one_route():
    source_path = Path(__file__).parent.parent / "app" / "api" / "companies.py"
    source = source_path.read_text()
    route_decorator_count = source.count("@router.get") + source.count("@app.get")
    assert route_decorator_count == 1
