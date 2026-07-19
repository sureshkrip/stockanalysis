"""Tests for TAXO-01: sectors.yaml loading, validation, and sync."""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select

SECTORS_YAML = Path(__file__).parent.parent / "sectors.yaml"


def test_load_sectors_yaml():
    from app.ingest.taxonomy import load_taxonomy

    config = load_taxonomy(SECTORS_YAML)

    assert len(config.companies) == 54
    assert len({c.sub_sector for c in config.companies}) == 10


def test_load_taxonomy_missing_required_field_raises(tmp_path):
    from app.ingest.taxonomy import load_taxonomy

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        "companies:\n  - ticker: NVDA\n    sub_sector: ai_chips\n"  # missing name
    )

    with pytest.raises(ValidationError) as exc_info:
        load_taxonomy(bad_yaml)

    assert "name" in str(exc_info.value)


def test_load_taxonomy_unrecognized_field_raises(tmp_path):
    from app.ingest.taxonomy import load_taxonomy

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        "companies:\n"
        "  - ticker: NVDA\n"
        "    name: NVIDIA\n"
        "    sub_sector: ai_chips\n"
        "    notes: extra field not allowed\n"
    )

    with pytest.raises(ValidationError):
        load_taxonomy(bad_yaml)


def test_sync_taxonomy_is_idempotent(db_session):
    from app.ingest.taxonomy import load_taxonomy, sync_taxonomy
    from app.models import Ticker

    config = load_taxonomy(SECTORS_YAML)

    sync_taxonomy(db_session, config)
    db_session.commit()
    count_after_first = len(db_session.scalars(select(Ticker)).all())

    sync_taxonomy(db_session, config)
    db_session.commit()
    count_after_second = len(db_session.scalars(select(Ticker)).all())

    assert count_after_first == 54
    assert count_after_second == 54


def test_sync_taxonomy_updates_changed_sub_sector_without_deleting_others(db_session):
    from app.ingest.taxonomy import TaxonomyConfig, TaxonomyEntry, sync_taxonomy
    from app.models import Ticker

    config = TaxonomyConfig(
        companies=[
            TaxonomyEntry(ticker="NVDA", name="NVIDIA", sub_sector="ai_chips"),
            TaxonomyEntry(ticker="TSM", name="Taiwan Semiconductor", sub_sector="semi_equipment"),
        ]
    )
    sync_taxonomy(db_session, config)
    db_session.commit()

    updated_config = TaxonomyConfig(
        companies=[
            TaxonomyEntry(ticker="NVDA", name="NVIDIA", sub_sector="emerging_watchlist"),
            TaxonomyEntry(ticker="TSM", name="Taiwan Semiconductor", sub_sector="semi_equipment"),
        ]
    )
    sync_taxonomy(db_session, updated_config)
    db_session.commit()

    rows = {t.ticker: t for t in db_session.scalars(select(Ticker)).all()}
    assert len(rows) == 2
    assert rows["NVDA"].sub_sector == "emerging_watchlist"
    assert rows["TSM"].sub_sector == "semi_equipment"
