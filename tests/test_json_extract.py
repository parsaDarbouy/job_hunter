"""Tests for JSON extraction from LLM responses."""

from __future__ import annotations

import json

import pytest

from job_hunter.json_extract import extract_json_object


def test_extract_json_object_ignores_trailing_text() -> None:
    payload = {
        "company_name": "Acme",
        "position_title": "SRE",
        "files": {"sections/experience.tex": r"\item \textbf{AWS} work"},
    }
    text = json.dumps(payload) + "\n\nHope this helps!"
    parsed = extract_json_object(text)
    assert parsed["company_name"] == "Acme"


def test_extract_json_object_from_markdown_fence() -> None:
    text = '```json\n{"alignment_percentage": 88, "reason": "good fit"}\n```'
    parsed = extract_json_object(text)
    assert parsed["alignment_percentage"] == 88


def test_extract_json_object_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="No JSON object"):
        extract_json_object("not json at all")
