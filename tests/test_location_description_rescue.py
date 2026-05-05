"""Tests for Gemini-assisted geography filtering."""

from __future__ import annotations

from unittest.mock import MagicMock

from job_hunter.job_listings.location_description_rescue import (
    geography_allowed_with_optional_rescue,
    strip_html_to_plain_text,
    summarize_location_constraints_for_prompt,
)
from job_hunter.job_listings.models import JobPosting
from job_hunter.job_listings.position_filters import posting_matches_position


def test_strip_html_to_plain_text_truncates_and_strips_tags() -> None:
    html = "<p>Hello&nbsp;<strong>world</strong></p>" + ("x" * 50_000)
    text = strip_html_to_plain_text(html, maximum_characters=30)
    assert "Hello" in text
    assert "world" in text
    assert "strong" not in text
    assert "[truncated]" in text


def test_summarize_constraints_includes_remote_countries() -> None:
    summary = summarize_location_constraints_for_prompt(
        {
            "countries_onsite_or_hybrid_ok": ["Canada"],
            "remote_work_allowed_from_countries": ["Canada"],
            "globally_remote_acceptable": True,
        },
    )
    assert "Canada" in summary


def test_geography_primary_pass_skips_runner() -> None:
    rescue = MagicMock()
    posting = JobPosting(
        url="https://example.com/1",
        title="Platform Engineer",
        location="Toronto, ON, Canada",
        source_id="s",
        provider_kind="greenhouse",
        description_html="",
    )
    position = {
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
        "titles": {"acceptable": ["Platform"], "not_acceptable": []},
    }
    ok = geography_allowed_with_optional_rescue(posting, position, rescue_runner=rescue)
    assert ok is True
    rescue.eligible_via_description.assert_not_called()


def test_geography_rescue_when_heuristic_fails() -> None:
    rescue = MagicMock()
    rescue.eligible_via_description.return_value = True
    posting = JobPosting(
        url="https://example.com/2",
        title="Platform Engineer",
        location="USA | Remote",
        source_id="s",
        provider_kind="ashby",
        description_html="<p>Open to Canada-based contractors.</p>",
    )
    position = {
        "location_constraints": {
            "countries_onsite_or_hybrid_ok": ["Canada"],
            "remote_work_allowed_from_countries": ["Canada"],
        },
        "titles": {"acceptable": ["Platform"], "not_acceptable": []},
        "acceptable_seniority_levels": [],
        "not_acceptable_seniority_levels": [],
    }
    ok = geography_allowed_with_optional_rescue(posting, position, rescue_runner=rescue)
    assert ok is True
    rescue.eligible_via_description.assert_called_once_with(posting)


def test_posting_matches_position_respects_rescue_mock() -> None:
    rescue = MagicMock()
    rescue.eligible_via_description.return_value = True
    posting = JobPosting(
        url="https://example.com/3",
        title="Senior Platform Engineer",
        location="Germany",
        source_id="s",
        provider_kind="ashby",
        description_html="<p>Full remote worldwide.</p>",
    )
    position = {
        "location_constraints": {"countries_onsite_or_hybrid_ok": ["Canada"]},
        "titles": {"acceptable": ["Platform"], "not_acceptable": []},
        "acceptable_seniority_levels": ["senior"],
        "not_acceptable_seniority_levels": [],
    }
    ok = posting_matches_position(posting, position, location_rescue_runner=rescue)
    assert ok is True
    rescue.eligible_via_description.assert_called_once()
