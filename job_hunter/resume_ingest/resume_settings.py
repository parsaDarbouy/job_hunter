"""CV-generation settings stored at the top of resume.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

RESUME_MAX_PAGES_KEY = "resume_max_pages"
TARGET_JOB_URL_KEY = "target_job_url"
CV_LAYOUT_KEY = "cv_layout"
CV_GENERATION_KEYS = (RESUME_MAX_PAGES_KEY, TARGET_JOB_URL_KEY, CV_LAYOUT_KEY)


def merge_cv_generation_settings(
    document: Mapping[str, Any],
    *,
    existing_output_path: Path | None,
) -> dict[str, Any]:
    """
    Preserve ``resume_max_pages``, ``target_job_url``, and ``cv_layout`` from an existing file.

    New keys are inserted at the top of the document when present.
    """
    prefix: dict[str, Any] = {}
    if existing_output_path is not None and existing_output_path.is_file():
        existing = yaml.safe_load(existing_output_path.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            for key in CV_GENERATION_KEYS:
                if key in existing:
                    prefix[key] = existing[key]
    merged: dict[str, Any] = {**prefix, **dict(document)}
    return merged


def parse_resume_max_pages(resume_document: Mapping[str, Any]) -> int:
    """Return a positive page limit from resume YAML."""
    raw = resume_document.get(RESUME_MAX_PAGES_KEY)
    try:
        pages = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{RESUME_MAX_PAGES_KEY} must be a positive integer in resume.yaml") from None
    if pages < 1:
        raise ValueError(f"{RESUME_MAX_PAGES_KEY} must be at least 1")
    return pages


def parse_target_job_url(resume_document: Mapping[str, Any]) -> str:
    """Return a non-empty job posting URL from resume YAML."""
    url = str(resume_document.get(TARGET_JOB_URL_KEY) or "").strip()
    if not url:
        raise ValueError(f"{TARGET_JOB_URL_KEY} must be set in resume.yaml")
    return url
