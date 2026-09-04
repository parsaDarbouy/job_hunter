"""Orchestrate recruiter and hiring-manager lookup for one job URL."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import yaml

from job_hunter.agent_cli import DEFAULT_AGENT_BINARY
from job_hunter.cv_generate.filename import slugify_filename_part
from job_hunter.paths import cv_output_dir, default_resume_yaml_path, job_description_path
from job_hunter.resume_ingest.resume_settings import parse_target_job_url
from job_hunter.role_contacts.agent_contacts import (
    extract_contacts_from_hits,
    plan_search_queries,
)
from job_hunter.role_contacts.http_fetch import fetch_url_text
from job_hunter.role_contacts.job_identity import resolve_job_identity
from job_hunter.role_contacts.models import ContactCandidate, JobIdentity, RoleContactReport, SearchHit
from job_hunter.role_contacts.posting_extract import extract_contacts_from_text
from job_hunter.role_contacts.search import collect_search_hits, default_search_queries
from job_hunter.role_contacts.yaml_writer import write_contacts_yaml

_logger = logging.getLogger(__name__)

_POSTING_EXCERPT_CHARS = 6_000


def merge_contact_candidates(
    posting_contacts: Sequence[ContactCandidate],
    search_contacts: Sequence[ContactCandidate],
) -> list[ContactCandidate]:
    """Prefer posting-derived contacts, then fill from search extraction."""
    merged: list[ContactCandidate] = []
    seen: set[str] = set()
    for candidate in list(posting_contacts) + list(search_contacts):
        key = candidate.email.lower() or candidate.linkedin_url.lower() or candidate.name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(candidate)
        if len(merged) >= 5:
            break
    return merged


def default_contacts_output_path(identity: JobIdentity) -> Path:
    """Place contacts.yaml under the same company/position dirs used for CVs."""
    company_part = slugify_filename_part(identity.company_name or "unknown")
    position_part = slugify_filename_part(identity.job_title or "unknown")
    return cv_output_dir() / company_part / position_part / "contacts.yaml"


def _job_url_from_resume(resume_path: Path) -> str:
    document = yaml.safe_load(resume_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"Resume YAML must be a mapping: {resume_path}")
    return parse_target_job_url(document)


def _print_contacts_report(report: RoleContactReport, output_path: Path) -> None:
    print("\n==================== ROLE CONTACTS ====================", file=sys.stderr)
    print(f"Wrote: {output_path}", file=sys.stderr)
    if not report.candidates:
        print("No recruiter or hiring manager found from public sources.", file=sys.stderr)
    for candidate in report.candidates:
        link = candidate.linkedin_url or candidate.email or "(no public URL)"
        print(
            f"{candidate.name} ({candidate.kind}, {candidate.confidence}) {link}",
            file=sys.stderr,
        )
    print("======================================================\n", file=sys.stderr)


def run_role_contact_lookup(
    *,
    job_url: str,
    output_path: Path | None = None,
    job_description_text: str = "",
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
    resolve_identity: Callable[[str], JobIdentity] = resolve_job_identity,
    fetch_posting_html: Callable[[str], str] = fetch_url_text,
    plan_queries: Callable[..., list[str]] = plan_search_queries,
    collect_hits: Callable[..., list[SearchHit]] = collect_search_hits,
    extract_from_hits: Callable[..., list[ContactCandidate]] = extract_contacts_from_hits,
) -> Path:
    """
    Look up public recruiter and hiring-manager contacts for ``job_url``.

    Writes YAML and prints a short stderr summary. Returns the output path.
    """
    identity = resolve_identity(job_url)
    posting_html = fetch_posting_html(job_url)
    excerpt_source = job_description_text.strip() or posting_html
    posting_contacts = extract_contacts_from_text(posting_html)
    if job_description_text.strip():
        posting_contacts = merge_contact_candidates(
            posting_contacts,
            extract_contacts_from_text(job_description_text),
        )

    queries: list[str] = []
    ai_used = False
    try:
        queries = plan_queries(
            identity,
            agent_binary=gemini_binary,
            model=model,
            debug=debug,
        )
        ai_used = True
    except Exception as exc:
        _logger.warning("role_contacts.query_plan_failed error=%s", exc)

    if not queries:
        queries = default_search_queries(identity)

    hits = collect_hits(identity=identity, queries=queries)
    search_contacts: list[ContactCandidate] = []
    try:
        search_contacts = extract_from_hits(
            identity=identity,
            posting_excerpt=excerpt_source[:_POSTING_EXCERPT_CHARS],
            posting_contacts=posting_contacts,
            hits=hits,
            agent_binary=gemini_binary,
            model=model,
            debug=debug,
        )
        ai_used = True
    except Exception as exc:
        _logger.warning("role_contacts.extract_failed error=%s", exc)

    candidates = merge_contact_candidates(posting_contacts, search_contacts)
    destination = (output_path or default_contacts_output_path(identity)).expanduser().resolve()
    report = RoleContactReport(
        job_url=identity.job_url,
        company_name=identity.company_name,
        job_title=identity.job_title,
        looked_up_at=datetime.now(timezone.utc).isoformat(),
        ai_used=ai_used,
        candidates=candidates,
    )
    written = write_contacts_yaml(report, destination)
    _print_contacts_report(report, written)
    return written


def run_lookup_after_cv_generate(
    *,
    pdf_path: Path,
    resume_path: Path | None = None,
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
) -> Path | None:
    """
    Run lookup after ``cv:generate`` using the resume job URL and CV folder.

    Failures are logged and swallowed so CV generation still succeeds.
    """
    resume_file = (resume_path or default_resume_yaml_path()).expanduser().resolve()
    try:
        job_url = _job_url_from_resume(resume_file)
    except Exception as exc:
        _logger.warning("role_contacts.skip_missing_job_url error=%s", exc)
        return None

    description_text = ""
    description_file = job_description_path()
    if description_file.is_file():
        description_text = description_file.read_text(encoding="utf-8")

    output_path = pdf_path.expanduser().resolve().parent / "contacts.yaml"
    try:
        return run_role_contact_lookup(
            job_url=job_url,
            output_path=output_path,
            job_description_text=description_text,
            gemini_binary=gemini_binary,
            model=model,
            debug=debug,
        )
    except Exception as exc:
        _logger.warning("role_contacts.lookup_failed error=%s", exc)
        return None
