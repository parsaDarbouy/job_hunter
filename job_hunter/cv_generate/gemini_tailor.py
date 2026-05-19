"""Gemini CLI tailoring of LaTeX CV files from resume YAML and job description."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

from job_hunter.cv_generate.layout_constraints import CvLayoutConstraints
from job_hunter.json_extract import extract_json_object

_logger = logging.getLogger(__name__)

_TAILOR_PROMPT = """You are a CV tailoring engine for ATS-friendly LaTeX resumes.

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Use ONLY facts present in resume_yaml and job_description_text. Do not fabricate experience.
- FORBIDDEN: new employers, job titles, employment dates, degrees, certifications, tools, metrics, or projects not supported by resume_yaml.
- ALLOWED: rephrase existing highlights; reorder bullets; emphasize skills already listed in resume_yaml; bold keywords that already appear in resume_yaml or job_description_text; tighten the objective; omit or shorten content to respect resume_max_pages.
- cv_layout_constraints (STRICT — must match exactly; count plain words with LaTeX markup removed):
  * sections/objective.tex (about me): word count MUST be >= about_me_word_count.min and <= about_me_word_count.max.
  * Experience \\item bullets in sections/experience.tex ONLY: include up to experience_bullets_per_page * resume_max_pages bullets total (never exceed). Prefer job-relevant highlights; use real bullets from resume_yaml only.
  * Each \\item in sections/experience.tex: plain-word count MUST be >= experience_bullet_word_count.min and <= experience_bullet_word_count.max. Shorten or split phrasing to comply; do not pad with filler words.
  * Each \\item in sections/experience.tex MUST wrap main keywords in \\textbf{{...}} (2–5 per bullet): technologies, tools, platforms, and role-relevant terms that already appear in resume_yaml or job_description_text (e.g. \\textbf{{AWS}}, \\textbf{{Kubernetes}}, \\textbf{{CI/CD}}). Do not bold entire sentences or words not in the source material.
  * sections/previous.tex (Previous Experience): NO \\item, NO \\begin{{zitemize}}, NO \\subsection, NO bullet lists. Use only the compact template format from template_files — one line per older role: \\skills{{Job title}}, \\textit{{Employer}}, \\textit{{Remote or city}} \\hfill {{\\bf start - end}}. List older roles from resume_yaml that are not already in sections/experience.tex.
- about_me_note (when non-empty): manual context for sections/objective.tex only. Reflect it in the about-me paragraph when it fits the target role and stays within about_me_word_count. Use only facts stated in about_me_note and resume_yaml; do not invent employers, tools, or metrics.
- experience_note_hints (when non-empty): apply only to sections/experience.tex (not previous.tex). For each hint, you MAY weave that note into at most ONE \\item for the matching employer—lightly (a short clause only). Do NOT expand the note into new responsibilities, metrics, or tools.
- Populate resume.tex contact macros (\\author, \\phone, \\city, \\email, \\LinkedIn, \\github) from resume_yaml profile when those values exist: profile.phone → \\phone, profile.location → \\city; otherwise keep existing template values.
- Populate sections/Accomplishments.tex from resume_yaml accomplishments (title, detail, date) when present; use the template's LaTeX structure (\\skills{}, \\textit{}, date on the right).
- Employment location (not the employer): use \\hfill Remote or a real city from resume_yaml (profile.location or the city in the company name, e.g. Shiraz). Main experience: \\subtext{{Employer \\hfill Remote}} or \\subtext{{Employer \\hfill City}}. Previous experience: \\textit{{Employer}}, \\textit{{Remote}} or \\textit{{City}} \\hfill. Never put only a city or Remote in the employer/company field.
- Preserve each file's LaTeX structure (\\documentclass, \\begin{document}, \\import-compatible section wrappers, \\subsection, \\subtext, zitemize, etc.).
- Escape LaTeX special characters in plain text: &, %, $, #, _, {, }, ~, ^, \\.
- Keep the CV within resume_max_pages when compiled (prefer fewer bullets and shorter sections when the limit is 1).
- company_name and position_title must be taken from the job_description_text (hiring company and role being applied for).

JSON shape:
{
  "company_name": "",
  "position_title": "",
  "files": {
    "resume.tex": "",
    "sections/objective.tex": "",
    "sections/skills.tex": "",
    "sections/experience.tex": "",
    "sections/education.tex": "",
    "sections/previous.tex": "",
    "sections/Accomplishments.tex": ""
  }
}

The input JSON follows on stdin after a single line containing only: ---CV-GENERATE-INPUT---"""


@dataclass(frozen=True)
class GeminiCvTailorResult:
    """Parsed Gemini output for CV tailoring."""

    company_name: str
    position_title: str
    files: dict[str, str]


def _coerce_files(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Gemini response files must be an object")
    files: dict[str, str] = {}
    for key, content in value.items():
        if not isinstance(key, str) or not isinstance(content, str):
            raise ValueError("Each tailored file must be a string path and string content")
        files[key] = content
    if not files:
        raise ValueError("Gemini response files must not be empty")
    return files


def tailor_cv_with_gemini_cli(
    *,
    resume_yaml_text: str,
    job_description_text: str,
    resume_max_pages: int,
    template_files: Mapping[str, str],
    experience_note_hints: list[dict[str, str]] | None = None,
    about_me_note: str = "",
    cv_layout_constraints: CvLayoutConstraints | None = None,
    gemini_binary: str = "gemini",
    model: str = "flash",
    debug: bool = False,
) -> GeminiCvTailorResult:
    """
    Run Gemini CLI in headless mode and parse tailored LaTeX file contents.

    Raises RuntimeError on CLI failures or invalid JSON.
    Raises FileNotFoundError if the gemini binary is missing.
    """
    input_payload: dict[str, Any] = {
        "resume_max_pages": resume_max_pages,
        "resume_yaml": resume_yaml_text,
        "job_description_text": job_description_text,
        "template_files": dict(template_files),
    }
    if experience_note_hints:
        input_payload["experience_note_hints"] = experience_note_hints
    if about_me_note.strip():
        input_payload["about_me_note"] = about_me_note.strip()
    if cv_layout_constraints is not None:
        input_payload["cv_layout_constraints"] = cv_layout_constraints.as_dict()
    stdin_payload = "---CV-GENERATE-INPUT---\n" + json.dumps(input_payload, ensure_ascii=False)
    command = [
        gemini_binary,
        "-p",
        _TAILOR_PROMPT,
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
            timeout=900,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Gemini CLI not found ({gemini_binary}). Install with: npm install -g @google/gemini-cli"
        ) from exc

    if debug:
        if completed.stdout:
            _logger.debug("gemini_tailor.subprocess stdout_bytes=%s", len(completed.stdout))
        if completed.stderr:
            err_text = completed.stderr.strip()
            if len(err_text) > 2_000:
                err_text = err_text[:2_000] + "…(truncated)"
            _logger.debug("gemini_tailor.subprocess stderr=%s", err_text)

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
        parsed = extract_json_object(response_text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini CLI response did not contain a valid JSON object") from exc

    company_name = str(parsed.get("company_name") or "").strip()
    position_title = str(parsed.get("position_title") or "").strip()
    if not company_name or not position_title:
        raise RuntimeError("Gemini response must include company_name and position_title")

    files = _coerce_files(parsed.get("files"))
    return GeminiCvTailorResult(
        company_name=company_name,
        position_title=position_title,
        files=files,
    )
