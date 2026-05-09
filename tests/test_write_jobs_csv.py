"""Tests for CSV export semantics."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from job_hunter.job_listings.models import JobPosting
from job_hunter.job_listings.write_jobs_csv import write_jobs_csv


def _read_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_added_to_list_date_is_run_day_when_no_previous_export(tmp_path: Path) -> None:
    out = tmp_path / "jobs.csv"
    posting = JobPosting(
        url="https://example.com/j/1",
        title="Engineer",
        location="Canada",
        source_id="s",
        provider_kind="greenhouse",
        company_name="Co",
        listing_posted_date="2026-01-01",
    )
    write_jobs_csv([posting], out, list_addition_run_date=date(2026, 5, 8))
    rows = _read_rows(out)
    assert len(rows) == 1
    assert rows[0]["added_to_list_date"] == "2026-05-08"


def test_added_to_list_date_preserved_across_runs(tmp_path: Path) -> None:
    out = tmp_path / "jobs.csv"
    first_day = date(2026, 1, 1)
    second_day = date(2026, 6, 1)
    posting = JobPosting(
        url="https://example.com/j/1",
        title="Engineer",
        location="Canada",
        source_id="s",
        provider_kind="greenhouse",
        company_name="Co",
        listing_posted_date="2026-01-01",
    )
    write_jobs_csv([posting], out, list_addition_run_date=first_day)
    write_jobs_csv([posting], out, list_addition_run_date=second_day)
    rows = _read_rows(out)
    assert rows[0]["added_to_list_date"] == "2026-01-01"


def test_migration_previous_csv_without_added_column_sets_run_day(tmp_path: Path) -> None:
    out = tmp_path / "jobs.csv"
    out.write_text(
        "\n".join(
            [
                "url,job_title,listing_posted_date,location,company_name",
                "https://example.com/old,Legacy,,Somewhere,Ship",
                "",
            ]
        ),
        encoding="utf-8",
    )
    posting = JobPosting(
        url="https://example.com/old",
        title="Legacy",
        location="Somewhere",
        source_id="s",
        provider_kind="greenhouse",
        company_name="Ship",
        listing_posted_date="",
    )
    write_jobs_csv([posting], out, list_addition_run_date=date(2026, 3, 3))
    rows = _read_rows(out)
    assert rows[0]["added_to_list_date"] == "2026-03-03"

