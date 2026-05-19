"""Fetch and persist job posting text for CV tailoring."""

from __future__ import annotations

from pathlib import Path

from job_hunter.job_filtering.job_page_text import fetch_job_description


def fetch_and_save_job_description(*, job_url: str, output_path: Path) -> str:
    """Fetch a job URL, write plain text to ``output_path``, and return the text."""
    description = fetch_job_description(job_url)
    if not description.strip():
        raise RuntimeError(f"Job description was empty after fetching {job_url}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(description, encoding="utf-8")
    return description
