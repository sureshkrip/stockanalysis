"""Tests for app.ingest.fundamentals — INGEST-02's filer-type branching
(the phase's highest-risk logic) and multi-year extraction.

Behavioral coverage against live-recorded fixtures for one filer of each
type: NVDA (us-gaap, domestic 10-K) and TSM (ifrs-full, foreign private
issuer 20-F). Also covers ASML/ARM/GDS/NBIS's shared code path (they all
branch the same way as TSM — ifrs-full — so TSM's fixture exercises that
whole branch).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ingest.fundamentals import (
    CONCEPT_MAP,
    UnknownTaxonomyError,
    compute_market_cap,
    extract_concept,
    extract_fundamentals,
    find_nearest_close,
    pick_taxonomy,
)
from app.models import Price


# --- pick_taxonomy -----------------------------------------------------


def test_pick_taxonomy_nvda_returns_us_gaap(nvda_facts):
    assert pick_taxonomy(nvda_facts["facts"]) == "us-gaap"


def test_pick_taxonomy_tsm_returns_ifrs_full(tsm_facts):
    assert pick_taxonomy(tsm_facts["facts"]) == "ifrs-full"


def test_pick_taxonomy_neither_present_raises_naming_present_keys():
    facts = {"dei": {"EntityCommonStockSharesOutstanding": {}}, "some-other-taxonomy": {}}

    with pytest.raises(UnknownTaxonomyError) as exc_info:
        pick_taxonomy(facts)

    assert "some-other-taxonomy" in str(exc_info.value)


# --- extract_concept -----------------------------------------------------


def test_extract_concept_tsm_revenue_returns_only_usd_never_twd(tsm_facts):
    entries = extract_concept(tsm_facts["facts"], "ifrs-full", "revenue", unit="USD")

    assert len(entries) > 0
    twd_entries = tsm_facts["facts"]["ifrs-full"]["Revenue"]["units"]["TWD"]
    twd_values = {e["val"] for e in twd_entries}
    for entry in entries:
        assert entry["val"] not in twd_values or entry["val"] in {
            e["val"] for e in tsm_facts["facts"]["ifrs-full"]["Revenue"]["units"]["USD"]
        }
    # Explicit: the raw USD unit list is exactly what's returned.
    assert entries == tsm_facts["facts"]["ifrs-full"]["Revenue"]["units"]["USD"]


def test_extract_concept_absent_field_returns_empty_list(nvda_facts):
    entries = extract_concept(nvda_facts["facts"], "us-gaap", "shares_outstanding", unit="shares")
    # NVDA fixture has no CommonStockSharesOutstanding us-gaap concept
    # (dei is used instead) — the candidate list is present but the
    # concept itself is absent from this response.
    assert entries == []


def test_extract_concept_first_present_candidate_name_wins():
    facts = {
        "us-gaap": {
            "Revenues": {
                "units": {"USD": [{"val": 100, "fy": 2020, "fp": "FY", "accn": "a", "filed": "2020-01-01", "end": "2019-12-31", "form": "10-K"}]}
            }
        }
    }
    # RevenueFromContractWithCustomerExcludingAssessedTax (1st candidate) is
    # absent; Revenues (2nd candidate) is present and must win.
    entries = extract_concept(facts, "us-gaap", "revenue", unit="USD")
    assert len(entries) == 1
    assert entries[0]["val"] == 100


# --- extract_fundamentals: filer-type branching ------------------------


def test_filer_type_branching(nvda_facts, tsm_facts, db_session):
    """Both us-gaap (NVDA) and ifrs-full (TSM) filers extract non-empty
    fundamentals with revenue populated on at least one row — the core
    proof that filer-type branching actually works end to end.
    """
    nvda_rows = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)
    tsm_rows = extract_fundamentals(tsm_facts["facts"], db_session, "TSM", years=50)

    assert len(nvda_rows) > 0
    assert any(r.revenue is not None for r in nvda_rows)
    assert all(r.taxonomy == "us-gaap" for r in nvda_rows)

    assert len(tsm_rows) > 0
    assert any(r.revenue is not None for r in tsm_rows)
    assert all(r.taxonomy == "ifrs-full" for r in tsm_rows)


def test_nvda_extraction_spans_at_least_three_distinct_fiscal_years(nvda_facts, db_session):
    rows = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)
    distinct_years = {r.fiscal_year for r in rows}
    assert len(distinct_years) >= 3


def test_tsm_extraction_never_includes_twd_revenue_values(tsm_facts, db_session):
    rows = extract_fundamentals(tsm_facts["facts"], db_session, "TSM", years=50)
    twd_values = {e["val"] for e in tsm_facts["facts"]["ifrs-full"]["Revenue"]["units"]["TWD"]}

    extracted_revenues = {r.revenue for r in rows if r.revenue is not None}
    assert extracted_revenues.isdisjoint(twd_values)


def test_unknown_taxonomy_raises_with_present_key_named(db_session):
    facts = {"weird-taxonomy": {}}
    with pytest.raises(UnknownTaxonomyError) as exc_info:
        extract_fundamentals(facts, db_session, "TEST", years=5)
    assert "weird-taxonomy" in str(exc_info.value)


# --- extract_fundamentals: provenance, ordering, boundary ---------------


def test_every_factrow_has_truthy_provenance(nvda_facts, tsm_facts, db_session):
    for facts, ticker in ((nvda_facts["facts"], "NVDA"), (tsm_facts["facts"], "TSM")):
        rows = extract_fundamentals(facts, db_session, ticker, years=50)
        assert len(rows) > 0
        for row in rows:
            assert row.accession_number
            assert row.filed_date
            assert row.fiscal_year
            assert row.fiscal_period
            assert row.form


def test_ordering_is_stable_across_repeated_calls(nvda_facts, db_session):
    rows1 = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)
    rows2 = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)
    assert rows1 == rows2


def test_results_sorted_ascending_by_period_end_then_filed_then_accn(nvda_facts, db_session):
    rows = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)
    keys = [(r.period_end, r.filed_date, r.accession_number) for r in rows]
    assert keys == sorted(keys)


def _synthetic_facts_with_two_periods(cutoff: date) -> dict:
    """Build a minimal us-gaap facts dict with one filing exactly at the
    history cutoff and one filing exactly one day before it.
    """
    included_end = cutoff.isoformat()
    excluded_end = (cutoff - timedelta(days=1)).isoformat()

    def _entry(end: str, accn: str, val: int) -> dict:
        return {
            "start": "2000-01-01",
            "end": end,
            "val": val,
            "accn": accn,
            "fy": 2000,
            "fp": "FY",
            "form": "10-K",
            "filed": end,
        }

    return {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        _entry(included_end, "0000000000-00-000001", 111),
                        _entry(excluded_end, "0000000000-00-000002", 222),
                    ]
                }
            },
            "NetIncomeLoss": {"units": {"USD": []}},
        }
    }


def test_boundary_closed_at_cutoff_inclusive_day_before_excluded(db_session):
    cutoff = date.today().replace(year=date.today().year - 5)
    facts = _synthetic_facts_with_two_periods(cutoff)

    rows = extract_fundamentals(facts, db_session, "TEST", years=5)

    included_periods = {r.period_end for r in rows}
    assert cutoff in included_periods
    assert (cutoff - timedelta(days=1)) not in included_periods


# --- CONCEPT_MAP sanity (both taxonomies present) ------------------------


def test_concept_map_has_both_taxonomies():
    assert "us-gaap" in CONCEPT_MAP
    assert "ifrs-full" in CONCEPT_MAP
    assert CONCEPT_MAP["ifrs-full"]["revenue"] == ["Revenue"]
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in CONCEPT_MAP["us-gaap"]["revenue"]


# --- market-cap derivation (Pattern 3, INGEST-02) -----------------------


def test_find_nearest_close_picks_smaller_absolute_distance(db_session):
    as_of = date(2026, 2, 20)
    db_session.add(Price(ticker="NVDA", close=Decimal("100.00"), as_of=as_of - timedelta(days=2)))
    db_session.add(Price(ticker="NVDA", close=Decimal("150.00"), as_of=as_of + timedelta(days=1)))
    db_session.commit()

    close = find_nearest_close(db_session, "NVDA", as_of)

    assert close == Decimal("150.00")


def test_find_nearest_close_returns_none_with_no_price_rows(db_session):
    assert find_nearest_close(db_session, "NVDA", date(2026, 2, 20)) is None


def test_compute_market_cap_null_not_zero_when_no_price(db_session):
    shares_entry = {"end": "2026-02-20", "val": 24300000000}

    result = compute_market_cap(shares_entry, db_session, "NVDA")

    assert result is None
    assert result != 0


def test_compute_market_cap_is_exact_decimal_no_float_drift(db_session):
    as_of = date(2026, 2, 20)
    db_session.add(Price(ticker="NVDA", close=Decimal("134.83"), as_of=as_of))
    db_session.commit()

    shares_entry = {"end": "2026-02-20", "val": 24300000000}
    result = compute_market_cap(shares_entry, db_session, "NVDA")

    assert isinstance(result, Decimal)
    assert result == Decimal("24300000000") * Decimal("134.83")


def test_extract_fundamentals_populates_market_cap_end_to_end(nvda_facts, db_session):
    # The NVDA fixture's FY2026 10-K carries a shares-outstanding entry
    # as of 2026-02-20 (accn 0001045810-26-000021) — seed a close near
    # that date so the corresponding FactRow gets a non-null market_cap.
    db_session.add(Price(ticker="NVDA", close=Decimal("134.83"), as_of=date(2026, 2, 20)))
    db_session.commit()

    rows = extract_fundamentals(nvda_facts["facts"], db_session, "NVDA", years=50)

    assert any(r.market_cap is not None for r in rows)
    target = next(r for r in rows if r.accession_number == "0001045810-26-000021")
    assert target.market_cap == Decimal("24300000000") * Decimal("134.83")


def test_no_ingest_time_rounding_in_fundamentals_module():
    import inspect

    import app.ingest.fundamentals as mod

    source = inspect.getsource(mod)
    assert "round(" not in "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )


def test_no_entity_public_float_substitution_in_fundamentals_module():
    import inspect

    import app.ingest.fundamentals as mod

    source = inspect.getsource(mod)
    lines = [line for line in source.splitlines() if not line.strip().startswith("#")]
    assert sum(line.count("EntityPublicFloat") for line in lines) == 0
