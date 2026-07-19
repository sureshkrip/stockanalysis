"""Tests for app.ingest.cik_resolver and app.ingest.edgar_client — the CIK
resolution/caching path and the shared EDGAR HTTP client's headers,
timeout, pacing, and retry behavior (INGEST-02 groundwork).

All HTTP is mocked via respx (it mocks the httpx transport specifically,
matching this hand-rolled client) — no test here makes a live network
request.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.ingest import cik_resolver, edgar_client
from app.ingest.cik_resolver import CikNotFoundError, resolve_cik
from app.models import TickerCik

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

SAMPLE_MAPPING = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


@pytest.fixture(autouse=True)
def _reset_caches():
    """Clear the lru_cache'd mapping/client between tests so one test's
    mocked response never leaks into the next.
    """
    cik_resolver._build_ticker_to_cik_map.cache_clear()
    edgar_client.get_edgar_client.cache_clear()
    edgar_client._last_request_monotonic = None
    yield
    cik_resolver._build_ticker_to_cik_map.cache_clear()
    edgar_client.get_edgar_client.cache_clear()


# --- CIK resolution --------------------------------------------------


def test_resolve_cik_cache_hit_makes_zero_network_calls(db_session):
    db_session.add(
        TickerCik(ticker="NVDA", cik="0001045810", resolved_at=datetime.now(timezone.utc))
    )
    db_session.commit()

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(COMPANY_TICKERS_URL)
        result = resolve_cik(db_session, "NVDA")

    assert result == "0001045810"
    assert route.call_count == 0


def test_resolve_cik_cache_miss_fetches_and_persists(db_session):
    with respx.mock:
        respx.get(COMPANY_TICKERS_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_MAPPING)
        )
        result = resolve_cik(db_session, "NVDA")

    assert result == "0001045810"

    cached = db_session.query(TickerCik).filter_by(ticker="NVDA").one_or_none()
    assert cached is not None
    assert cached.cik == "0001045810"


def test_resolve_cik_second_call_after_miss_issues_no_further_http(db_session):
    with respx.mock:
        route = respx.get(COMPANY_TICKERS_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_MAPPING)
        )
        resolve_cik(db_session, "NVDA")
        assert route.call_count == 1

        # Second call for the same ticker: the ticker_ciks row now exists,
        # so this must be a cache hit with no further HTTP call.
        resolve_cik(db_session, "NVDA")
        assert route.call_count == 1


def test_resolve_cik_apple_zero_pads_to_ten_digits(db_session):
    with respx.mock:
        respx.get(COMPANY_TICKERS_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_MAPPING)
        )
        result = resolve_cik(db_session, "AAPL")

    assert result == "0000320193"
    assert len(result) == 10


def test_resolve_cik_missing_ticker_raises_cik_not_found(db_session):
    with respx.mock:
        respx.get(COMPANY_TICKERS_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_MAPPING)
        )
        with pytest.raises(CikNotFoundError):
            resolve_cik(db_session, "CBRS")


def test_resolve_cik_cold_start_issues_one_mapping_request_for_many_tickers(db_session):
    """A cold run resolving multiple tickers should hit the network once,
    not once per ticker — the in-run mapping cache is what makes this true.
    """
    with respx.mock:
        route = respx.get(COMPANY_TICKERS_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_MAPPING)
        )
        resolve_cik(db_session, "NVDA")
        resolve_cik(db_session, "AAPL")

    assert route.call_count == 1


# --- EDGAR client: headers, timeout, retry, pacing --------------------


def test_edgar_client_sends_user_agent_from_settings():
    client = edgar_client.get_edgar_client()
    from app.config import get_settings

    assert client.headers["user-agent"] == get_settings().edgar_user_agent


def test_edgar_client_has_explicit_connect_and_read_timeout():
    client = edgar_client.get_edgar_client()
    assert client.timeout.connect == 5.0
    assert client.timeout.read == 10.0


def test_edgar_get_retries_5xx_then_succeeds():
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json"
    with respx.mock:
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        response = edgar_client.edgar_get(url)

    assert response.status_code == 200
    assert route.call_count == 2


def test_edgar_get_404_is_not_retried():
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK9999999999.json"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            edgar_client.edgar_get(url)

    assert route.call_count == 1


def test_edgar_get_exhausts_retry_budget_bounded_at_3():
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            edgar_client.edgar_get(url)

    assert route.call_count == 3
