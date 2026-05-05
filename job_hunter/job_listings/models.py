"""Shared datatypes for listing export."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    """One normalized job row for filtering and spreadsheet export (optionally carries HTML JD text)."""

    url: str
    title: str
    location: str
    source_id: str
    provider_kind: str
    description_html: str = ""
