"""Typed records for role-contact lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ContactKind = Literal["recruiter", "hiring_manager", "unknown"]
ConfidenceLevel = Literal["high", "medium", "low"]

_VALID_KINDS = frozenset({"recruiter", "hiring_manager", "unknown"})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


@dataclass(frozen=True)
class ContactCandidate:
    """One possible recruiter or hiring manager for a role."""

    name: str
    kind: ContactKind
    title: str
    linkedin_url: str
    email: str
    confidence: ConfidenceLevel
    evidence: tuple[str, ...]
    source: str

    def to_mapping(self) -> dict[str, Any]:
        """Serialize for YAML."""
        return {
            "name": self.name,
            "kind": self.kind,
            "title": self.title,
            "linkedin_url": self.linkedin_url,
            "email": self.email,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "source": self.source,
        }


@dataclass(frozen=True)
class JobIdentity:
    """Facts extracted from a posting URL and public ATS JSON."""

    job_url: str
    company_name: str = ""
    job_title: str = ""
    location: str = ""
    department: str = ""
    requisition_id: str = ""
    provider_kind: str = ""
    provider_job_id: str = ""
    provider_board_token: str = ""

    def to_mapping(self) -> dict[str, Any]:
        """Serialize identity fields used in the contacts report."""
        return {
            "job_url": self.job_url,
            "company_name": self.company_name,
            "job_title": self.job_title,
            "location": self.location,
            "department": self.department,
            "requisition_id": self.requisition_id,
            "provider_kind": self.provider_kind,
            "provider_job_id": self.provider_job_id,
            "provider_board_token": self.provider_board_token,
        }


@dataclass
class SearchHit:
    """One public web or LinkedIn search result."""

    title: str
    url: str
    snippet: str
    source: str


@dataclass
class RoleContactReport:
    """Lookup result written next to a tailored CV."""

    job_url: str
    company_name: str
    job_title: str
    looked_up_at: str
    ai_used: bool
    candidates: list[ContactCandidate] = field(default_factory=list)

    def to_mapping(self) -> dict[str, Any]:
        """Serialize for YAML."""
        return {
            "job_url": self.job_url,
            "company_name": self.company_name,
            "job_title": self.job_title,
            "looked_up_at": self.looked_up_at,
            "ai_used": self.ai_used,
            "candidates": [candidate.to_mapping() for candidate in self.candidates],
        }


def normalize_contact_kind(value: object) -> ContactKind:
    """Coerce model output into a known contact kind."""
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in {"hiring-manager", "hiringmanager", "manager"}:
        return "hiring_manager"
    if text in _VALID_KINDS:
        return text  # type: ignore[return-value]
    return "unknown"


def normalize_confidence(value: object) -> ConfidenceLevel:
    """Coerce model output into a known confidence bucket."""
    text = str(value or "").strip().lower()
    if text in _VALID_CONFIDENCE:
        return text  # type: ignore[return-value]
    return "low"
