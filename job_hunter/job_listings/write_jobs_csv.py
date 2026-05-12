"""Write matched jobs to a UTF-8 CSV file."""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any, Mapping

from job_hunter.job_listings.models import JobPosting


ADDED_TO_LIST_DATE_COLUMN = "added_to_list_date"
JOB_DESCRIPTION_COLUMN = "job_description"


JOBS_EXPORT_FIELDNAMES = [
    "url",
    "job_title",
    "listing_posted_date",
    ADDED_TO_LIST_DATE_COLUMN,
    "location",
    "company_name",
    JOB_DESCRIPTION_COLUMN,
]


def _canonical_row_from_reader(row: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in JOBS_EXPORT_FIELDNAMES:
        out[name] = str(row.get(name) or "").strip()
    return out


def _load_existing_export_rows(csv_path: Path) -> list[dict[str, str]]:
    """
    Deserialize prior export rows deduped by ``url``, preserving file order.

    Rows without a usable ``url`` are skipped.
    Unknown / legacy headers are tolerated; absent columns yield empty strings.
    """
    if not csv_path.is_file():
        return []
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    try:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                if not isinstance(raw, dict):
                    continue
                canonical = _canonical_row_from_reader(raw)
                url_key = canonical["url"].strip()
                if not url_key or url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                rows.append(canonical)
    except OSError:
        return []
    return rows


def _backfill_missing_added_dates(rows: list[dict[str, str]], run_iso: str) -> None:
    """Fill empty ``added_to_list_date`` cells (e.g. legacy CSV) with the current run day."""
    for row in rows:
        if not str(row.get(ADDED_TO_LIST_DATE_COLUMN) or "").strip():
            row[ADDED_TO_LIST_DATE_COLUMN] = run_iso


def _posting_to_row(posting: JobPosting, added_iso: str) -> dict[str, str]:
    return {
        "url": posting.url.strip(),
        "job_title": posting.title,
        "listing_posted_date": posting.listing_posted_date,
        ADDED_TO_LIST_DATE_COLUMN: added_iso,
        "location": posting.location,
        "company_name": posting.company_name,
        JOB_DESCRIPTION_COLUMN: "",
    }


def write_jobs_csv(
    postings: list[JobPosting],
    output_path: Path,
    *,
    list_addition_run_date: datetime.date | None = None,
) -> None:
    """
    Persist ``postings`` with columns ``url``, ``job_title``, ``listing_posted_date``,
    ``added_to_list_date``, ``location``, ``company_name``, ``job_description``.

    If ``output_path`` already exists, **existing rows are kept**. For each fetched posting, when
    its ``url`` already appears in that file the row is **skipped** so prior fields (including the
    original ``added_to_list_date``) remain unchanged; brand-new URLs are **appended** with
    ``added_to_list_date`` set to ``list_addition_run_date`` (default **local**
    :func:`datetime.date.today`). Jobs that disappeared from listings stay in the file until removed
    manually.

    ``listing_posted_date`` remains the calendar day reported by the listing API where present.

    Overwrites ``output_path`` atomically via full rewrite each run. Uses UTF-8 and standard CSV
    quoting.
    """
    run_day = list_addition_run_date or datetime.date.today()
    run_iso = run_day.isoformat()

    merged_rows = _load_existing_export_rows(output_path)
    _backfill_missing_added_dates(merged_rows, run_iso)
    urls_present = {row["url"].strip() for row in merged_rows if row["url"].strip()}

    for posting in postings:
        url_key = posting.url.strip()
        if not url_key:
            continue
        if url_key in urls_present:
            continue
        merged_rows.append(_posting_to_row(posting, run_iso))
        urls_present.add(url_key)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(JOBS_EXPORT_FIELDNAMES)
        for row in merged_rows:
            writer.writerow([row[name] for name in JOBS_EXPORT_FIELDNAMES])
