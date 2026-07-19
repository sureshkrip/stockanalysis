"""Phase 1 Wave 0 end-to-end test: sectors.yaml -> DB -> GET /companies.

This test is intentionally written before app.main / app.ingest.taxonomy
exist (RED state). Task 2 makes it pass (GREEN state).
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

SECTORS_YAML = Path(__file__).parent.parent / "sectors.yaml"


def test_companies_returns_full_taxonomy(tmp_path, monkeypatch):
    db_path = tmp_path / "e2e.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EDGAR_USER_AGENT", "DataCenterStocks sureshkrip@gmail.com")

    from app.config import get_settings

    get_settings.cache_clear()

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
