"""Public URL builders for supported ATS job list endpoints."""

from __future__ import annotations

from urllib.parse import quote


def greenhouse_jobs_url(board_token: str) -> str:
    """Greenhouse public jobs JSON for a board token."""
    safe = quote(str(board_token), safe="")
    return f"https://boards-api.greenhouse.io/v1/boards/{safe}/jobs"


def ashby_job_board_url(organization_slug: str) -> str:
    """Ashby public posting API for a job board slug."""
    safe = quote(str(organization_slug), safe="")
    return f"https://api.ashbyhq.com/posting-api/job-board/{safe}?includeCompensation=true"


def lever_postings_url(site_slug: str) -> str:
    """Lever public postings JSON for a careers site slug (``jobs.lever.co/{slug}``)."""
    safe = quote(str(site_slug), safe="")
    return f"https://api.lever.co/v0/postings/{safe}?mode=json"


def workable_apply_jobs_url(apply_account_slug: str) -> str:
    """
    Workable public widget JSON for an account slug (path under ``apply.workable.com/{slug}/``).

    Uses the v1 widget endpoint, which is typically reachable without an API key; the older
    ``/api/v3/accounts/.../jobs`` URL often returns 404 for public callers.
    """
    safe = quote(str(apply_account_slug), safe="")
    return f"https://apply.workable.com/api/v1/widget/accounts/{safe}"
