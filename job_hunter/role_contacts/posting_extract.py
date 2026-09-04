"""Pull named contacts from posting HTML and ATS JSON without a model."""

from __future__ import annotations

import html as html_module
import re
import urllib.parse
from typing import Any, Mapping

from job_hunter.job_filtering.job_page_text import html_to_text
from job_hunter.role_contacts.models import ContactCandidate, ContactKind, normalize_contact_kind

_MAILTO_PATTERN = re.compile(r"mailto:([^?\"'\s>]+)", flags=re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", flags=re.IGNORECASE)
_LABEL_NAME_PATTERN = re.compile(
    r"(?:Recruiter|Hiring[ \t]+Manager|Posted[ \t]+by)\s*[:\-]\s*"
    r"([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,3})",
)
_SKIPPED_EMAIL_LOCAL_PARTS = frozenset(
    {
        "privacy",
        "noreply",
        "no-reply",
        "jobs",
        "careers",
        "support",
        "info",
        "legal",
        "accessibleinterviewing",
        "accommodations",
        "help",
    }
)
_GENERIC_EMAIL_DOMAINS = frozenset({"greenhouse.io", "us-greenhouse-mail.io"})


def _skipped_email(address: str) -> bool:
    lowered = address.strip().lower()
    local, _, domain = lowered.partition("@")
    if not local or not domain:
        return True
    if local in _SKIPPED_EMAIL_LOCAL_PARTS:
        return True
    if domain in _GENERIC_EMAIL_DOMAINS or domain.endswith(".greenhouse.io"):
        return True
    return False


def _candidate(
    *,
    name: str,
    kind: ContactKind,
    email: str = "",
    title: str = "",
    evidence: str,
) -> ContactCandidate:
    return ContactCandidate(
        name=name.strip(),
        kind=normalize_contact_kind(kind),
        title=title.strip(),
        linkedin_url="",
        email=email.strip(),
        confidence="high",
        evidence=(evidence,),
        source="job_posting",
    )


def extract_contacts_from_text(text: str) -> list[ContactCandidate]:
    """Find mailto addresses and labeled names in visible posting text or HTML."""
    if not text.strip():
        return []
    decoded = html_module.unescape(text)
    visible = html_to_text(decoded) if "<" in decoded else decoded
    candidates: list[ContactCandidate] = []
    seen: set[str] = set()

    for match in _MAILTO_PATTERN.finditer(decoded):
        address = decode_mailto_address(match.group(1))
        if _skipped_email(address) or address.lower() in seen:
            continue
        seen.add(address.lower())
        local = address.split("@", 1)[0]
        name = local.replace(".", " ").replace("_", " ").replace("-", " ").title()
        candidates.append(
            _candidate(
                name=name,
                kind="recruiter",
                email=address,
                evidence=f"mailto:{address} on the job posting",
            )
        )

    for match in _EMAIL_PATTERN.finditer(visible):
        address = match.group(0)
        if _skipped_email(address) or address.lower() in seen:
            continue
        seen.add(address.lower())
        local = address.split("@", 1)[0]
        name = local.replace(".", " ").replace("_", " ").title()
        candidates.append(
            _candidate(
                name=name,
                kind="unknown",
                email=address,
                evidence=f"email {address} in the job posting",
            )
        )

    for match in _LABEL_NAME_PATTERN.finditer(visible):
        label_start = visible[max(0, match.start() - 20) : match.start()].lower()
        name = match.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        kind = "hiring_manager" if "hiring" in match.group(0).lower() else "recruiter"
        if "posted" in match.group(0).lower() and "recruiter" not in label_start:
            kind = "unknown"
        candidates.append(
            _candidate(
                name=name,
                kind=kind,
                evidence=f"labeled on the posting: {match.group(0).strip()}",
            )
        )
    return candidates


def decode_mailto_address(raw: str) -> str:
    """Decode a mailto target."""
    return urllib.parse.unquote(raw).strip().rstrip(".")


def extract_contacts_from_ats_payload(payload: Mapping[str, Any] | None) -> list[ContactCandidate]:
    """Read recruiter-like fields if a public ATS JSON payload includes them."""
    if not isinstance(payload, Mapping):
        return []
    candidates: list[ContactCandidate] = []
    for key in ("recruiter", "hiring_manager", "hiringManager"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            name = str(value.get("name") or value.get("full_name") or "").strip()
            email = str(value.get("email") or "").strip()
            if name or email:
                kind = "hiring_manager" if "manager" in key.lower() else "recruiter"
                candidates.append(
                    _candidate(
                        name=name or email.split("@", 1)[0],
                        kind=kind,
                        email=email,
                        title=str(value.get("title") or "").strip(),
                        evidence=f"ATS JSON field {key}",
                    )
                )
        elif isinstance(value, str) and value.strip():
            kind = "hiring_manager" if "manager" in key.lower() else "recruiter"
            candidates.append(
                _candidate(
                    name=value.strip(),
                    kind=kind,
                    evidence=f"ATS JSON field {key}",
                )
            )
    content = payload.get("content") or payload.get("descriptionPlain") or payload.get("description")
    if isinstance(content, str):
        candidates.extend(extract_contacts_from_text(content))
    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    unique: list[ContactCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.email.lower() or candidate.name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique
