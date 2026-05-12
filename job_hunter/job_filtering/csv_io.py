"""CSV helpers for AI job filtering."""

from __future__ import annotations

import csv
from pathlib import Path

from job_hunter.job_listings.write_jobs_csv import (
    ADDED_TO_LIST_DATE_COLUMN,
    JOB_DESCRIPTION_COLUMN,
    JOBS_EXPORT_FIELDNAMES,
)


def read_jobs_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]], bool]:
    """
    Read exported job rows and ensure each row has a ``job_description`` key.

    Returns ``(fieldnames, rows, column_was_added)``. Existing unknown columns are preserved.
    """
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: str(value or "") for key, value in row.items() if key is not None} for row in reader]

    if not fieldnames:
        fieldnames = list(JOBS_EXPORT_FIELDNAMES)

    column_was_added = JOB_DESCRIPTION_COLUMN not in fieldnames
    if column_was_added:
        fieldnames.append(JOB_DESCRIPTION_COLUMN)

    for row in rows:
        row.setdefault(JOB_DESCRIPTION_COLUMN, "")
        row.setdefault(ADDED_TO_LIST_DATE_COLUMN, "")

    return fieldnames, rows, column_was_added


def write_jobs_csv_rows(csv_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write CSV rows using the supplied field order."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
