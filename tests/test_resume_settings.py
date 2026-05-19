"""Tests for resume.yaml CV-generation settings."""

from __future__ import annotations

import pytest

from job_hunter.resume_ingest.resume_settings import (
    parse_about_me_note,
    parse_resume_max_pages,
    parse_target_job_url,
)


def test_parse_resume_max_pages_requires_positive_integer() -> None:
    with pytest.raises(ValueError, match="resume_max_pages"):
        parse_resume_max_pages({})
    with pytest.raises(ValueError, match="resume_max_pages"):
        parse_resume_max_pages({"resume_max_pages": 0})
    assert parse_resume_max_pages({"resume_max_pages": 2}) == 2


def test_parse_about_me_note_returns_stripped_string_or_empty() -> None:
    assert parse_about_me_note({}) == ""
    assert parse_about_me_note({"about_me_note": "  SRE with ownership  "}) == "SRE with ownership"


def test_parse_target_job_url_requires_non_empty() -> None:
    with pytest.raises(ValueError, match="target_job_url"):
        parse_target_job_url({})
    assert parse_target_job_url({"target_job_url": "https://example.com/j/1"}) == (
        "https://example.com/j/1"
    )
