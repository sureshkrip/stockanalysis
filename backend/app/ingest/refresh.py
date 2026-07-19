"""Refresh orchestrator (STORE-02) — the process Coolify's nightly
scheduled task invokes as `python -m app.ingest.refresh` (docker exec
backend python -m app.ingest.refresh, per RESEARCH.md's Architecture
Patterns section).

Follows RESEARCH.md Pattern 1's per-ticker failure isolation structure:
load+validate the taxonomy and sync it (a taxonomy validation error is a
legitimate hard failure and is allowed to propagate — this is the one
exception to the never-abort rule) -> iterate tickers, wrapping each
price fetch+write in its own try/except that records a TickerFailure and
continues -> commit per ticker so an interrupted run leaves every
already-processed ticker durably persisted -> always write one
RefreshLog row, including a fully clean run.

Per D-02a, a ticker is never removed from sectors.yaml or the tickers
table by this pipeline, regardless of failure — the per-run failure log
is the safety net between the owner's manual taxonomy reviews.
"""
from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingest.cik_resolver import resolve_cik
from app.ingest.edgar_client import get_companyfacts
from app.ingest.fundamentals import extract_fundamentals, write_fundamentals
from app.ingest.prices import fetch_price, write_price
from app.ingest.taxonomy import load_taxonomy, sync_taxonomy
from app.models import RefreshLog

logger = logging.getLogger(__name__)


@dataclass
class TickerFailure:
    ticker: str
    stage: str
    error: str


@dataclass
class RefreshResult:
    run_id: str
    tickers_attempted: int
    failures: list[TickerFailure] = field(default_factory=list)

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    @property
    def succeeded_count(self) -> int:
        return self.tickers_attempted - self.failure_count


def record_failure(
    failures: list[TickerFailure], ticker: str, stage: str, exc: Exception
) -> None:
    """Append a TickerFailure. Never deduplicates or merges — two
    different tickers failing at the same stage are two independent
    facts the owner needs to see; collapsing them would hide the scale
    of a systemic outage.
    """
    failure = TickerFailure(ticker=ticker, stage=stage, error=str(exc))
    failures.append(failure)
    logger.warning(
        "ticker refresh failed: ticker=%s stage=%s error=%s", ticker, stage, str(exc)
    )


def persist_refresh_log(
    session: Session,
    run_id: str,
    started_at: datetime,
    failures: list[TickerFailure],
    attempted: int,
) -> None:
    """Write one RefreshLog row. Called on every run, including a fully
    clean one, so the owner can distinguish 'ran clean' from 'never ran'.
    """
    session.add(
        RefreshLog(
            run_id=run_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            tickers_attempted=attempted,
            failure_count=len(failures),
            failures=[
                {"ticker": f.ticker, "stage": f.stage, "error": f.error} for f in failures
            ],
        )
    )
    session.commit()


def run_refresh(session: Session, taxonomy_path: str | Path) -> RefreshResult:
    """Run one price-refresh pass over the full taxonomy.

    A taxonomy validation error propagates unhandled — see module
    docstring. Every per-ticker price fetch/write failure below is
    isolated: under no circumstance may it propagate out of the loop.
    """
    config = load_taxonomy(taxonomy_path)
    sync_taxonomy(session, config)
    session.commit()

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    tickers = [entry.ticker for entry in config.companies]
    failures: list[TickerFailure] = []

    for ticker in tickers:
        # Price and fundamentals are two independent stages inside the
        # same per-ticker pass (never a second loop over tickers, which
        # would double wall-clock time and split the failure log across
        # two conceptual runs). Neither stage's try/except may swallow
        # the other's outcome: a flaky price provider must not prevent a
        # fundamentals attempt, and vice versa.
        try:
            row = fetch_price(ticker)
            write_price(session, row)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - per-ticker isolation is intentional
            session.rollback()
            record_failure(failures, ticker, "price", exc)

        try:
            cik = resolve_cik(session, ticker)
            # Commit immediately so a newly-resolved CIK is durably
            # cached even if the fundamentals fetch below fails — the
            # cache row must not be rolled back by an unrelated
            # downstream failure.
            session.commit()
        except Exception as exc:  # noqa: BLE001 - per-ticker isolation is intentional
            session.rollback()
            record_failure(failures, ticker, "cik", exc)
            continue

        try:
            facts = get_companyfacts(cik)
            fact_rows = extract_fundamentals(facts["facts"], session, ticker)
            write_fundamentals(session, ticker, fact_rows)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - per-ticker isolation is intentional
            session.rollback()
            record_failure(failures, ticker, "fundamentals", exc)
            continue

    persist_refresh_log(session, run_id, started_at, failures, len(tickers))

    return RefreshResult(run_id=run_id, tickers_attempted=len(tickers), failures=failures)


def _default_taxonomy_path() -> Path:
    return Path(__file__).parent.parent.parent / "sectors.yaml"


def _main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: `python -m app.ingest.refresh [taxonomy_path]`.

    Exits 0 whenever the run completed — even with per-ticker failures
    present, since those are expected steady-state noise for Coolify's
    scheduled-task alerting, not an alertable condition. A non-zero exit
    is reserved for a genuine orchestration failure (invalid taxonomy,
    unreachable database) that propagates out of run_refresh.
    """
    logging.basicConfig(level=logging.INFO)

    from app.db import get_session_factory

    argv = sys.argv[1:] if argv is None else argv
    taxonomy_path = Path(argv[0]) if argv else _default_taxonomy_path()

    session_factory = get_session_factory()
    with session_factory() as session:
        result = run_refresh(session, taxonomy_path)

    print(
        f"Refresh run {result.run_id}: attempted={result.tickers_attempted} "
        f"succeeded={result.succeeded_count} failed={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
