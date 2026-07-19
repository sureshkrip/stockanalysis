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
