"""Human-readable company labels derived from ATS board identifiers."""

from __future__ import annotations

import re
from typing import Any, Mapping


def humanize_board_identifier(identifier: str) -> str:
    """
    Produce a short display label from a board token or careers slug (best-effort, not canonical branding).

    Splits on ``-``, ``_``, and ``.``, then applies simple title-casing per segment.
    """
    raw = str(identifier).strip()
    if not raw:
        return ""
    normalized = raw.replace("_", "-").replace(".", "-")
    segments = [segment for segment in re.split(r"-+", normalized) if segment]
    if not segments:
        return raw[:1].upper() + raw[1:] if raw else ""
    pieces: list[str] = []
    for segment in segments:
        lowered = segment.lower()
        pieces.append(lowered[:1].upper() + lowered[1:] if lowered else "")
    return " ".join(pieces)


def greenhouse_company_display(job: Mapping[str, Any], *, board_token: str) -> str:
    name = str(job.get("company_name") or "").strip()
    if name:
        return name
    return humanize_board_identifier(board_token)
