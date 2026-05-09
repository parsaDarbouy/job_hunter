"""Tests for listing publication date normalization."""

from __future__ import annotations

from job_hunter.job_listings.board_fetchers import _listing_posted_date_iso


def test_parse_greenhouse_datetime_with_offset() -> None:
    assert _listing_posted_date_iso("2026-04-17T05:58:03-04:00") == "2026-04-17"


def test_parse_ashby_fractional_zulu() -> None:
    assert _listing_posted_date_iso("2026-04-02T21:00:55.755+00:00") == "2026-04-02"


def test_parse_workable_date_only() -> None:
    assert _listing_posted_date_iso("2026-02-12") == "2026-02-12"


def test_parse_empty_returns_empty_string() -> None:
    assert _listing_posted_date_iso("") == ""
    assert _listing_posted_date_iso(None) == ""
