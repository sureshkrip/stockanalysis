"""GET /companies — D-08 nested taxonomy + price + fundamentals payload.

This plan (01-01) populates taxonomy only; price=null and fundamentals=[]
for every company. Plans 02/04 populate those fields against this same
unchanged response contract (D-07).

Route is a plain sync function, never a coroutine — CLAUDE.md/RESEARCH.md
lock sync FastAPI routes + sync SQLAlchemy; FastAPI runs sync def routes in
a threadpool automatically.
"""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Ticker

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
    tickers = db.scalars(select(Ticker).order_by(Ticker.ticker)).all()
    return [
        CompanyResponse(
            taxonomy=TaxonomyInfo(ticker=t.ticker, name=t.name, sub_sector=t.sub_sector),
            price=None,
            fundamentals=[],
        )
        for t in tickers
    ]
