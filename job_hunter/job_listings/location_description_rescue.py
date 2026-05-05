"""Gemini-assisted geography pass when ATS ``location`` is ambiguous versus ``position.yaml``."""

from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

from job_hunter.job_listings.location_geo import posting_location_allowed
from job_hunter.job_listings.models import JobPosting


def summarize_location_constraints_for_prompt(location_constraints: Mapping[str, Any]) -> str:
    """Human-readable geography rules for prompting (mirrors heuristic checks)."""
    lines: list[str] = []
    countries = location_constraints.get("countries_onsite_or_hybrid_ok") or []
    if isinstance(countries, list) and countries:
        lines.append(f"- Onsite or hybrid acceptable in countries: {[str(c).strip() for c in countries if str(c).strip()]}")
    cities = location_constraints.get("cities_onsite_or_hybrid_ok") or []
    if isinstance(cities, list) and cities:
        lines.append(f"- Onsite or hybrid acceptable in cities: {[str(c).strip() for c in cities if str(c).strip()]}")
    remote_countries = location_constraints.get("remote_work_allowed_from_countries") or []
    if isinstance(remote_countries, list) and remote_countries:
        lines.append(
            "- Remote-only / distributed roles are acceptable when the employer allows the worker to be based in: "
            f"{[str(c).strip() for c in remote_countries if str(c).strip()]}"
        )
    if location_constraints.get("globally_remote_acceptable") is True:
        lines.append("- Truly worldwide / no-country-restriction remote (explicit in text) is acceptable.")
    if not lines:
        return "(no geography rules provided)"
    return "\n".join(lines)


_HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.DOTALL)
_SCRIPT_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)


def strip_html_to_plain_text(fragment: str, *, maximum_characters: int) -> str:
    """Cheap HTML removal for ATS snippets; truncation limits prompt size."""
    if not fragment or not fragment.strip():
        return ""
    without_scripts = _SCRIPT_PATTERN.sub(" ", fragment)
    without_tags = _HTML_TAG_PATTERN.sub(" ", without_scripts)
    text = html_lib.unescape(without_tags)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > maximum_characters:
        return text[:maximum_characters] + "\n...[truncated]"
    return text


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
        raise ValueError("No JSON object found in Gemini response body")
    parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response root must be a JSON object")
    return parsed


_LOCATION_LIKELIHOOD_PROMPT = """You judge whether a job description matches stated geography constraints.

Return exactly one JSON object (no markdown). Shape:
{"likelihood": number, "rationale": string}

- "likelihood" is between 0.0 and 1.0: your calibrated probability that a candidate satisfying the GEOGRAPHY CONSTRAINTS below can realistically take this job (eligible location / remote footprint as described).

- Base likelihood on explicit job-description text only. If the description does not mention where someone may work from, assume low likelihood unless the LOCATION FIELD clearly fits the constraints already (the model still sees both).

- Use likelihood above 0.5 only when the text reasonably supports eligibility under those constraints.

- "rationale" is one short sentence.

The stdin body after ---JOB--- begins with GEOGRAPHY CONSTRAINTS, then title, listing location field, then plain-text description.

"""


