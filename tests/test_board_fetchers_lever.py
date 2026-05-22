"""Tests for Lever board fetcher."""

from __future__ import annotations

from unittest.mock import patch

from job_hunter.job_listings.board_fetchers import _fetch_lever, _listing_posted_date_from_lever_created_at


def test_listing_posted_date_from_lever_created_at_milliseconds() -> None:
    assert _listing_posted_date_from_lever_created_at(1605753685375) == "2020-11-19"


def test_fetch_lever_parses_postings() -> None:
    payload = [
        {
            "text": "Senior SRE/DevOps Engineer",
            "hostedUrl": "https://jobs.lever.co/metabase/abc",
            "createdAt": 1776800480563,
            "categories": {"location": "Global Remote", "allLocations": ["Global Remote"]},
        }
    ]
    source = {"id": "lever_pack__metabase", "kind": "lever", "site_slug": "metabase"}
    with patch(
        "job_hunter.job_listings.board_fetchers.get_json_optional",
        return_value=(payload, None),
    ):
        postings, warning = _fetch_lever(source, "lever_pack__metabase")
    assert warning is None
    assert len(postings) == 1
    assert postings[0].title == "Senior SRE/DevOps Engineer"
    assert postings[0].url == "https://jobs.lever.co/metabase/abc"
    assert postings[0].location == "Global Remote"
    assert postings[0].provider_kind == "lever"
    assert postings[0].listing_posted_date == "2026-04-21"
