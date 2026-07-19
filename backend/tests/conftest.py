"""Shared pytest fixtures for the backend test suite."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session(tmp_path):
    """A SQLAlchemy session against a tmp_path-backed SQLite database.

    Creates all tables from Base.metadata, yields a Session, and disposes
    the engine on teardown so each test gets an isolated database.
    """
    from app.models import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


@pytest.fixture
def nvda_facts():
    """Parsed NVDA companyfacts fixture (us-gaap filer)."""
    with open(FIXTURES_DIR / "nvda_companyfacts.json") as f:
        return json.load(f)


@pytest.fixture
def tsm_facts():
    """Parsed TSM companyfacts fixture (ifrs-full filer)."""
    with open(FIXTURES_DIR / "tsm_companyfacts.json") as f:
        return json.load(f)
