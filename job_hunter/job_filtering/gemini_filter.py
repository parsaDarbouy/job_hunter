"""Gemini CLI job-fit scoring."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from job_hunter.job_listings.write_jobs_csv import JOB_DESCRIPTION_COLUMN


_FILTER_PROMPT = """You are a job-fit evaluation engine.

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Use only the supplied resume YAML, position YAML, and job row. Do not fabricate facts.
- Evaluate fit against BOTH the candidate resume and the desired position criteria.
- Penalize blocked seniority, unacceptable geography, unrelated titles, unrealistic stated years of experience, and missing core skills.
- Prefer evidence from job_description. If job_description is empty, use the other job row fields and lower confidence.
- alignment_percentage must be an integer from 0 to 100.
- passes must be true only when the job is worth applying to and alignment_percentage is at least minimum_alignment_percentage.
- reason must be one concise sentence.

JSON shape:
{
  "alignment_percentage": 0,
  "passes": false,
  "reason": ""
}

The input JSON follows on stdin after a single line containing only: ---JOB-FILTERING-INPUT---"""


@dataclass(frozen=True)
class GeminiJobAssessment:
    """AI assessment for one exported job row."""

    alignment_percentage: int
    passes: bool
    reason: str


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return stripped


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = _strip_json_fence(text)
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON root must be an object")
    return parsed


def _coerce_percentage(value: Any) -> int:
    try:
        percentage = int(round(float(value)))
    except (TypeError, ValueError):
        percentage = 0
    return max(0, min(100, percentage))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _model_row(row: Mapping[str, str], max_description_chars: int) -> dict[str, str]:
    model_row = {key: str(value or "") for key, value in row.items()}
    description = model_row.get(JOB_DESCRIPTION_COLUMN, "")
    if max_description_chars > 0 and len(description) > max_description_chars:
        model_row[JOB_DESCRIPTION_COLUMN] = description[:max_description_chars]
    return model_row


def assess_job_with_gemini_cli(
    row: Mapping[str, str],
    *,
    resume_yaml_text: str,
    position_yaml_text: str,
    minimum_alignment_percentage: int,
    gemini_binary: str = "gemini",
    model: str = "flash",
    max_description_chars: int = 30_000,
    debug: bool = False,
) -> GeminiJobAssessment:
    """
    Run Gemini CLI in headless mode and parse a strict JSON job-fit assessment.

    Raises RuntimeError on CLI failures or invalid JSON.
    Raises FileNotFoundError if the gemini binary is missing.
    """
    input_payload = {
        "minimum_alignment_percentage": minimum_alignment_percentage,
        "resume_yaml": resume_yaml_text,
        "position_yaml": position_yaml_text,
        "job": _model_row(row, max_description_chars),
    }
    stdin_payload = "---JOB-FILTERING-INPUT---\n" + json.dumps(input_payload, ensure_ascii=False)
    command = [
        gemini_binary,
        "-p",
        _FILTER_PROMPT,
        "--output-format",
        "json",
        "-m",
        model,
        "--skip-trust",
    ]
    try:
        completed = subprocess.run(
            command,
            input=stdin_payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Gemini CLI not found ({gemini_binary}). Install with: npm install -g @google/gemini-cli"
        ) from exc

    if debug:
        if completed.stdout:
            print("[debug] gemini stdout length:", len(completed.stdout), file=sys.stderr)
        if completed.stderr:
            print("[debug] gemini stderr:\n", completed.stderr, file=sys.stderr)

    if completed.returncode != 0:
        raise RuntimeError(
            f"Gemini CLI exited with {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini CLI did not return valid JSON envelope") from exc

    if isinstance(envelope, dict) and envelope.get("error"):
        err = envelope["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Gemini CLI error: {message}")

    response_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Gemini CLI JSON envelope missing response text")

    try:
        parsed = _extract_json_object(response_text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini CLI response did not contain a valid JSON object") from exc

    percentage = _coerce_percentage(parsed.get("alignment_percentage"))
    passes = _coerce_bool(parsed.get("passes")) and percentage >= minimum_alignment_percentage
    reason = str(parsed.get("reason") or "").strip()
    return GeminiJobAssessment(alignment_percentage=percentage, passes=passes, reason=reason)
