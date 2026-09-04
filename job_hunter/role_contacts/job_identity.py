"""Resolve company, title, and ATS identifiers from a job posting URL."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Mapping

from job_hunter.job_filtering.job_page_text import html_to_text, parse_greenhouse_job_reference
from job_hunter.job_listings.http_json import get_json_optional
from job_hunter.role_contacts.http_fetch import fetch_url_text
from job_hunter.role_contacts.models import JobIdentity

_GREENHOUSE_BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _host(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _path_parts(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    return [part for part in parsed.path.split("/") if part]


def parse_greenhouse_reference(url: str) -> tuple[str, str] | None:
    """
    Return ``(board_token, job_id)`` for Greenhouse postings.

    Extends :func:`parse_greenhouse_job_reference` with ``gh_board`` query params
    used on branded career sites such as Samsara.
    """
    existing = parse_greenhouse_job_reference(url)
    if existing is not None:
        return existing

    parsed = urllib.parse.urlparse(url.strip())
    query = urllib.parse.parse_qs(parsed.query)
    job_id = _first_query_value(query, "gh_jid")
    board_token = _first_query_value(query, "gh_board")
    if job_id and job_id.isdigit() and board_token:
        return board_token, job_id

    host = _host(url)
    parts = _path_parts(url)
    if host in _GREENHOUSE_BOARD_HOSTS and len(parts) >= 3 and parts[1] == "jobs" and parts[2].isdigit():
        return parts[0], parts[2]
    return None


def parse_lever_reference(url: str) -> tuple[str, str] | None:
    """Return ``(site_slug, posting_id)`` for ``jobs.lever.co`` URLs."""
    host = _host(url)
    if host != "jobs.lever.co":
        return None
    parts = _path_parts(url)
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def parse_ashby_reference(url: str) -> tuple[str, str] | None:
    """Return ``(organization_slug, job_id)`` for Ashby job URLs."""
    host = _host(url)
    if host != "jobs.ashbyhq.com":
        return None
    parts = _path_parts(url)
    if len(parts) < 2:
        return None
    if parts[1] == "job" and len(parts) >= 3:
        return parts[0], parts[2]
    return parts[0], parts[1]


def _department_name(payload: Mapping[str, Any]) -> str:
    departments = payload.get("departments")
    if isinstance(departments, list) and departments:
        first = departments[0]
        if isinstance(first, Mapping):
            return str(first.get("name") or "").strip()
    return str(payload.get("department") or payload.get("teamName") or "").strip()


def _location_name(payload: Mapping[str, Any]) -> str:
    location = payload.get("location")
    if isinstance(location, Mapping):
        return str(location.get("name") or "").strip()
    if isinstance(location, str):
        return location.strip()
    categories = payload.get("categories")
    if isinstance(categories, Mapping):
        return str(categories.get("location") or "").strip()
    return ""


def _identity_from_greenhouse_payload(
    *,
    job_url: str,
    board_token: str,
    job_id: str,
    payload: Mapping[str, Any],
) -> JobIdentity:
    location = _location_name(payload)
    return JobIdentity(
        job_url=job_url,
        company_name=str(payload.get("company_name") or "").strip(),
        job_title=str(payload.get("title") or "").strip(),
        location=location,
        department=_department_name(payload),
        requisition_id=str(payload.get("requisition_id") or "").strip(),
        provider_kind="greenhouse",
        provider_job_id=job_id,
        provider_board_token=board_token,
    )


def _identity_from_lever_payload(
    *,
    job_url: str,
    site_slug: str,
    posting_id: str,
    payload: Mapping[str, Any],
) -> JobIdentity:
    categories = payload.get("categories")
    department = ""
    location = ""
    if isinstance(categories, Mapping):
        department = str(categories.get("department") or categories.get("team") or "").strip()
        location = str(categories.get("location") or "").strip()
    return JobIdentity(
        job_url=job_url,
        company_name=str(payload.get("company") or "").strip() or site_slug,
        job_title=str(payload.get("text") or payload.get("title") or "").strip(),
        location=location,
        department=department,
        requisition_id="",
        provider_kind="lever",
        provider_job_id=posting_id,
        provider_board_token=site_slug,
    )


def _title_from_html(html_document: str) -> tuple[str, str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_document, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "", ""
    title_text = html_to_text(match.group(1))
    if " at " in title_text.lower():
        role, _, company = title_text.partition(" at ")
        company = re.split(r"\s+[|\-–]\s+", company, maxsplit=1)[0]
        return role.strip(), company.strip()
    return title_text.strip(), ""


def resolve_job_identity(job_url: str) -> JobIdentity:
    """Fetch public ATS JSON when possible and return a :class:`JobIdentity`."""
    cleaned = job_url.strip()
    greenhouse = parse_greenhouse_reference(cleaned)
    if greenhouse is not None:
        board_token, job_id = greenhouse
        api_url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{urllib.parse.quote(board_token, safe='')}/jobs/{urllib.parse.quote(job_id, safe='')}"
        )
        payload, _error = get_json_optional(api_url)
        if isinstance(payload, Mapping):
            return _identity_from_greenhouse_payload(
                job_url=cleaned,
                board_token=board_token,
                job_id=job_id,
                payload=payload,
            )
        return JobIdentity(
            job_url=cleaned,
            provider_kind="greenhouse",
            provider_job_id=job_id,
            provider_board_token=board_token,
        )

    lever = parse_lever_reference(cleaned)
    if lever is not None:
        site_slug, posting_id = lever
        api_url = (
            f"https://api.lever.co/v0/postings/{urllib.parse.quote(site_slug, safe='')}/"
            f"{urllib.parse.quote(posting_id, safe='')}?mode=json"
        )
        payload, _error = get_json_optional(api_url)
        if isinstance(payload, Mapping):
            return _identity_from_lever_payload(
                job_url=cleaned,
                site_slug=site_slug,
                posting_id=posting_id,
                payload=payload,
            )
        return JobIdentity(
            job_url=cleaned,
            provider_kind="lever",
            provider_job_id=posting_id,
            provider_board_token=site_slug,
        )

    ashby = parse_ashby_reference(cleaned)
    if ashby is not None:
        organization_slug, job_id = ashby
        return JobIdentity(
            job_url=cleaned,
            company_name=organization_slug.replace("-", " ").title(),
            provider_kind="ashby",
            provider_job_id=job_id,
            provider_board_token=organization_slug,
        )

    html_document = fetch_url_text(cleaned)
    title, company = _title_from_html(html_document)
    return JobIdentity(
        job_url=cleaned,
        company_name=company,
        job_title=title,
    )
