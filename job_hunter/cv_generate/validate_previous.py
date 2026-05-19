"""Validate sections/previous.tex uses the compact no-bullet template format."""

from __future__ import annotations

import re
from typing import Mapping

_FORBIDDEN_IN_PREVIOUS = (
    (r"\\begin\{zitemize\}", "zitemize environment"),
    (r"\\item\b", "\\item bullets"),
    (r"\\subsection\b", "\\subsection headings"),
)


def validate_previous_experience_format(files: Mapping[str, str]) -> None:
    """
    Ensure previous experience matches the template (title/company/date lines only).

    Raises ValueError when bullets or subsection blocks are present.
    """
    content = files.get("sections/previous.tex", "")
    if not content.strip():
        return

    violations: list[str] = []
    for pattern, label in _FORBIDDEN_IN_PREVIOUS:
        if re.search(pattern, content):
            violations.append(label)

    if violations:
        joined = ", ".join(violations)
        raise ValueError(
            "sections/previous.tex must use compact \\skills/\\textit lines only (no bullets): "
            f"found {joined}"
        )
