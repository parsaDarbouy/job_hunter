"""Post-check tailored LaTeX against resume.yaml employers."""

from __future__ import annotations

import re
from typing import Any, Mapping


_SUBTEXT_PATTERN = re.compile(r"\\subtext\{([^}]+)\}")
_COMPANY_BEFORE_LOCATION_PATTERN = re.compile(
    r"\\textit\{([^}]+)\},\s*\\textit\{[^}]+\}\s*\\hfill",
)

_MIN_SUBSTRING_MATCH_LEN = 4


def allowed_location_tokens(
    resume_document: Mapping[str, Any],
    *,
    allowed_employers: set[str],
) -> set[str]:
    """
    Cities and ``Remote`` that may appear in the location slot (not employers).

    Includes profile.location, ``remote``, and trailing tokens from company names
    (e.g. ``shiraz`` from ``Rahkar ... Raya Shiraz``).
    """
    tokens: set[str] = {"remote"}
    profile = resume_document.get("profile")
    if isinstance(profile, dict):
        location = str(profile.get("location") or "").strip()
        if location:
            tokens.add(_normalize_employer(location))
            for part in re.split(r"[,/]", location):
                part = part.strip()
                if part:
                    tokens.add(_normalize_employer(part))
    for employer in allowed_employers:
        words = employer.split()
        if words:
            tokens.add(words[-1])
    return tokens


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


def _mention_matches_allowed(mention: str, allowed: set[str]) -> bool:
    normalized = _normalize_employer(mention)
    if not normalized:
        return True
    if normalized in allowed:
        return True
    if len(normalized) < _MIN_SUBSTRING_MATCH_LEN:
        return False
    return any(
        normalized in employer or employer in normalized for employer in allowed
    )


def extract_employer_mentions(latex_text: str) -> list[str]:
    """
    Extract employer names from experience LaTeX.

    Uses ``\\subtext`` (employer before ``\\hfill`` only) and the company
    ``\\textit`` before a location ``\\textit`` (previous experience). Does not
    treat the location slot (``Remote``, city names) as an employer.
    """
    mentions: list[str] = []
    for match in _SUBTEXT_PATTERN.finditer(latex_text):
        employer = _employer_from_subtext(match.group(1))
        if employer:
            mentions.append(employer)
    for match in _COMPANY_BEFORE_LOCATION_PATTERN.finditer(latex_text):
        employer = match.group(1).strip()
        if employer:
            mentions.append(employer)
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

    location_tokens = allowed_location_tokens(
        resume_document,
        allowed_employers=allowed,
    )

    unknown: list[str] = []
    for relative_path, content in files.items():
        if "experience" not in relative_path and "previous" not in relative_path:
            continue
        for mention in extract_employer_mentions(content):
            normalized = _normalize_employer(mention)
            if normalized in location_tokens:
                continue
            if not _mention_matches_allowed(mention, allowed):
                unknown.append(f"{relative_path}: {mention}")

    if unknown:
        joined = "; ".join(unknown)
        raise ValueError(
            "Tailored LaTeX references employers not present in resume.yaml experience: "
            f"{joined}"
        )
