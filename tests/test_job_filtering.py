"""Tests for date-scoped AI job filtering."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from job_hunter.job_filtering.gemini_filter import GeminiJobAssessment
from job_hunter.job_filtering.run_job_filtering import run_job_filtering


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_filtering_adds_missing_description_column_and_fetches_only_target_date(tmp_path: Path) -> None:
    jobs_csv = tmp_path / "jobs.csv"
    jobs_csv.write_text(
        "\n".join(
            [
                "url,job_title,listing_posted_date,added_to_list_date,location,company_name",
                "https://example.com/a,Platform Engineer,,2026-05-08,Canada,Example",
                "https://example.com/b,Platform Engineer,,2026-05-09,Canada,Example",
                "",
            ]
        ),
        encoding="utf-8",
    )
    resume = tmp_path / "resume.yaml"
    resume.write_text("skills:\n  tools:\n    - Kubernetes\n", encoding="utf-8")
    position = tmp_path / "position.yaml"
    position.write_text(
        "ai_filtering:\n  minimum_alignment_percentage: 70\n",
        encoding="utf-8",
    )
    output = tmp_path / "filtered.csv"

    fetched_urls: list[str] = []

    def fetch_description(url: str) -> str:
        fetched_urls.append(url)
        return "Kubernetes Terraform AWS platform engineering role"

    def assess_job(row: dict[str, str], **kwargs: Any) -> GeminiJobAssessment:
        assert kwargs["minimum_alignment_percentage"] == 70
        assert row["job_description"]
        return GeminiJobAssessment(alignment_percentage=85, passes=True, reason="Strong fit")

    result = run_job_filtering(
        target_date=date(2026, 5, 8),
        jobs_csv_path=jobs_csv,
        resume_path=resume,
        position_path=position,
        output_path=output,
        description_fetcher=fetch_description,
        job_assessor=assess_job,
    )

    assert result == output.resolve()
    assert fetched_urls == ["https://example.com/a"]

    rewritten_header = jobs_csv.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert rewritten_header[-1] == "job_description"
    rewritten_rows = _read_rows(jobs_csv)
    assert rewritten_rows[0]["job_description"] == "Kubernetes Terraform AWS platform engineering role"
    assert rewritten_rows[1]["job_description"] == ""

    filtered_rows = _read_rows(output)
    assert len(filtered_rows) == 1
    assert filtered_rows[0]["url"] == "https://example.com/a"
    assert filtered_rows[0]["job_description"] == "Kubernetes Terraform AWS platform engineering role"


def test_filtering_rejects_rows_below_configured_threshold_without_refetch(tmp_path: Path) -> None:
    jobs_csv = tmp_path / "jobs.csv"
    jobs_csv.write_text(
        "\n".join(
            [
                "url,job_title,listing_posted_date,added_to_list_date,location,company_name,job_description",
                "https://example.com/a,Platform Engineer,,2026-05-08,Canada,Example,Existing description",
                "",
            ]
        ),
        encoding="utf-8",
    )
    resume = tmp_path / "resume.yaml"
    resume.write_text("skills:\n  tools:\n    - Kubernetes\n", encoding="utf-8")
    position = tmp_path / "position.yaml"
    position.write_text(
        "ai_filtering:\n  minimum_alignment_percentage: 90\n",
        encoding="utf-8",
    )
    output = tmp_path / "filtered.csv"

    def fetch_description(url: str) -> str:
        raise AssertionError(f"unexpected fetch for {url}")

    def assess_job(row: dict[str, str], **kwargs: Any) -> GeminiJobAssessment:
        return GeminiJobAssessment(alignment_percentage=80, passes=True, reason="Below threshold")

    run_job_filtering(
        target_date=date(2026, 5, 8),
        jobs_csv_path=jobs_csv,
        resume_path=resume,
        position_path=position,
        output_path=output,
        description_fetcher=fetch_description,
        job_assessor=assess_job,
    )

    assert _read_rows(output) == []