def _invoke_gemini_json(
    *,
    prompt: str,
    stdin_payload: str,
    gemini_binary: str,
    model: str,
    debug: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = [
        gemini_binary,
        "-p",
        prompt,
        "--output-format",
        "json",
        "-m",
        model,
        "--skip-trust",
    ]
    completed = subprocess.run(
        command,
        input=stdin_payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if debug and completed.stderr:
        print("[debug][location-rescue] gemini stderr:\n", completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Gemini CLI failed (exit {completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini CLI returned invalid outer JSON") from exc
    if isinstance(envelope, dict) and envelope.get("error"):
        err = envelope["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Gemini CLI error: {message}")
    response_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError("Gemini CLI envelope missing response text")
    return _extract_json_object(response_text)


@dataclass
class LocationDescriptionRescueConfig:
    threshold: float
    min_plain_text_chars: int
    max_description_chars: int
    gemini_binary: str
    model: str
    timeout_seconds: float
    constraints_summary: str
    debug: bool


class LocationDescriptionRescueRunner:
    """When board location fails heuristics, ask Gemini whether the JD supports the geography rules."""

    def __init__(self, *, position: Mapping[str, Any], config: LocationDescriptionRescueConfig) -> None:
        self._constraints_summary = config.constraints_summary
        self._config = config
        self._likelihood_cache: dict[str, float] = {}

    @staticmethod
    def maybe_build(
        position: Mapping[str, Any],
        *,
        gemini_binary: str | None,
        model: str | None,
        debug: bool,
    ) -> LocationDescriptionRescueRunner | None:
        constraints = position.get("location_constraints")
        if not isinstance(constraints, dict):
            return None
        rescue = constraints.get("gemini_description_rescue")
        if not isinstance(rescue, dict) or rescue.get("enabled") is not True:
            return None
        threshold_raw = rescue.get("minimum_likelihood", 0.5)
        threshold = float(threshold_raw)
        if not (0.0 <= threshold <= 1.0):
            raise ValueError("location_constraints.gemini_description_rescue.minimum_likelihood must be between 0 and 1")
        min_plain = int(rescue.get("min_plain_text_chars", 80))
        max_desc = int(rescue.get("max_description_chars", 14_000))
        timeout_seconds = float(rescue.get("timeout_seconds", 120))
        gb = rescue.get("gemini_binary") or gemini_binary or "gemini"
        md = rescue.get("model") or model or "flash"
        summary = summarize_location_constraints_for_prompt(constraints)
        config = LocationDescriptionRescueConfig(
            threshold=threshold,
            min_plain_text_chars=max(0, min_plain),
            max_description_chars=max(500, max_desc),
            gemini_binary=str(gb),
            model=str(md),
            timeout_seconds=max(30.0, timeout_seconds),
            constraints_summary=summary,
            debug=debug,
        )
        return LocationDescriptionRescueRunner(position=position, config=config)

    def eligible_via_description(self, posting: JobPosting) -> bool:
        key = posting.url.strip()
        if key in self._likelihood_cache:
            return self._likelihood_cache[key] >= self._config.threshold

        plain = strip_html_to_plain_text(posting.description_html or "", maximum_characters=self._config.max_description_chars)
        if len(plain) < self._config.min_plain_text_chars:
            if self._config.debug:
                print(
                    f"[debug][location-rescue] skip (description too short: {len(plain)} chars): {posting.title!r}",
                )
            self._likelihood_cache[key] = 0.0
            return False

        stdin_payload = (
            "---JOB---\nGEOGRAPHY CONSTRAINTS:\n"
            f"{self._constraints_summary}\n\n"
            f"TITLE: {posting.title}\n"
            f"LISTING LOCATION FIELD: {posting.location}\n\n"
            "JOB DESCRIPTION PLAIN TEXT:\n"
            f"{plain}\n"
        )
        try:
            parsed = _invoke_gemini_json(
                prompt=_LOCATION_LIKELIHOOD_PROMPT,
                stdin_payload=stdin_payload,
                gemini_binary=self._config.gemini_binary,
                model=self._config.model,
                debug=self._config.debug,
                timeout_seconds=self._config.timeout_seconds,
            )
        except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            if self._config.debug:
                print(f"[debug][location-rescue] Gemini call failed ({type(exc).__name__}): {exc}")
            self._likelihood_cache[key] = 0.0
            return False
        likelihood_raw = parsed.get("likelihood")
        try:
            likelihood = float(likelihood_raw)
        except (TypeError, ValueError):
            likelihood = 0.0
        likelihood = max(0.0, min(1.0, likelihood))
        self._likelihood_cache[key] = likelihood
        if self._config.debug:
            rationale = parsed.get("rationale", "")
            print(
                f"[debug][location-rescue] likelihood={likelihood:.2f} title={posting.title!r} "
                f"rationale={rationale!s}",
            )
        return likelihood >= self._config.threshold


def geography_allowed_with_optional_rescue(
    posting: JobPosting,
    position: Mapping[str, Any],
    *,
    rescue_runner: LocationDescriptionRescueRunner | None,
) -> bool:
    """Primary location heuristic, then optional Gemini read of the job description."""
    if posting_location_allowed(posting, position):
        return True
    if rescue_runner is None:
        return False
    return rescue_runner.eligible_via_description(posting)
