"""Public web and LinkedIn guest search used as lookup inputs."""

from __future__ import annotations

import html as html_module
import re
import urllib.parse

from job_hunter.job_filtering.job_page_text import html_to_text
from job_hunter.role_contacts.http_fetch import fetch_url_text
from job_hunter.role_contacts.models import JobIdentity, SearchHit

_DDG_RESULT_PATTERN = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_PATTERN = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_LINKEDIN_JOB_HREF_PATTERN = re.compile(
    r'href="(https://[^"]+/jobs/view/[^"]+)"',
    flags=re.IGNORECASE,
)
_LINKEDIN_JOB_TITLE_PATTERN = re.compile(
    r'base-search-card__title[^>]*>\s*([^<]+)',
    flags=re.IGNORECASE,
)
_LINKEDIN_ORG_ID_PATTERN = re.compile(r"(?:urn:li:organization:|f_C=)(\d+)")
_MAX_HITS_PER_QUERY = 8


def default_search_queries(identity: JobIdentity) -> list[str]:
    """Deterministic DuckDuckGo queries when the model does not return any."""
    company = identity.company_name.strip()
    title = identity.job_title.strip()
    department = identity.department.strip()
    queries: list[str] = []
    if company:
        queries.append(
            f'site:linkedin.com/in "{company}" '
            '("Technical Recruiter" OR "Senior Recruiter" OR "Talent Acquisition")'
        )
        if department:
            queries.append(
                f'site:linkedin.com/posts "{company}" recruiter ({department} OR Platform OR Infrastructure)'
            )
        else:
            queries.append(f'site:linkedin.com/posts "{company}" recruiter ("I\'m hiring" OR "we\'re hiring")')
    if company and title:
        queries.append(
            f'site:linkedin.com/posts "{title}" "{company}" ("I\'m hiring" OR "we\'re hiring" OR hiring)'
        )
        queries.append(f'site:linkedin.com/jobs "{title}" "{company}"')
    return queries[:5]


def unwrap_duckduckgo_url(url: str) -> str:
    """Return the destination URL from a DuckDuckGo redirect link."""
    parsed = urllib.parse.urlparse(html_module.unescape(url))
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return urllib.parse.unquote(query["uddg"][0])
    return html_module.unescape(url)


def parse_duckduckgo_html(html_document: str) -> list[SearchHit]:
    """Parse result titles, URLs, and snippets from DuckDuckGo HTML."""
    titles_and_urls = _DDG_RESULT_PATTERN.findall(html_document)
    snippets = [html_to_text(chunk) for chunk in _DDG_SNIPPET_PATTERN.findall(html_document)]
    hits: list[SearchHit] = []
    for index, (raw_url, raw_title) in enumerate(titles_and_urls[:_MAX_HITS_PER_QUERY]):
        snippet = snippets[index] if index < len(snippets) else ""
        hits.append(
            SearchHit(
                title=html_to_text(raw_title),
                url=unwrap_duckduckgo_url(raw_url),
                snippet=snippet,
                source="duckduckgo",
            )
        )
    return hits


def search_duckduckgo(query: str) -> list[SearchHit]:
    """Run one DuckDuckGo HTML search."""
    body = urllib.parse.urlencode({"q": query}).encode("utf-8")
    html_document = fetch_url_text(
        "https://html.duckduckgo.com/html/",
        method="POST",
        body=body,
        content_type="application/x-www-form-urlencoded",
    )
    return parse_duckduckgo_html(html_document)


def company_linkedin_slug(company_name: str) -> str:
    """Best-effort LinkedIn company URL slug from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower())
    slug = slug.strip("-")
    slug = re.sub(r"-(inc|llc|ltd|corp|co|company)$", "", slug)
    return slug.strip("-")


def parse_linkedin_organization_id(html_document: str) -> str:
    """Return a LinkedIn company numeric id when present in public HTML."""
    match = _LINKEDIN_ORG_ID_PATTERN.search(html_document)
    if match:
        return match.group(1)
    return ""


def parse_linkedin_job_search_html(html_document: str) -> list[SearchHit]:
    """Parse public LinkedIn job-search cards."""
    hrefs = _LINKEDIN_JOB_HREF_PATTERN.findall(html_document)
    titles = [html_to_text(chunk) for chunk in _LINKEDIN_JOB_TITLE_PATTERN.findall(html_document)]
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for index, href in enumerate(hrefs):
        url = html_module.unescape(href).split("?", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        title = titles[index] if index < len(titles) else ""
        hits.append(SearchHit(title=title, url=url, snippet="", source="linkedin_jobs"))
        if len(hits) >= _MAX_HITS_PER_QUERY:
            break
    return hits


def search_linkedin_jobs(identity: JobIdentity) -> list[SearchHit]:
    """Find public LinkedIn job cards for the same company and title."""
    slug = company_linkedin_slug(identity.company_name)
    if not slug:
        return []
    jobs_page = fetch_url_text(f"https://www.linkedin.com/company/{slug}/jobs/")
    organization_id = parse_linkedin_organization_id(jobs_page)
    keywords = identity.job_title or "software engineer"
    query = urllib.parse.urlencode({"keywords": keywords, "location": "Worldwide"})
    if organization_id:
        query += f"&f_C={organization_id}"
    search_url = f"https://www.linkedin.com/jobs/search?{query}"
    html_document = fetch_url_text(search_url)
    hits = parse_linkedin_job_search_html(html_document)
    if hits:
        return hits
    guest_url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
        + urllib.parse.urlencode({"keywords": keywords, "start": "0"})
    )
    if organization_id:
        guest_url += f"&f_C={organization_id}"
    guest_html = fetch_url_text(guest_url)
    return parse_linkedin_job_search_html(guest_html)


def collect_search_hits(*, identity: JobIdentity, queries: list[str]) -> list[SearchHit]:
    """Run DuckDuckGo queries plus a LinkedIn guest job search."""
    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    for query in queries[:5]:
        for hit in search_duckduckgo(query):
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            hits.append(hit)
    for hit in search_linkedin_jobs(identity):
        if hit.url in seen_urls:
            continue
        seen_urls.add(hit.url)
        hits.append(hit)
    return hits
