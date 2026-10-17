"""Unit tests for the meetings-list filter helpers.

Covers the date-range query parser added for `GET /meetings` (participant +
date_from/date_to filtering). The participant/date WHERE clauses are exercised
end-to-end against the dev DB during manual QA; here we lock down the pure
date-parsing behaviour that decides whether a bound is applied at all.
"""

from datetime import date

from api.v1.meetings import _parse_date_query


def test_parses_valid_iso_date():
    assert _parse_date_query("2026-01-15") == date(2026, 1, 15)


def test_tolerates_surrounding_whitespace():
    assert _parse_date_query("  2026-12-31  ") == date(2026, 12, 31)


def test_missing_value_is_none():
    assert _parse_date_query(None) is None
    assert _parse_date_query("") is None
    assert _parse_date_query("   ") is None


def test_invalid_values_are_ignored():
    # Garbage, wrong format, and out-of-range dates all return None (filter skipped).
    for bad in ("notadate", "2026/01/15", "15-01-2026", "2026-13-01", "2026-02-30"):
        assert _parse_date_query(bad) is None
