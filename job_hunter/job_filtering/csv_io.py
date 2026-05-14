"""CSV helpers for AI job filtering."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

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


class FilteredJobsCsvStreamWriter:
    """
    Write a filtered-jobs CSV incrementally: header first, then one data row at a time.

    Flushes the underlying file after each row so accepted rows survive process interruption.
    """

    def __init__(self, csv_path: Path, fieldnames: list[str]) -> None:
        self._csv_path = csv_path
        self._fieldnames = fieldnames
        self._handle: TextIO | None = None
        self._writer: csv.DictWriter | None = None

    def open(self) -> None:
        """Truncate (or create) the file and write the CSV header."""
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._csv_path.open("w", encoding="utf-8", newline="")
        self._handle = handle
        self._writer = csv.DictWriter(handle, fieldnames=self._fieldnames, extrasaction="ignore")
        self._writer.writeheader()
        handle.flush()

    def write_accepted_row(self, row: Mapping[str, str]) -> None:
        """Append one accepted row and flush to disk."""
        if self._writer is None or self._handle is None:
            raise RuntimeError("FilteredJobsCsvStreamWriter.open must be called before write_accepted_row")
        self._writer.writerow({name: row.get(name, "") for name in self._fieldnames})
        self._handle.flush()

    def close(self) -> None:
        """Close the output file."""
        if self._handle is not None:
            self._handle.close()
        self._handle = None
        self._writer = None
