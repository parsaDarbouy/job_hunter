"""Unit tests for ``position_filters``."""

from __future__ import annotations

from job_hunter.job_listings.models import JobPosting
from job_hunter.job_listings.position_filters import (
    infer_seniority_from_title,
    posting_matches_position,
    posting_title_allowed,
)


def _posting(*, title: str, location: str) -> JobPosting:
    return JobPosting(
        url="https://example.com/job/1",
        title=title,
        location=location,
        source_id="src",
        provider_kind="greenhouse",
    )


def test_not_acceptable_title_rejects() -> None:
    position = {"titles": {"acceptable": ["Engineer"], "not_acceptable": ["Sales"]}}
    posting = _posting(title="Sales Engineer", location="Canada")
    assert posting_title_allowed(posting, position) is False
    assert posting_matches_position(posting, position) is False


def test_acceptable_title_requires_substring_when_list_nonempty() -> None:
    position = {"titles": {"acceptable": ["DevOps"], "not_acceptable": []}}
    ok = _posting(title="Senior DevOps Engineer", location="Canada")
    bad = _posting(title="Account Executive", location="Canada")
    assert posting_title_allowed(ok, position) is True
    assert posting_title_allowed(bad, position) is False


def test_location_requires_configured_country() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
    }
    toronto = _posting(title="Software Engineer", location="Toronto, ON, Canada")
    austin = _posting(title="Software Engineer", location="Austin, TX, USA")
    assert posting_matches_position(toronto, position) is True
    assert posting_matches_position(austin, position) is False


def test_location_skipped_when_no_geography_rules() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "location_constraints": {"notes": "only notes, no geography keys"},
    }
    anywhere = _posting(title="Software Engineer", location="Moon Base")
    assert posting_matches_position(anywhere, position) is True


def test_globally_remote_worldwide_phrase() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "location_constraints": {"globally_remote_acceptable": True},
    }
    posting = _posting(title="Software Engineer", location="Remote — worldwide")
    assert posting_matches_position(posting, position) is True


def test_infer_seniority_prefers_higher_band() -> None:
    assert infer_seniority_from_title("Senior Staff Engineer") == "staff"
    assert infer_seniority_from_title("Senior Director of Engineering") == "director"


def test_seniority_allowlist_filters_staff() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "acceptable_seniority_levels": ["junior", "mid_level", "senior"],
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
    }
    staff = _posting(title="Staff Site Reliability Engineer", location="Toronto, ON, Canada")
    senior = _posting(title="Senior Site Reliability Engineer", location="Toronto, ON, Canada")
    assert posting_matches_position(staff, position) is False
    assert posting_matches_position(senior, position) is True


def test_seniority_blocklist_rejects_intern() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "not_acceptable_seniority_levels": ["intern"],
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
    }
    intern = _posting(title="Software Engineer Intern", location="Toronto, ON, Canada")
    mid = _posting(title="Software Engineer", location="Toronto, ON, Canada")
    assert posting_matches_position(intern, position) is False
    assert posting_matches_position(mid, position) is True


def test_seniority_not_applied_when_lists_empty() -> None:
    position = {
        "titles": {"acceptable": ["Engineer"], "not_acceptable": []},
        "acceptable_seniority_levels": [],
        "not_acceptable_seniority_levels": [],
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
    }
    staff = _posting(title="Staff Engineer", location="Toronto, ON, Canada")
    assert posting_matches_position(staff, position) is True
