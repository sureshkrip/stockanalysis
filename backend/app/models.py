"""SQLAlchemy 2.0 typed models (Mapped[] / mapped_column idiom exclusively).

Kept deliberately separate from the Pydantic API response schemas in
app/api/companies.py — the point-in-time provenance columns here
(accession_number, filed_date) should not be forced into every response
shape (see RESEARCH.md Alternatives Considered re: SQLModel).
"""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String)
    sub_sector: Mapped[str] = mapped_column(String, index=True)


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of", name="uq_price_ticker_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    close: Mapped[float] = mapped_column(Numeric)
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String, default="yfinance")


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "fiscal_year", "fiscal_period", "accession_number",
            name="uq_fundamental_period_filing",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    fiscal_year: Mapped[int]
    fiscal_period: Mapped[str]  # "FY", "Q1".."Q3" — EDGAR's "fp" field
    form: Mapped[str]  # "10-K", "10-Q", "20-F"
    accession_number: Mapped[str]  # EDGAR "accn" — provenance
    filed_date: Mapped[date] = mapped_column(Date)  # EDGAR "filed" — provenance
    period_end: Mapped[date] = mapped_column(Date)  # EDGAR "end"
    revenue: Mapped[float | None] = mapped_column(Numeric)
    net_income: Mapped[float | None] = mapped_column(Numeric)
    market_cap: Mapped[float | None] = mapped_column(Numeric)  # derived, see Pattern 3
    source: Mapped[str] = mapped_column(String, default="SEC EDGAR")
    taxonomy: Mapped[str]  # "us-gaap" | "ifrs-full" — audit trail


class TickerCik(Base):
    __tablename__ = "ticker_ciks"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    cik: Mapped[str] = mapped_column(String(10))
    resolved_at: Mapped[datetime] = mapped_column(DateTime)


class RefreshLog(Base):
    __tablename__ = "refresh_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tickers_attempted: Mapped[int]
    failure_count: Mapped[int]
    failures: Mapped[dict | None] = mapped_column(JSON, nullable=True)
