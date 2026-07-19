"""GET /companies — D-08 nested taxonomy + price + fundamentals payload.

Plan 01-01 populated taxonomy only (price=null, fundamentals=[]). Plan
01-02 joined the latest Price row per ticker into this same unchanged
response contract (D-07/D-08). Plan 04 populates the fundamentals array
with every stored filing period per ticker — the full multi-year history
D-09 requires, not just the latest — with per-filing provenance.

Route is a plain sync function, never a coroutine — CLAUDE.md/RESEARCH.md
lock sync FastAPI routes + sync SQLAlchemy; FastAPI runs sync def routes in
a threadpool automatically.
"""
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Fundamental, Price, Ticker

router = APIRouter()


class FundamentalPeriod(BaseModel):
    fiscal_year: int
    fiscal_period: str
    revenue: float | None
    net_income: float | None
    market_cap: float | None
    filed_date: date
    accession_number: str


class PriceSnapshot(BaseModel):
    value: float
    source: str
    as_of: date


class TaxonomyInfo(BaseModel):
    ticker: str
    name: str
    sub_sector: str


class CompanyResponse(BaseModel):
    taxonomy: TaxonomyInfo
    price: PriceSnapshot | None
    fundamentals: list[FundamentalPeriod]


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyResponse]:
    # Latest Price per ticker via a max(as_of)-per-ticker subquery joined
    # back onto Price, rather than one query per ticker — a single
    # bounded round-trip across the full taxonomy, not an N+1 loop. The
    # (ticker, as_of) unique constraint makes max-by-as_of a deterministic
    # single-row selection with no tie-breaking needed.
    latest_as_of = (
        select(Price.ticker, func.max(Price.as_of).label("max_as_of"))
        .group_by(Price.ticker)
        .subquery()
    )

    stmt = (
        select(Ticker, Price)
        .outerjoin(latest_as_of, latest_as_of.c.ticker == Ticker.ticker)
        .outerjoin(
            Price,
            (Price.ticker == latest_as_of.c.ticker) & (Price.as_of == latest_as_of.c.max_as_of),
        )
        .order_by(Ticker.ticker)
    )

    rows = db.execute(stmt).all()

    # Every stored Fundamental row across the whole taxonomy in one query
    # (not one query per ticker) — D-09's full multi-year history, grouped
    # into per-ticker lists in Python. Ordering is pushed into the query
    # itself (ascending by period_end, filed_date, accession_number) so
    # entries sharing a fiscal year/period (an original and its
    # restatement) come out in a stable, total order across repeated
    # requests rather than relying on the database's unspecified default
    # row order.
    fundamentals_stmt = select(Fundamental).order_by(
        Fundamental.period_end, Fundamental.filed_date, Fundamental.accession_number
    )
    fundamentals_by_ticker: dict[str, list[Fundamental]] = defaultdict(list)
    for f in db.scalars(fundamentals_stmt).all():
        fundamentals_by_ticker[f.ticker].append(f)

    return [
        CompanyResponse(
            taxonomy=TaxonomyInfo(ticker=t.ticker, name=t.name, sub_sector=t.sub_sector),
            price=(
                PriceSnapshot(value=float(p.close), source=p.source, as_of=p.as_of)
                if p is not None
                else None
            ),
            fundamentals=[
                FundamentalPeriod(
                    fiscal_year=f.fiscal_year,
                    fiscal_period=f.fiscal_period,
                    revenue=float(f.revenue) if f.revenue is not None else None,
                    net_income=float(f.net_income) if f.net_income is not None else None,
                    market_cap=float(f.market_cap) if f.market_cap is not None else None,
                    filed_date=f.filed_date,
                    accession_number=f.accession_number,
                )
                for f in fundamentals_by_ticker.get(t.ticker, [])
            ],
        )
        for t, p in rows
    ]
