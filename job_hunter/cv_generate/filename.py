"""Safe PDF filenames from company and position titles."""

from __future__ import annotations

import re


def slugify_filename_part(text: str) -> str:
    """Convert a label to a filesystem-safe token."""
    collapsed = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    collapsed = re.sub(r"[-\s]+", "_", collapsed.strip())
    return collapsed.strip("_") or "unknown"


def build_cv_pdf_filename(*, company_name: str, position_title: str) -> str:
    """Return ``{company}_{position}.pdf`` with sanitized components."""
    company_part = slugify_filename_part(company_name)
    position_part = slugify_filename_part(position_title)
    return f"{company_part}_{position_part}.pdf"
