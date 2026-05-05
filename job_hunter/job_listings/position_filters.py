"""Apply ``position.yaml`` criteria to normalized :class:`JobPosting` rows."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Mapping

from job_hunter.job_listings.location_description_rescue import geography_allowed_with_optional_rescue
from job_hunter.job_listings.location_geo import posting_location_allowed
from job_hunter.job_listings.models import JobPosting

if TYPE_CHECKING:
    from job_hunter.job_listings.location_description_rescue import LocationDescriptionRescueRunner


def _titles_block(position: Mapping[str, Any]) -> Mapping[str, Any]:
    titles = position.get("titles")
    return titles if isinstance(titles, dict) else {}


def _acceptable_title_strings(position: Mapping[str, Any]) -> list[str]:
    raw = _titles_block(position).get("acceptable")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("position.titles.acceptable must be a list when present")
    return [str(item).strip() for item in raw if str(item).strip()]


def _not_acceptable_title_strings(position: Mapping[str, Any]) -> list[str]:
    raw = _titles_block(position).get("not_acceptable")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("position.titles.not_acceptable must be a list when present")
    return [str(item).strip() for item in raw if str(item).strip()]


def posting_title_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Title rules:

    * Any ``not_acceptable`` substring (case-insensitive) rejects.
    * When ``acceptable`` is non-empty, require at least one substring match.
    * When ``acceptable`` is empty, only ``not_acceptable`` is enforced.
    """
    title_lower = posting.title.lower()
    for blocked in _not_acceptable_title_strings(position):
        if blocked.lower() in title_lower:
            return False
    acceptable = _acceptable_title_strings(position)
    if not acceptable:
        return True
    for wanted in acceptable:
        if wanted.lower() in title_lower:
            return True
    return False


def infer_seniority_from_title(title: str) -> str | None:
    """
    Best-effort seniority bucket from the job title only (listing APIs rarely send structured level).

    When several signals appear (e.g. "Senior Staff"), the **highest** band wins.
    Returns one of: executive, head, director, principal, staff, lead, senior, mid_level, junior, intern.
    """
    t = (title or "").strip().lower()
    if not t:
        return None
    hits: list[tuple[int, str]] = []

    def add(rank: int, level: str, cond: bool) -> None:
        if cond:
            hits.append((rank, level))

    add(
        0,
        "executive",
        "vice president" in t
        or bool(re.search(r"\b(cto|ceo|cfo|coo)\b", t))
        or "chief technology officer" in t
        or "chief product officer" in t
        or "chief executive officer" in t,
    )
    add(1, "head", "head of" in t or t.startswith("head "))
    add(2, "director", bool(re.search(r"\bdirector\b", t)))
    add(3, "principal", bool(re.search(r"\bprincipal\b", t)))
    add(4, "staff", bool(re.search(r"\bstaff\b", t)))
    add(5, "lead", bool(re.search(r"\blead\b", t)))
    add(
        6,
        "senior",
        bool(re.search(r"\bsenior\b", t)) or bool(re.search(r"\bsr\.?\b", t)),
    )
    add(
        7,
        "mid_level",
        "mid-level" in t
        or "mid level" in t
        or "engineer ii" in t
        or bool(re.search(r"\bengineer\s*2\b", t)),
    )
    add(
        8,
        "junior",
        bool(re.search(r"\bjunior\b", t))
        or bool(re.search(r"\bjr\.?\b", t))
        or "entry-level" in t
        or "entry level" in t,
    )
    add(9, "intern", bool(re.search(r"\bintern(ship)?\b", t)))
    if not hits:
        return None
    return min(hits, key=lambda x: x[0])[1]


def _seniority_level_list(position: Mapping[str, Any], key: str) -> list[str]:
    raw = position.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"position.{key} must be a list when present")
    return [str(item).strip() for item in raw if str(item).strip()]


def posting_seniority_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Seniority rules use ``acceptable_seniority_levels`` and ``not_acceptable_seniority_levels``.

    * ``not_acceptable_seniority_levels``: reject when :func:`infer_seniority_from_title` matches.
    * ``acceptable_seniority_levels``: when non-empty, require inferred level to be listed.
      Titles with **no** inferred seniority still pass (ATS titles are noisy).
    * When both lists are empty or absent, seniority is not filtered.
    """
    acceptable = _seniority_level_list(position, "acceptable_seniority_levels")
    blocked = _seniority_level_list(position, "not_acceptable_seniority_levels")
    if not acceptable and not blocked:
        return True
    inferred = infer_seniority_from_title(posting.title)
    if inferred is not None and inferred in blocked:
        return False
    if acceptable:
        if inferred is None:
            return True
        return inferred in acceptable
    return True


def posting_compensation_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Compensation is usually absent from ATS list payloads.

    When ``minimum_acceptable_salary_annual`` is set but cannot be evaluated from the
    posting, the row is **kept** so you can review manually in the spreadsheet.
    """
    _ = posting
    _ = position
    return True


def posting_matches_position(
    posting: JobPosting,
    position: Mapping[str, Any],
    *,
    location_rescue_runner: LocationDescriptionRescueRunner | None = None,
) -> bool:
    """Return True when the posting satisfies all implemented filters."""
    if not posting.url.strip():
        return False
    if not posting_title_allowed(posting, position):
        return False
    if not geography_allowed_with_optional_rescue(
        posting,
        position,
        rescue_runner=location_rescue_runner,
    ):
        return False
    if not posting_compensation_allowed(posting, position):
        return False
    if not posting_seniority_allowed(posting, position):
        return False
    return True
