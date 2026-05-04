"""Apply ``position.yaml`` criteria to normalized :class:`JobPosting` rows."""

from __future__ import annotations

from typing import Any, Mapping

from job_hunter.job_listings.models import JobPosting


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


def posting_location_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Conservative geography match using ``location_constraints``:

    * Pass when the job location string contains a configured country or city.
    * Pass when it contains a ``remote_work_allowed_from_countries`` entry.
    * When ``globally_remote_acceptable`` is true, pass for explicit worldwide-style phrases.
    """
    constraints = position.get("location_constraints")
    if not isinstance(constraints, dict):
        return True
    has_geography_or_remote_rule = any(
        [
            bool(constraints.get("countries_onsite_or_hybrid_ok")),
            bool(constraints.get("cities_onsite_or_hybrid_ok")),
            bool(constraints.get("remote_work_allowed_from_countries")),
            constraints.get("globally_remote_acceptable") is True,
        ]
    )
    if not has_geography_or_remote_rule:
        return True
    location_text = (posting.location or "").strip()
    location_lower = location_text.lower()
    if not location_lower:
        return bool(constraints.get("globally_remote_acceptable"))

    for country in constraints.get("countries_onsite_or_hybrid_ok") or []:
        if isinstance(country, str) and country.strip() and country.lower() in location_lower:
            return True
    for city in constraints.get("cities_onsite_or_hybrid_ok") or []:
        if isinstance(city, str) and city.strip() and city.lower() in location_lower:
            return True
    for country in constraints.get("remote_work_allowed_from_countries") or []:
        if isinstance(country, str) and country.strip() and country.lower() in location_lower:
            return True

    if constraints.get("globally_remote_acceptable") is True:
        worldwide_phrases = (
            "worldwide",
            "anywhere",
            "globally",
            "global remote",
            "fully distributed",
            "100% remote",
        )
        if any(phrase in location_lower for phrase in worldwide_phrases):
            return True

    return False


def posting_compensation_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Compensation is usually absent from ATS list payloads.

    When ``minimum_acceptable_salary_annual`` is set but cannot be evaluated from the
    posting, the row is **kept** so you can review manually in the spreadsheet.
    """
    _ = posting
    _ = position
    return True


def posting_matches_position(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """Return True when the posting satisfies all implemented filters."""
    if not posting.url.strip():
        return False
    if not posting_title_allowed(posting, position):
        return False
    if not posting_location_allowed(posting, position):
        return False
    if not posting_compensation_allowed(posting, position):
        return False
    return True
