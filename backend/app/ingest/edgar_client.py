"""Shared SEC EDGAR httpx client — headers, timeout, pacing, and retry.

RESEARCH.md's Pitfall 3 verified empirically that a request carrying a
generic library User-Agent gets a 403 from SEC, and SEC may IP-block the
source for roughly ten minutes. That failure mode takes down every
remaining ticker in the run, not just one — which is exactly why this is
a single shared, centrally-configured client (T-01-10) rather than a
per-call header that one code path can forget.

Note the two EDGAR hosts differ: `company_tickers.json` is served from
`https://www.sec.gov/files/`, while the XBRL APIs (companyfacts) live on
`https://data.sec.gov/`. This client is not bound to a `base_url` for
that reason — callers pass full URLs.
"""
from __future__ import annotations

import time
from functools import lru_cache

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import get_settings

# Deliberately conservative against SEC's published 10 req/sec floor
# (0.1s) — a simple monotonic-clock guard between outbound calls (T-01-11)
# is sufficient at this project's single-process scale.
EDGAR_MIN_REQUEST_INTERVAL = 0.15

_last_request_monotonic: float | None = None


def _pace_request() -> None:
    """Block until at least EDGAR_MIN_REQUEST_INTERVAL has elapsed since
    the previous outbound EDGAR request.
    """
    global _last_request_monotonic
    now = time.monotonic()
    if _last_request_monotonic is not None:
        elapsed = now - _last_request_monotonic
        remaining = EDGAR_MIN_REQUEST_INTERVAL - elapsed
        if remaining > 0:
            time.sleep(remaining)
    _last_request_monotonic = time.monotonic()


@lru_cache
def get_edgar_client() -> httpx.Client:
    """A single shared httpx.Client for every outbound EDGAR request.

    Configured with an explicit connect+read timeout (T-01-12) and a
    User-Agent sourced from settings (T-01-10) — never hardcoded, so a
    real contact address always reaches SEC per their published API
    policy, and the value can be swapped per-environment without a code
    change.
    """
    settings = get_settings()
    return httpx.Client(
        headers={"User-Agent": settings.edgar_user_agent},
        timeout=httpx.Timeout(10.0, connect=5.0),
    )


def _is_retryable_error(exc: BaseException) -> bool:
    """Retry on transport errors and 5xx/429 responses only.

    A 404 (missing CIK/company) is a permanent per-ticker condition —
    retrying it three times wastes rate-limit budget that other tickers
    need, so it must NOT be retried.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return False


@retry(
    retry=retry_if_exception(_is_retryable_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    reraise=True,
)
def edgar_get(url: str) -> httpx.Response:
    """GET a full URL through the shared, paced, retried EDGAR client.

    Raises for any non-2xx status via raise_for_status(), so callers
    always receive either a healthy Response or an exception.
    """
    _pace_request()
    client = get_edgar_client()
    response = client.get(url)
    response.raise_for_status()
    return response


def get_companyfacts(cik: str) -> dict:
    """Fetch the full companyfacts payload for a zero-padded CIK.

    Issued against the data.sec.gov XBRL host (distinct from the
    www.sec.gov host used for company_tickers.json).
    """
    response = edgar_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    return response.json()
