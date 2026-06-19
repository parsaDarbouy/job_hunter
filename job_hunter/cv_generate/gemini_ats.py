"""Antigravity CLI / legacy Gemini CLI ATS-style scoring for resume YAML vs job description text."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from job_hunter.agent_cli import DEFAULT_AGENT_BINARY, run_agent_cli_headless
from job_hunter.json_extract import extract_json_object

_logger = logging.getLogger(__name__)

_ATS_PROMPT = """You are an ATS (Applicant Tracking System) evaluator.

Task: compare the candidate resume YAML to the job description text and output a short ATS-style match report.

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Do NOT praise or use marketing language.
- Do NOT fabricate facts.
- Determine missing keywords/requirements by looking for job-relevant hard skills/technologies/competencies in the resume YAML.
- score must be an integer from 0 to 100 (higher = more keywords present).
- missing_keywords must be an array of short strings (cap at 12). Only include keywords that seem required by the job description but are missing from the resume YAML.
- note must be a single very short sentence (<= 120 chars) describing the biggest gap causing missing_keywords.

JSON shape:
{
  "score": 0,
  "missing_keywords": ["", ""],
  "note": ""
}

The input JSON follows on stdin after a single line containing only: ---CV-ATS-INPUT---"""


@dataclass(frozen=True)
class GeminiAtsReport:
    """ATS-style comparison report."""

    score: int
    missing_keywords: list[str]
    note: str


def _coerce_int_0_100(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 0
    return max(0, min(100, number))


def _dedupe_case_insensitive_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(item)
    return output


def _coerce_missing_keywords(value: Any, *, cap: int = 12) -> list[str]:
    keywords: list[str] = []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        keywords.append(text)
    keywords = _dedupe_case_insensitive_preserve_order(keywords)
    return keywords[:cap]


def _coerce_note(value: Any) -> str:
    note = str(value or "").strip()
    # ATS "note" should be terse; keep it hard-capped defensively.
    if len(note) > 120:
        note = note[:120].rstrip()
    return note


def parse_ats_report_from_llm_response(response_text: str) -> GeminiAtsReport:
    """Parse a strict JSON ATS report from Gemini response text."""
    parsed = extract_json_object(response_text)
    score = _coerce_int_0_100(parsed.get("score"))
    missing_keywords = _coerce_missing_keywords(parsed.get("missing_keywords"))
    note = _coerce_note(parsed.get("note"))
    return GeminiAtsReport(score=score, missing_keywords=missing_keywords, note=note)


def assess_resume_vs_job_with_gemini_cli(
    *,
    resume_yaml_text: str,
    job_description_text: str,
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
) -> GeminiAtsReport:
    """Run Antigravity CLI (``agy``) or legacy Gemini CLI and return an ATS-style match report."""
    input_payload = {
        "resume_yaml": resume_yaml_text,
        "job_description_text": job_description_text,
    }
    stdin_payload = "---CV-ATS-INPUT---\n" + json.dumps(input_payload, ensure_ascii=False)
    response_text = run_agent_cli_headless(
        agent_binary=gemini_binary,
        prompt=_ATS_PROMPT,
        stdin_payload=stdin_payload,
        model=model,
        debug=debug,
    )
    return parse_ats_report_from_llm_response(response_text)

