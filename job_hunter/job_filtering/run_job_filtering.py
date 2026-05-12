"""Run date-scoped AI filtering for exported jobs."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Callable

import yaml

from job_hunter.job_filtering.csv_io import read_jobs_csv_rows, write_jobs_csv_rows
from job_hunter.job_filtering.gemini_filter import GeminiJobAssessment, assess_job_with_gemini_cli
from job_hunter.job_filtering.job_page_text import fetch_job_description
from job_hunter.job_listings.write_jobs_csv import ADDED_TO_LIST_DATE_COLUMN, JOB_DESCRIPTION_COLUMN
from job_hunter.paths import (
    default_filtered_jobs_csv_path,
    default_jobs_export_csv_path,
    default_position_yaml_path,
    default_resume_yaml_path,
)


_DEFAULT_MINIMUM_ALIGNMENT_PERCENTAGE = 70


def _read_text(path: Path) -> str:
    return path.expanduser().resolve().read_text(encoding="utf-8")


def _load_minimum_alignment_percentage(position_yaml_text: str) -> int:
    loaded = yaml.safe_load(position_yaml_text) or {}
    if not isinstance(loaded, dict):
        return _DEFAULT_MINIMUM_ALIGNMENT_PERCENTAGE
    ai_filtering = loaded.get("ai_filtering") or {}
    if not isinstance(ai_filtering, dict):
        return _DEFAULT_MINIMUM_ALIGNMENT_PERCENTAGE
    value = ai_filtering.get("minimum_alignment_percentage", _DEFAULT_MINIMUM_ALIGNMENT_PERCENTAGE)
    try:
        percentage = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MINIMUM_ALIGNMENT_PERCENTAGE
    return max(0, min(100, percentage))


def _candidate_rows(rows: list[dict[str, str]], target_date: datetime.date) -> list[dict[str, str]]:
    target_iso = target_date.isoformat()
    return [row for row in rows if row.get(ADDED_TO_LIST_DATE_COLUMN, "").strip() == target_iso]


def run_job_filtering(
    *,
    target_date: datetime.date,
    jobs_csv_path: Path | None = None,
    resume_path: Path | None = None,
    position_path: Path | None = None,
    output_path: Path | None = None,
    gemini_binary: str = "gemini",
    model: str = "flash",
    max_description_chars: int = 30_000,
    debug: bool = False,
    description_fetcher: Callable[[str], str] = fetch_job_description,
    job_assessor: Callable[..., GeminiJobAssessment] = assess_job_with_gemini_cli,
) -> Path:
    """
    Filter jobs added on ``target_date`` and write accepted rows to a dated CSV.

    Missing ``job_description`` values are fetched from each job URL before Gemini scoring and
    persisted back into the input jobs CSV.
    """
    jobs_path = (jobs_csv_path or default_jobs_export_csv_path()).expanduser().resolve()
    resume_yaml_path = (resume_path or default_resume_yaml_path()).expanduser().resolve()
    position_yaml_path = (position_path or default_position_yaml_path()).expanduser().resolve()
    filtered_output_path = (
        output_path or default_filtered_jobs_csv_path(target_date)
    ).expanduser().resolve()

    fieldnames, rows, column_was_added = read_jobs_csv_rows(jobs_path)
    candidates = _candidate_rows(rows, target_date)
    resume_yaml_text = _read_text(resume_yaml_path)
    position_yaml_text = _read_text(position_yaml_path)
    minimum_alignment_percentage = _load_minimum_alignment_percentage(position_yaml_text)

    jobs_csv_changed = column_was_added
    accepted_rows: list[dict[str, str]] = []

    for row in candidates:
        description = row.get(JOB_DESCRIPTION_COLUMN, "").strip()
        if not description:
            try:
                fetched_description = description_fetcher(row.get("url", ""))
            except Exception as exc:  # pragma: no cover - defensive around network failures
                fetched_description = ""
                if debug:
                    print(f"[debug] failed to fetch {row.get('url', '')}: {exc}", file=sys.stderr)
            if fetched_description:
                row[JOB_DESCRIPTION_COLUMN] = fetched_description
                jobs_csv_changed = True

        assessment = job_assessor(
            row,
            resume_yaml_text=resume_yaml_text,
            position_yaml_text=position_yaml_text,
            minimum_alignment_percentage=minimum_alignment_percentage,
            gemini_binary=gemini_binary,
            model=model,
            max_description_chars=max_description_chars,
            debug=debug,
        )
        if debug:
            print(
                "[debug]",
                row.get("job_title", ""),
                assessment.alignment_percentage,
                assessment.passes,
                assessment.reason,
                file=sys.stderr,
            )
        if assessment.passes and assessment.alignment_percentage >= minimum_alignment_percentage:
            accepted_rows.append(row)

    if jobs_csv_changed:
        write_jobs_csv_rows(jobs_path, fieldnames, rows)

    write_jobs_csv_rows(filtered_output_path, fieldnames, accepted_rows)
    return filtered_output_path
