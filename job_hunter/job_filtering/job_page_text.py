"""Fetch and reduce public job pages to plain text for AI filtering."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Mapping


_MAX_RESPONSE_BYTES = 2_000_000
_SKIPPED_TAGS = {"script", "style", "noscript", "svg"}
_GREENHOUSE_BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})
_WORKDAY_JOBS_HOST_SUFFIX = ".myworkdayjobs.com"
_META_DESCRIPTION_KEYS = frozenset(
    {"description", "og:description", "twitter:description"},
)
_USER_AGENT = "job-hunter/0.1 (+https://github.com/google-gemini/gemini-cli)"


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return _normalize_text(" ".join(self._parts))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip("\"'")
    return "utf-8"


def html_to_text(html: str) -> str:
    """Extract visible text from an HTML document."""
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


class _MetaDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._best: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attribute_map = {
            name.lower(): (value or "").strip()
            for name, value in attrs
            if name
        }
        content = attribute_map.get("content", "").strip()
        if not content:
            return
        name = attribute_map.get("name", "").lower()
        property_name = attribute_map.get("property", "").lower()
        if name in _META_DESCRIPTION_KEYS or property_name in _META_DESCRIPTION_KEYS:
            if len(content) > len(self._best):
                self._best = content

    def description(self) -> str:
        return _normalize_text(html.unescape(self._best))


def extract_html_meta_description(document_html: str) -> str:
    """Return the longest job-related meta description from an HTML document."""
    parser = _MetaDescriptionParser()
    parser.feed(document_html)
    parser.close()
    return parser.description()


def parse_greenhouse_job_reference(url: str) -> tuple[str, str] | None:
    """
    Return ``(board_token, job_id)`` when ``url`` points at a Greenhouse posting.

    Supports ``gh_jid`` on custom career sites (for example ``careers.upstart.com``)
    and ``/{token}/jobs/{id}`` paths on ``boards.greenhouse.io``.
    """
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    query = urllib.parse.parse_qs(parsed.query)
    job_id = _first_query_value(query, "gh_jid")
    board_token: str | None = None

    path_parts = [part for part in parsed.path.split("/") if part]
    if host in _GREENHOUSE_BOARD_HOSTS and len(path_parts) >= 3 and path_parts[1] == "jobs":
        board_token = path_parts[0]
        if job_id is None and path_parts[2].isdigit():
            job_id = path_parts[2]

    if job_id is None:
        return None
    if not job_id.isdigit():
        return None

    if board_token is None:
        host_parts = host.split(".")
        if len(host_parts) >= 3 and host_parts[0] in {"careers", "jobs"}:
            board_token = host_parts[1]
        else:
            return None

    return board_token, job_id


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _greenhouse_job_api_url(board_token: str, job_id: str) -> str:
    safe_token = urllib.parse.quote(board_token, safe="")
    safe_job_id = urllib.parse.quote(job_id, safe="")
    return f"https://boards-api.greenhouse.io/v1/boards/{safe_token}/jobs/{safe_job_id}"


def _greenhouse_payload_to_text(payload: Mapping[str, Any]) -> str:
    parts: list[str] = []
    title = str(payload.get("title") or "").strip()
    if title:
        parts.append(title)
    company_name = str(payload.get("company_name") or "").strip()
    if company_name:
        parts.append(company_name)
    location = payload.get("location")
    if isinstance(location, dict):
        location_name = str(location.get("name") or "").strip()
        if location_name:
            parts.append(location_name)
    content = str(payload.get("content") or "").strip()
    if content:
        parts.append(html_to_text(html.unescape(content)))
    return _normalize_text("\n\n".join(parts))


def parse_workday_job_reference(url: str) -> tuple[str, str, str, str] | None:
    """
    Return ``(site_origin, tenant, career_site_slug, job_path)`` for Workday URLs.

    Example::
      https://clio.wd3.myworkdayjobs.com/en-US/ClioCareerSite/job/Remote---Canada/Role_ID
    """
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host.endswith(_WORKDAY_JOBS_HOST_SUFFIX):
        return None

    tenant = host.split(".", maxsplit=1)[0]
    if not tenant:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    try:
        job_index = path_parts.index("job")
    except ValueError:
        return None
    if job_index < 1:
        return None

    job_path_parts = path_parts[job_index + 1 :]
    if not job_path_parts:
        return None

    career_site_slug = path_parts[job_index - 1]
    job_path = "/".join(job_path_parts)
    site_origin = f"{parsed.scheme}://{parsed.netloc}"
    return site_origin, tenant, career_site_slug, job_path


def _workday_job_api_url(
    site_origin: str,
    tenant: str,
    career_site_slug: str,
    job_path: str,
) -> str:
    encoded_job_path = "/".join(
        urllib.parse.quote(segment, safe="") for segment in job_path.split("/")
    )
    safe_tenant = urllib.parse.quote(tenant, safe="")
    safe_site = urllib.parse.quote(career_site_slug, safe="")
    return f"{site_origin.rstrip('/')}/wday/cxs/{safe_tenant}/{safe_site}/job/{encoded_job_path}"


def _workday_payload_to_text(payload: Mapping[str, Any]) -> str:
    job_posting = payload.get("jobPostingInfo")
    if not isinstance(job_posting, Mapping):
        return ""

    parts: list[str] = []
    title = str(job_posting.get("title") or "").strip()
    if title:
        parts.append(title)
    location = str(job_posting.get("location") or "").strip()
    if location:
        parts.append(location)
    job_description = str(job_posting.get("jobDescription") or "").strip()
    if job_description:
        parts.append(html_to_text(html.unescape(job_description)))
    return _normalize_text("\n\n".join(parts))


def fetch_workday_job_description(
    site_origin: str,
    tenant: str,
    career_site_slug: str,
    job_path: str,
    *,
    timeout_seconds: int = 30,
) -> str:
    """Fetch a Workday posting via the public ``/wday/cxs/`` JSON API."""
    api_url = _workday_job_api_url(site_origin, tenant, career_site_slug, job_path)
    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError:
        return ""
    payload_data = json.loads(payload.decode("utf-8"))
    if not isinstance(payload_data, dict):
        return ""
    return _workday_payload_to_text(payload_data)


def fetch_greenhouse_job_description(
    board_token: str,
    job_id: str,
    *,
    timeout_seconds: int = 30,
) -> str:
    """Fetch a single Greenhouse posting via the public boards API."""
    api_url = _greenhouse_job_api_url(board_token, job_id)
    request = urllib.request.Request(api_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError:
        return ""
    payload_data = json.loads(payload.decode("utf-8"))
    if not isinstance(payload_data, dict):
        return ""
    return _greenhouse_payload_to_text(payload_data)


def _fetch_html_job_description(url: str, *, timeout_seconds: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read(_MAX_RESPONSE_BYTES)
        content_type = response.headers.get("content-type", "")

    charset = _charset_from_content_type(content_type)
    decoded = payload.decode(charset, errors="replace")
    if "html" in content_type.lower() or "<html" in decoded[:500].lower():
        visible_text = html_to_text(decoded)
        if visible_text:
            return visible_text
        meta_description = extract_html_meta_description(decoded)
        if meta_description:
            return meta_description
        return ""
    return _normalize_text(decoded)


def fetch_job_description(url: str, *, timeout_seconds: int = 30) -> str:
    """Fetch a public job URL and return a compact plain-text description."""
    if not url.strip():
        return ""

    cleaned_url = url.strip()
    description = _fetch_html_job_description(cleaned_url, timeout_seconds=timeout_seconds)
    if description:
        return description

    reference = parse_greenhouse_job_reference(cleaned_url)
    if reference is not None:
        board_token, job_id = reference
        greenhouse_description = fetch_greenhouse_job_description(
            board_token,
            job_id,
            timeout_seconds=timeout_seconds,
        )
        if greenhouse_description:
            return greenhouse_description

    workday_reference = parse_workday_job_reference(cleaned_url)
    if workday_reference is None:
        return ""
    site_origin, tenant, career_site_slug, job_path = workday_reference
    return fetch_workday_job_description(
        site_origin,
        tenant,
        career_site_slug,
        job_path,
        timeout_seconds=timeout_seconds,
    )
