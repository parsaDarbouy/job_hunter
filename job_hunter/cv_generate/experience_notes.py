"""Extract per-role context notes from resume.yaml for CV tailoring."""

from __future__ import annotations

from typing import Any, Mapping


def _coerce_note(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _note_from_orphan_entry(entry: Mapping[str, Any]) -> str:
    for key, value in entry.items():
        if isinstance(key, str) and key.strip().lower() == "note":
            return _coerce_note(value)
    return ""


def collect_experience_notes(resume_document: Mapping[str, Any]) -> list[dict[str, str]]:
    """
    Return structured note hints for experience entries that include a ``note``.

    Supports ``note`` on the same mapping as ``company`` / ``title``, and legacy
    list items shaped like ``- Note: ...`` immediately after a role (no company).
    """
    experience = resume_document.get("experience")
    if not isinstance(experience, list):
        return []

    hints: list[dict[str, str]] = []
    last_company = ""
    last_title = ""

    for entry in experience:
        if not isinstance(entry, dict):
            continue

        company = _coerce_note(entry.get("company"))
        title = _coerce_note(entry.get("title"))
        inline_note = _coerce_note(entry.get("note"))

        if company:
            last_company = company
            last_title = title
            if inline_note:
                hints.append({"company": company, "title": title, "note": inline_note})
            continue

        orphan_note = _note_from_orphan_entry(entry)
        if orphan_note and last_company:
            hints.append({"company": last_company, "title": last_title, "note": orphan_note})

    return hints
