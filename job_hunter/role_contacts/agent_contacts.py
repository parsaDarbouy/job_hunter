"""Agent prompts that plan search queries and extract contacts from snippets."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Sequence

from job_hunter.agent_cli import DEFAULT_AGENT_BINARY, run_agent_cli_headless
from job_hunter.json_extract import extract_json_object
from job_hunter.role_contacts.models import (
    ContactCandidate,
    JobIdentity,
    SearchHit,
    normalize_confidence,
    normalize_contact_kind,
)

_QUERY_PROMPT = """You plan public web searches to find the recruiter and/or hiring manager for one job.

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Do not invent people. You are only writing search queries.
- Prefer LinkedIn: site:linkedin.com/in for recruiters, site:linkedin.com/posts for hiring posts.
- Use the exact company name and job title when they are provided.
- At most 5 queries. Each query must be a single string a search engine can run.

JSON shape:
{
  "queries": ["", ""]
}

The input JSON follows on stdin after a single line containing only: ---ROLE-CONTACTS-QUERIES---"""

_EXTRACT_PROMPT = """You extract recruiter and hiring-manager contacts for one job from search snippets.

Rules (strict):
- Output exactly ONE JSON object and nothing else. No markdown fences, no commentary.
- Only name people who appear in the provided snippets or posting excerpts.
- Do not invent LinkedIn URLs, emails, titles, or names.
- If a URL is not in the input, leave linkedin_url empty.
- Prefer recruiters whose book matches this team (platform, infrastructure, security, etc.).
- Hiring managers are engineering leaders posting this role, not recruiters.
- confidence is high only when the snippet clearly ties the person to this company and this kind of role.
- Cap at 5 candidates. Empty list is allowed.

JSON shape:
{
  "candidates": [
    {
      "name": "",
      "kind": "recruiter",
      "title": "",
      "linkedin_url": "",
      "email": "",
      "confidence": "medium",
      "evidence": [""]
    }
  ]
}

kind must be recruiter, hiring_manager, or unknown.
confidence must be high, medium, or low.

The input JSON follows on stdin after a single line containing only: ---ROLE-CONTACTS-EXTRACT---"""

AgentRunner = Callable[..., str]


def parse_search_queries(response_text: str) -> list[str]:
    """Parse query strings from a model JSON object."""
    parsed = extract_json_object(response_text)
    raw_queries = parsed.get("queries")
    queries: list[str] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            text = str(item or "").strip()
            if text:
                queries.append(text)
    return queries[:5]


def parse_extracted_candidates(response_text: str) -> list[ContactCandidate]:
    """Parse contact candidates from a model JSON object."""
    parsed = extract_json_object(response_text)
    raw_candidates = parsed.get("candidates")
    if not isinstance(raw_candidates, list):
        return []
    candidates: list[ContactCandidate] = []
    for item in raw_candidates:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        evidence_raw = item.get("evidence")
        evidence: list[str] = []
        if isinstance(evidence_raw, list):
            for part in evidence_raw:
                text = str(part or "").strip()
                if text:
                    evidence.append(text)
        elif isinstance(evidence_raw, str) and evidence_raw.strip():
            evidence.append(evidence_raw.strip())
        candidates.append(
            ContactCandidate(
                name=name,
                kind=normalize_contact_kind(item.get("kind")),
                title=str(item.get("title") or "").strip(),
                linkedin_url=str(item.get("linkedin_url") or "").strip(),
                email=str(item.get("email") or "").strip(),
                confidence=normalize_confidence(item.get("confidence")),
                evidence=tuple(evidence),
                source="web_search",
            )
        )
        if len(candidates) >= 5:
            break
    return candidates


def plan_search_queries(
    identity: JobIdentity,
    *,
    agent_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
    run_agent: AgentRunner = run_agent_cli_headless,
) -> list[str]:
    """Ask the model for a short list of public search queries."""
    payload = {
        "company_name": identity.company_name,
        "job_title": identity.job_title,
        "location": identity.location,
        "department": identity.department,
        "requisition_id": identity.requisition_id,
        "job_url": identity.job_url,
    }
    stdin_payload = "---ROLE-CONTACTS-QUERIES---\n" + json.dumps(payload, ensure_ascii=False)
    response_text = run_agent(
        agent_binary=agent_binary,
        prompt=_QUERY_PROMPT,
        stdin_payload=stdin_payload,
        model=model,
        debug=debug,
    )
    return parse_search_queries(response_text)


def extract_contacts_from_hits(
    *,
    identity: JobIdentity,
    posting_excerpt: str,
    posting_contacts: Sequence[ContactCandidate],
    hits: Sequence[SearchHit],
    agent_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
    run_agent: AgentRunner = run_agent_cli_headless,
) -> list[ContactCandidate]:
    """Ask the model to name contacts using only provided snippets."""
    hit_payload: list[dict[str, Any]] = [
        {"title": hit.title, "url": hit.url, "snippet": hit.snippet, "source": hit.source}
        for hit in hits[:24]
    ]
    already_found = [candidate.to_mapping() for candidate in posting_contacts]
    payload = {
        "job": identity.to_mapping(),
        "posting_excerpt": posting_excerpt[:4_000],
        "already_found_on_posting": already_found,
        "search_hits": hit_payload,
    }
    stdin_payload = "---ROLE-CONTACTS-EXTRACT---\n" + json.dumps(payload, ensure_ascii=False)
    response_text = run_agent(
        agent_binary=agent_binary,
        prompt=_EXTRACT_PROMPT,
        stdin_payload=stdin_payload,
        model=model,
        debug=debug,
    )
    return parse_extracted_candidates(response_text)
