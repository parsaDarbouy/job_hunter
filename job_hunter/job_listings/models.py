"""Shared datatypes for listing export."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    """
    One normalized job row for filtering and spreadsheet export.

    ``company_name`` is the Greenhouse ``company_name`` when available; otherwise a display
    label derived from board token or organization/account slug.
    """

    url: str
    title: str
    location: str
    source_id: str
    provider_kind: str
    company_name: str = ""
