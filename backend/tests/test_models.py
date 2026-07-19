"""Tests for STORE-01: SQLAlchemy models, CRUD roundtrip, point-in-time uniqueness."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError


def test_crud_roundtrip(db_session):
    from app.models import Ticker

    ticker = Ticker(ticker="NVDA", name="NVIDIA", sub_sector="ai_chips")
    db_session.add(ticker)
    db_session.commit()

    fetched = db_session.get(Ticker, "NVDA")
    assert fetched is not None
    assert fetched.name == "NVIDIA"
    assert fetched.sub_sector == "ai_chips"


def test_fundamental_unique_constraint_blocks_exact_duplicate(db_session):
    from app.models import Fundamental, Ticker

    db_session.add(Ticker(ticker="NVDA", name="NVIDIA", sub_sector="ai_chips"))
    db_session.commit()

    def make_row(accession_number: str) -> "Fundamental":
        return Fundamental(
            ticker="NVDA",
            fiscal_year=2026,
            fiscal_period="FY",
            form="10-K",
            accession_number=accession_number,
            filed_date=date(2026, 2, 25),
            period_end=date(2026, 1, 25),
            revenue=100.0,
            net_income=50.0,
            market_cap=None,
            taxonomy="us-gaap",
        )

    db_session.add(make_row("0001045810-26-000021"))
    db_session.commit()

    db_session.add(make_row("0001045810-26-000021"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same tuple differing only in accession_number inserts as a second row.
    db_session.add(make_row("0001045810-26-000099"))
    db_session.commit()

    from sqlalchemy import select

    rows = db_session.scalars(select(Fundamental).where(Fundamental.ticker == "NVDA")).all()
    assert len(rows) == 2
