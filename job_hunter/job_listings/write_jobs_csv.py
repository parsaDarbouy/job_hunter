"""Write matched jobs to a UTF-8 CSV file."""

from __future__ import annotations

import csv
import datetime
from pathlib import Path

from job_hunter.job_listings.models import JobPosting


_ADDED_COLUMN = "added_to_list_date"


def _load_added_to_list_date_by_url(previous_csv: Path) -> dict[str, str]:
    """
    Load URL → ``YYYY-MM-DD`` from an existing export so re-runs keep the original “first seen here” day.

    When the file has no ``added_to_list_date`` column (pre-feature CSV), returns an empty map so
    every visible row adopts the next run date once.
    """
    if not previous_csv.is_file():
        return {}
    try:
        with previous_csv.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or _ADDED_COLUMN not in reader.fieldnames:
                return {}
            accumulated: dict[str, str] = {}
            for row in reader:
                if not isinstance(row, dict):
                    continue
                url_key = str(row.get("url") or "").strip()
                when = str(row.get(_ADDED_COLUMN) or "").strip()
                if not url_key or not when:
                    continue
                earlier = accumulated.get(url_key)
                if earlier is None or when < earlier:
                    accumulated[url_key] = when
            return accumulated
    except OSError:
        return {}


def write_jobs_csv(
    postings: list[JobPosting],
    output_path: Path,
    *,
    list_addition_run_date: datetime.date | None = None,
) -> None:
    """
    Persist ``postings`` with columns ``url``, ``job_title``, ``listing_posted_date``,
    ``added_to_list_date``, ``location``, ``company_name``.

    ``listing_posted_date`` is ``YYYY-MM-DD`` when the listing API exposed a publication time.

    ``added_to_list_date`` is the calendar day this tool first included the row for that ``url`` in
    this CSV: new URLs use ``list_addition_run_date`` (default **local** :func:`datetime.date.today`);
    URLs already present in ``output_path`` keep their previous value.

    Overwrites ``output_path`` when it already exists. Uses UTF-8 and standard CSV quoting.
    """
    run_day = list_addition_run_date or datetime.date.today()
    run_iso = run_day.isoformat()
    preserved = _load_added_to_list_date_by_url(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["url", "job_title", "listing_posted_date", _ADDED_COLUMN, "location", "company_name"],
        )
        for posting in postings:
            url_key = posting.url.strip()
            added = preserved.get(url_key) or run_iso
            writer.writerow(
                [
                    posting.url,
                    posting.title,
                    posting.listing_posted_date,
                    added,
                    posting.location,
                    posting.company_name,
                ]
            )
