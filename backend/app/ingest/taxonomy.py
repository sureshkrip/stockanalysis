"""sectors.yaml loader + validation (TAXO-01) and taxonomy -> tickers sync.

Security note (T-01-01): yaml.safe_load is used exclusively — never
yaml.load / yaml.full_load — since sectors.yaml is an owner-editable file
that could carry arbitrary content. safe_load never constructs arbitrary
Python objects from the YAML stream.
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ticker


class TaxonomyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sub_sector: str


class TaxonomyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies: list[TaxonomyEntry]


def load_taxonomy(path: str | Path) -> TaxonomyConfig:
    """Parse and validate sectors.yaml.

    Raises pydantic.ValidationError naming the offending ticker/field on a
    missing required key or an unrecognized (typo'd) key — TAXO-01's whole
    premise is owner-editable config, so validation errors must be clear.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)
    return TaxonomyConfig.model_validate(raw)


def sync_taxonomy(session: Session, config: TaxonomyConfig) -> None:
    """Upsert each taxonomy entry into the tickers table, keyed on ticker.

    Per D-02a this MUST NOT delete rows for tickers absent from the YAML —
    delisted tickers stay in the taxonomy permanently until a deliberate
    owner edit removes them.
    """
    existing = {t.ticker: t for t in session.scalars(select(Ticker)).all()}

    for entry in config.companies:
        row = existing.get(entry.ticker)
        if row is None:
            session.add(Ticker(ticker=entry.ticker, name=entry.name, sub_sector=entry.sub_sector))
        else:
            if row.name != entry.name:
                row.name = entry.name
            if row.sub_sector != entry.sub_sector:
                row.sub_sector = entry.sub_sector


def _main() -> None:
    """Container-startup entrypoint: sync backend/sectors.yaml into the DB.

    Wave-0-scoped stand-in for the full `app.ingest.refresh` orchestrator
    (prices + fundamentals + failure log) that plans 02-04 build out. Run
    via `python -m app.ingest.taxonomy` from the Dockerfile CMD, after the
    Alembic migration and before uvicorn starts, so `docker compose up
    --build` alone proves TAXO-01's owner-editable YAML end to end.
    """
    from app.db import get_session_factory

    sectors_yaml = Path(__file__).parent.parent.parent / "sectors.yaml"
    config = load_taxonomy(sectors_yaml)

    session_factory = get_session_factory()
    with session_factory() as session:
        sync_taxonomy(session, config)
        session.commit()

    print(f"Synced {len(config.companies)} tickers from {sectors_yaml}")


if __name__ == "__main__":
    _main()
