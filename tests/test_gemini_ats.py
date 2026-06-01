from __future__ import annotations

import pytest

from job_hunter.cv_generate.gemini_ats import parse_ats_report_from_llm_response


def test_parse_ats_report_coerces_and_caps_score() -> None:
    report = parse_ats_report_from_llm_response(
        '{"score": 105.2, "missing_keywords": [], "note": ""}'
    )
    assert report.score == 100

    report = parse_ats_report_from_llm_response(
        '{"score": -10, "missing_keywords": [], "note": ""}'
    )
    assert report.score == 0


def test_parse_ats_report_missing_keywords_dedupes_case_insensitive_and_trims() -> None:
    report = parse_ats_report_from_llm_response(
        '{"score": 50, "missing_keywords": [" Terraform", "terraform", " ", null], "note": "x"}'
    )
    assert report.missing_keywords == ["Terraform"]


def test_parse_ats_report_trims_note_and_hard_caps_length() -> None:
    long_note = "a" * 200
    report = parse_ats_report_from_llm_response(
        f'{{"score": 1, "missing_keywords": [], "note": "{long_note}"}}'
    )
    assert len(report.note) <= 120


def test_parse_ats_report_raises_when_no_json_object_found() -> None:
    with pytest.raises(ValueError, match="No JSON object found"):
        parse_ats_report_from_llm_response("not json at all")

