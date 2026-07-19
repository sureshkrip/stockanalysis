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

import pytest

from app.ingest.fundamentals import (
    CONCEPT_MAP,
    UnknownTaxonomyError,
    extract_concept,
    extract_fundamentals,
    pick_taxonomy,
)


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


def test_filer_type_branching(nvda_facts, tsm_facts):
    """Both us-gaap (NVDA) and ifrs-full (TSM) filers extract non-empty
    fundamentals with revenue populated on at least one row — the core
    proof that filer-type branching actually works end to end.
    """
    nvda_rows = extract_fundamentals(nvda_facts["facts"], years=50)
    tsm_rows = extract_fundamentals(tsm_facts["facts"], years=50)

    assert len(nvda_rows) > 0
    assert any(r.revenue is not None for r in nvda_rows)
    assert all(r.taxonomy == "us-gaap" for r in nvda_rows)

    assert len(tsm_rows) > 0
    assert any(r.revenue is not None for r in tsm_rows)
    assert all(r.taxonomy == "ifrs-full" for r in tsm_rows)


def test_nvda_extraction_spans_at_least_three_distinct_fiscal_years(nvda_facts):
    rows = extract_fundamentals(nvda_facts["facts"], years=50)
    distinct_years = {r.fiscal_year for r in rows}
    assert len(distinct_years) >= 3


def test_tsm_extraction_never_includes_twd_revenue_values(tsm_facts):
    rows = extract_fundamentals(tsm_facts["facts"], years=50)
    twd_values = {e["val"] for e in tsm_facts["facts"]["ifrs-full"]["Revenue"]["units"]["TWD"]}

    extracted_revenues = {r.revenue for r in rows if r.revenue is not None}
    assert extracted_revenues.isdisjoint(twd_values)


def test_unknown_taxonomy_raises_with_present_key_named():
    facts = {"weird-taxonomy": {}}
    with pytest.raises(UnknownTaxonomyError) as exc_info:
        extract_fundamentals(facts, years=5)
    assert "weird-taxonomy" in str(exc_info.value)


# --- extract_fundamentals: provenance, ordering, boundary ---------------


def test_every_factrow_has_truthy_provenance(nvda_facts, tsm_facts):
    for facts in (nvda_facts["facts"], tsm_facts["facts"]):
        rows = extract_fundamentals(facts, years=50)
        assert len(rows) > 0
        for row in rows:
            assert row.accession_number
            assert row.filed_date
            assert row.fiscal_year
            assert row.fiscal_period
            assert row.form


def test_ordering_is_stable_across_repeated_calls(nvda_facts):
    rows1 = extract_fundamentals(nvda_facts["facts"], years=50)
    rows2 = extract_fundamentals(nvda_facts["facts"], years=50)
    assert rows1 == rows2


def test_results_sorted_ascending_by_period_end_then_filed_then_accn(nvda_facts):
    rows = extract_fundamentals(nvda_facts["facts"], years=50)
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


def test_boundary_closed_at_cutoff_inclusive_day_before_excluded():
    cutoff = date.today().replace(year=date.today().year - 5)
    facts = _synthetic_facts_with_two_periods(cutoff)

    rows = extract_fundamentals(facts, years=5)

    included_periods = {r.period_end for r in rows}
    assert cutoff in included_periods
    assert (cutoff - timedelta(days=1)) not in included_periods


# --- CONCEPT_MAP sanity (both taxonomies present) ------------------------


def test_concept_map_has_both_taxonomies():
    assert "us-gaap" in CONCEPT_MAP
    assert "ifrs-full" in CONCEPT_MAP
    assert CONCEPT_MAP["ifrs-full"]["revenue"] == ["Revenue"]
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in CONCEPT_MAP["us-gaap"]["revenue"]
