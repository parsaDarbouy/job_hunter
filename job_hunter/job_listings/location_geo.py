"""Conservative heuristic matching of ATS ``location`` strings against ``location_constraints``."""

from __future__ import annotations

from typing import Mapping

from job_hunter.job_listings.models import JobPosting


def posting_location_allowed(posting: JobPosting, position: Mapping[str, Any]) -> bool:
    """
    Geography match using ``location_constraints``:

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
