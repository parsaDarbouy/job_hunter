"""Write matched jobs to a UTF-8 CSV file."""

from __future__ import annotations

import csv
from pathlib import Path

from job_hunter.job_listings.models import JobPosting


def write_jobs_csv(postings: list[JobPosting], output_path: Path) -> None:
    """
    Persist ``postings`` with columns ``url``, ``job_title``, ``location``.

    Overwrites ``output_path`` when it already exists. Uses UTF-8 and standard CSV quoting.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["url", "job_title", "location"])
        for posting in postings:
            writer.writerow([posting.url, posting.title, posting.location])
