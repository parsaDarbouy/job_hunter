"""Tests for deterministic text cleanup."""

from __future__ import annotations

from job_hunter.resume_ingest.text_cleaner import clean_resume_text


def test_clean_resume_text_collapses_whitespace() -> None:
    raw = "Hello  \n\n\n\nworld\r\n\t\tfoo"
    assert clean_resume_text(raw) == "Hello\n\nworld\nfoo"
