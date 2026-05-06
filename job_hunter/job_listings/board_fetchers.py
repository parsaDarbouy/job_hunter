"""Fetch and normalize job rows from supported ATS public endpoints."""

from __future__ import annotations

from typing import Any, Mapping

from job_hunter.job_listings.http_json import get_json_optional
from job_hunter.job_listings.models import JobPosting


def fetch_jobs_for_source(source: Mapping[str, Any]) -> tuple[list[JobPosting], str | None]:
    """
    Return normalized postings plus an optional human-readable warning.

    Unsupported or manual sources return an empty list without error.
    """
    kind = source.get("kind")
    source_id = str(source.get("id", "unknown"))
    if kind == "custom_career_page":
        return [], None
    if kind == "greenhouse":
        return _fetch_greenhouse(source, source_id)
    if kind == "ashby":
        return _fetch_ashby(source, source_id)
    if kind == "workable":
        return _fetch_workable(source, source_id)
    return [], f"skip unknown provider kind {kind!r} for source {source_id!r}"


def _fetch_greenhouse(source: Mapping[str, Any], source_id: str) -> tuple[list[JobPosting], str | None]:
    from job_hunter.job_listings.board_urls import greenhouse_jobs_url

    token = source.get("board_token")
    if not token:
        return [], f"greenhouse source {source_id!r} missing board_token"
    url = greenhouse_jobs_url(str(token))
    payload, error_message = get_json_optional(url)
    if error_message:
        return [], error_message
    assert isinstance(payload, dict)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return [], f"greenhouse response missing jobs[] for {source_id!r}"
    postings: list[JobPosting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("absolute_url") or "").strip()
        location_value = job.get("location")
        if isinstance(location_value, dict):
            location_text = str(location_value.get("name") or "").strip()
        else:
            location_text = str(location_value or "").strip()
        if not title or not link:
            continue
        postings.append(
            JobPosting(
                url=link,
                title=title,
                location=location_text,
                source_id=source_id,
                provider_kind="greenhouse",
            )
        )
    return postings, None


def _fetch_ashby(source: Mapping[str, Any], source_id: str) -> tuple[list[JobPosting], str | None]:
    from job_hunter.job_listings.board_urls import ashby_job_board_url

    slug = source.get("organization_slug")
    if not slug:
        return [], f"ashby source {source_id!r} missing organization_slug"
    url = ashby_job_board_url(str(slug))
    payload, error_message = get_json_optional(url)
    if error_message:
        return [], error_message
    assert isinstance(payload, dict)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return [], f"ashby response missing jobs[] for {source_id!r}"
    postings: list[JobPosting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = str(job.get("title") or "").strip()
        link = str(job.get("jobUrl") or "").strip()
        location_text = str(job.get("location") or "").strip()
        if not title or not link:
            continue
        postings.append(
            JobPosting(
                url=link,
                title=title,
                location=location_text,
                source_id=source_id,
                provider_kind="ashby",
            )
        )
    return postings, None


def _first_url_field(job: dict[str, Any]) -> str:
    """Pick the best-effort public URL from a Workable-shaped job object."""
    for key in ("url", "application_url", "job_url", "public_url", "shortcode_url"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    shortcode = job.get("shortcode")
    if isinstance(shortcode, str) and shortcode.strip():
        return f"https://apply.workable.com/j/{shortcode.strip()}"
    return ""


def _workable_results_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        jobs = payload.get("jobs")
        if isinstance(jobs, list):
            return [item for item in jobs if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _location_from_workable_job(job: Mapping[str, Any]) -> str:
    """Flatten city / country / remote fields when present."""
    city = str(job.get("city") or "").strip()
    country = str(job.get("country") or "").strip()
    location_label = str(job.get("location") or "").strip()
    telework = job.get("telework")
    remote_bits: list[str] = []
    if job.get("telecommuting") is True:
        remote_bits.append("Remote")
    if isinstance(telework, dict):
        if telework.get("fully_remote") is True:
            remote_bits.append("Remote")
    if location_label:
        return location_label
    parts = [part for part in (city, country) if part]
    if remote_bits and parts:
        return ", ".join(parts) + " (" + remote_bits[0] + ")"
    if parts:
        return ", ".join(parts)
    return remote_bits[0] if remote_bits else ""


def _fetch_workable(source: Mapping[str, Any], source_id: str) -> tuple[list[JobPosting], str | None]:
    from job_hunter.job_listings.board_urls import workable_apply_jobs_url

    slug = source.get("apply_account_slug")
    if not slug:
        return [], f"workable source {source_id!r} missing apply_account_slug"
    url = workable_apply_jobs_url(str(slug))
    payload, error_message = get_json_optional(url)
    if error_message:
        return [], error_message
    rows = _workable_results_list(payload)
    postings: list[JobPosting] = []
    for job in rows:
        title = str(job.get("title") or "").strip()
        link = _first_url_field(job)
        location_text = _location_from_workable_job(job)
        if not title or not link:
            continue
        postings.append(
            JobPosting(
                url=link,
                title=title,
                location=location_text,
                source_id=source_id,
                provider_kind="workable",
            )
        )
    return postings, None if postings else "workable response contained no parseable job rows"


def dedupe_job_postings_by_url(postings: list[JobPosting]) -> list[JobPosting]:
    """Stable de-duplication by URL (first occurrence wins)."""
    seen: set[str] = set()
    unique: list[JobPosting] = []
    for posting in postings:
        key = posting.url.strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(posting)
    return unique
