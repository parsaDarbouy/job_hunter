"""Deterministic normalization: dates, durations, deduplication, stable ordering."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

_SKILL_LIST_KEYS = ("languages", "frameworks", "cloud", "tools", "other")


def _parse_partial_date(
    label: str,
    *,
    is_end: bool,
    reference_now: datetime | None = None,
) -> tuple[int, int] | None:
    raw = (label or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower in {"present", "current", "now", "today"}:
        anchor = reference_now or datetime.now(timezone.utc)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        return (anchor.year, anchor.month)

    default_day = 28 if is_end else 1
    try:
        dt = date_parser.parse(
            raw,
            default=datetime(2001, 1, default_day, tzinfo=timezone.utc),
            fuzzy=False,
        )
        return (dt.year, dt.month)
    except (ValueError, TypeError, OverflowError):
        year_only = re.fullmatch(r"(\d{4})", raw)
        if year_only:
            year = int(year_only.group(1))
            return (year, 12 if is_end else 1)
    return None


def _months_span(start: tuple[int, int] | None, end: tuple[int, int] | None) -> int:
    if start is None or end is None:
        return 0
    y1, m1 = start
    y2, m2 = end
    span = (y2 - y1) * 12 + (m2 - m1) + 1
    return max(span, 0)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _skill_sort_key(token: str) -> tuple[str, str]:
    return (token.lower(), token)


def _dedupe_skills_cross_category(skills: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Deduplicate case-insensitively across skill buckets.

    Higher-priority buckets (languages first, then frameworks, cloud, tools, other)
    win when the same token appears in multiple lists.
    """
    global_seen: set[str] = set()
    by_category: dict[str, list[str]] = {k: [] for k in _SKILL_LIST_KEYS}

    for category in _SKILL_LIST_KEYS:
        for token in skills.get(category, []) or []:
            if not isinstance(token, str):
                continue
            cleaned = token.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in global_seen:
                continue
            global_seen.add(key)
            by_category[category].append(cleaned)

    for category in _SKILL_LIST_KEYS:
        by_category[category] = sorted(by_category[category], key=_skill_sort_key)
    return by_category


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = _coerce_str(item)
        if s:
            out.append(s)
    return out


def _coerce_float_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return 0.0


def normalize_extracted_resume(
    extracted: dict[str, Any],
    *,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    """
    Merge LLM JSON into the canonical resume document shape with deterministic lists.

    Computes duration_months from start/end dates when parsable; otherwise 0.
    """
    now = reference_time or datetime.now(timezone.utc)
    profile_in = extracted.get("profile") if isinstance(extracted.get("profile"), dict) else {}
    summary_in = extracted.get("summary") if isinstance(extracted.get("summary"), dict) else {}
    skills_in = extracted.get("skills") if isinstance(extracted.get("skills"), dict) else {}

    skills_raw = {
        key: _coerce_str_list(skills_in.get(key)) for key in _SKILL_LIST_KEYS
    }
    skills_out = _dedupe_skills_cross_category(skills_raw)

    experience_out: list[dict[str, Any]] = []
    for row in extracted.get("experience") or []:
        if not isinstance(row, dict):
            continue
        start_label = _coerce_str(row.get("start_date"))
        end_label = _coerce_str(row.get("end_date"))
        start_key = _parse_partial_date(start_label, is_end=False, reference_now=now)
        end_key = _parse_partial_date(end_label, is_end=True, reference_now=now)
        if end_key is None and end_label.strip():
            end_key = _parse_partial_date(end_label, is_end=True, reference_now=now)
        if end_key is None and (
            not end_label.strip() or end_label.strip().lower() in {"present", "current", "now", "today"}
        ):
            end_key = (now.year, now.month)

        duration_months = _months_span(start_key, end_key)
        highlights = _dedupe_preserve_order(_coerce_str_list(row.get("highlights")))

        experience_out.append(
            {
                "company": _coerce_str(row.get("company")),
                "title": _normalize_title(_coerce_str(row.get("title"))),
                "start_date": start_label,
                "end_date": end_label,
                "duration_months": duration_months,
                "highlights": highlights,
            }
        )

    experience_out.sort(
        key=lambda row: (
            _parse_partial_date(str(row.get("start_date")), is_end=False, reference_now=now) or (0, 0),
            row.get("company", "").lower(),
            row.get("title", "").lower(),
        ),
        reverse=True,
    )

    education_out: list[dict[str, Any]] = []
    for row in extracted.get("education") or []:
        if not isinstance(row, dict):
            continue
        education_out.append(
            {
                "institution": _coerce_str(row.get("institution")),
                "degree": _coerce_str(row.get("degree")),
                "field": _coerce_str(row.get("field")),
                "start_date": _coerce_str(row.get("start_date")),
                "end_date": _coerce_str(row.get("end_date")),
            }
        )
    education_out.sort(
        key=lambda row: (
            _parse_partial_date(str(row.get("start_date")), is_end=False, reference_now=now) or (0, 0),
            row.get("institution", "").lower(),
        ),
        reverse=True,
    )

    accomplishments_out: list[dict[str, str]] = []
    seen_accomplishment_titles: set[str] = set()
    for row in extracted.get("accomplishments") or []:
        if not isinstance(row, dict):
            continue
        title = _coerce_str(row.get("title"))
        detail = _coerce_str(row.get("detail"))
        date_label = _coerce_str(row.get("date"))
        if not title and not detail:
            continue
        dedupe_key = title.lower() or detail.lower()
        if dedupe_key in seen_accomplishment_titles:
            continue
        seen_accomplishment_titles.add(dedupe_key)
        accomplishments_out.append(
            {
                "title": title,
                "detail": detail,
                "date": date_label,
            }
        )
    accomplishments_out.sort(
        key=lambda row: (
            _parse_partial_date(str(row.get("date")), is_end=True, reference_now=now) or (0, 0),
            row.get("title", "").lower(),
        ),
        reverse=True,
    )

    years = summary_in.get("total_years_experience")
    if years is None or years == "":
        total_years_numeric: int | float = 0
    else:
        total_years_numeric = _coerce_float_or_zero(years)

    domains = sorted(
        {d.strip().lower() for d in _coerce_str_list(summary_in.get("domains")) if d.strip()},
        key=lambda s: (s, s),
    )

    if isinstance(total_years_numeric, float) and total_years_numeric.is_integer():
        total_years_out: int | float = int(total_years_numeric)
    else:
        total_years_out = total_years_numeric

    return {
        "profile": {
            "name": _coerce_str(profile_in.get("name")),
            "email": _coerce_str(profile_in.get("email")),
            "phone": _coerce_str(profile_in.get("phone")),
            "location": _coerce_str(profile_in.get("location")),
            "links": {
                "github": _coerce_str(profile_in.get("github")),
                "linkedin": _coerce_str(profile_in.get("linkedin")),
            },
        },
        "summary": {
            "total_years_experience": total_years_out,
            "domains": domains,
        },
        "skills": skills_out,
        "experience": experience_out,
        "education": education_out,
        "accomplishments": accomplishments_out,
    }


def _normalize_title(title: str) -> str:
    collapsed = re.sub(r"\s+", " ", title.strip())
    return collapsed
