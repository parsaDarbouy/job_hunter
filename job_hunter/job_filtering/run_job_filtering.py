"""Run date-scoped AI filtering for exported jobs."""

from __future__ import annotations

import datetime
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, TextIO

import yaml

from job_hunter.job_filtering.csv_io import FilteredJobsCsvStreamWriter, read_jobs_csv_rows, write_jobs_csv_rows
from job_hunter.agent_cli import DEFAULT_AGENT_BINARY
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

_logger = logging.getLogger(__name__)


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


def _format_progress_line(
    *,
    current: int,
    total: int,
    accepted: int,
    bar_width: int = 24,
) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = min(bar_width, int(bar_width * current / total))
    bar = "#" * filled + "-" * (bar_width - filled)
    return f"[{bar}] {current}/{total} processed | {accepted} accepted"


def run_job_filtering(
    *,
    target_date: datetime.date,
    jobs_csv_path: Path | None = None,
    resume_path: Path | None = None,
    position_path: Path | None = None,
    output_path: Path | None = None,
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    max_description_chars: int = 30_000,
    debug: bool = False,
    enable_progress: bool = True,
    progress_stream: TextIO | None = None,
    description_fetcher: Callable[[str], str] = fetch_job_description,
    job_assessor: Callable[..., GeminiJobAssessment] = assess_job_with_gemini_cli,
) -> Path:
    """
    Filter jobs added on ``target_date`` and write accepted rows to a dated CSV.

    Missing ``job_description`` values are fetched from each job URL before Gemini scoring and
    persisted back into the input jobs CSV. Accepted rows are appended to the filtered CSV as
    soon as each job passes, with a flush after each row, so partial results remain if the
    process stops unexpectedly.

    Logs go to the configured ``logging`` handlers (configure ``job_hunter`` or root for CLI).
    When ``enable_progress`` is True, a single-line progress indicator is written to
    ``progress_stream`` (default stderr), cleared with a newline when the run finishes.
    """
    run_id = uuid.uuid4().hex[:10]
    stream = progress_stream if progress_stream is not None else sys.stderr
    started = time.monotonic()

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

    total_candidates = len(candidates)
    _logger.info(
        "job_filtering.start run_id=%s target_date=%s candidates=%s csv_rows=%s "
        "minimum_alignment_pct=%s gemini_model=%s jobs_csv=%s output_csv=%s",
        run_id,
        target_date.isoformat(),
        total_candidates,
        len(rows),
        minimum_alignment_percentage,
        model,
        jobs_path,
        filtered_output_path,
    )

    jobs_csv_changed = column_was_added
    accepted_count = 0
    fetch_failures = 0

    filtered_writer = FilteredJobsCsvStreamWriter(filtered_output_path, fieldnames)
    filtered_writer.open()
    try:
        def _write_progress(processed: int, accepted: int) -> None:
            if not enable_progress:
                return
            line = f"jobs:filter {run_id} {_format_progress_line(current=processed, total=total_candidates, accepted=accepted)}"
            stream.write(f"\r{line}")
            stream.flush()

        if enable_progress and total_candidates > 0:
            _write_progress(0, 0)

        for index, row in enumerate(candidates, start=1):
            description = row.get(JOB_DESCRIPTION_COLUMN, "").strip()
            if not description:
                try:
                    fetched_description = description_fetcher(row.get("url", ""))
                except Exception as exc:  # pragma: no cover - defensive around network failures
                    fetched_description = ""
                    fetch_failures += 1
                    _logger.warning(
                        "job_filtering.description_fetch_failed run_id=%s url=%s error=%s",
                        run_id,
                        row.get("url", ""),
                        exc,
                    )
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
                _logger.debug(
                    "job_filtering.assessment run_id=%s job_title=%r alignment_pct=%s passes=%s reason=%r",
                    run_id,
                    row.get("job_title", ""),
                    assessment.alignment_percentage,
                    assessment.passes,
                    assessment.reason,
                )
            if assessment.passes and assessment.alignment_percentage >= minimum_alignment_percentage:
                filtered_writer.write_accepted_row(row)
                accepted_count += 1

            _write_progress(index, accepted_count)

        if enable_progress and total_candidates > 0:
            stream.write("\n")
            stream.flush()

        if jobs_csv_changed:
            write_jobs_csv_rows(jobs_path, fieldnames, rows)
    finally:
        filtered_writer.close()

    elapsed_ms = int((time.monotonic() - started) * 1000)
    _logger.info(
        "job_filtering.complete run_id=%s duration_ms=%s accepted=%s rejected=%s "
        "fetch_failures=%s jobs_csv_updated=%s output_csv=%s",
        run_id,
        elapsed_ms,
        accepted_count,
        total_candidates - accepted_count,
        fetch_failures,
        jobs_csv_changed,
        filtered_output_path,
    )
    return filtered_output_path
