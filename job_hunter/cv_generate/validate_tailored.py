"""Post-check tailored LaTeX against resume.yaml employers."""

from __future__ import annotations

import re
from typing import Mapping


_SUBTEXT_PATTERN = re.compile(r"\\subtext\{([^}]+)\}")
_TEXTIT_PATTERN = re.compile(r"\\textit\{([^}]+)\}")


def allowed_employers_from_resume(resume_document: Mapping[str, object]) -> set[str]:
    """Collect normalized company names from resume experience entries."""
    experience = resume_document.get("experience")
    if not isinstance(experience, list):
        return set()
    allowed: set[str] = set()
    for entry in experience:
        if not isinstance(entry, dict):
            continue
        company = str(entry.get("company") or "").strip()
        if company:
            allowed.add(_normalize_employer(company))
    return allowed


def _normalize_employer(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().casefold())


def _employer_from_subtext(segment: str) -> str:
    before_hfill = segment.split("\\hfill")[0]
    return before_hfill.strip()


def extract_employer_mentions(latex_text: str) -> list[str]:
    """Extract employer-like names from LaTeX subtext and textit macros."""
    mentions: list[str] = []
    for match in _SUBTEXT_PATTERN.finditer(latex_text):
        employer = _employer_from_subtext(match.group(1))
        if employer:
            mentions.append(employer)
    for match in _TEXTIT_PATTERN.finditer(latex_text):
        candidate = match.group(1).strip()
        if candidate and not candidate.lower().startswith("http"):
            mentions.append(candidate)
    return mentions


def validate_employers_in_latex(
    *,
    resume_document: Mapping[str, object],
    files: Mapping[str, str],
) -> None:
    """
    Ensure employers referenced in tailored LaTeX exist in resume.yaml.

    Raises ValueError when an unknown employer is detected.
    """
    allowed = allowed_employers_from_resume(resume_document)
    if not allowed:
        return

    unknown: list[str] = []
    for relative_path, content in files.items():
        if "experience" not in relative_path and "previous" not in relative_path:
            continue
        for mention in extract_employer_mentions(content):
            normalized = _normalize_employer(mention)
            if normalized not in allowed:
                unknown.append(f"{relative_path}: {mention}")

    if unknown:
        joined = "; ".join(unknown)
        raise ValueError(
            "Tailored LaTeX references employers not present in resume.yaml experience: "
            f"{joined}"
        )
