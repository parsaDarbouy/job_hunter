"""Smoke tests for listing export with network calls mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from job_hunter.job_listings.models import JobPosting
from job_hunter.job_listings.run_listings_export import run_listings_export


def test_run_listings_export_writes_query_and_csv(tmp_path: Path) -> None:
    weblist = tmp_path / "weblist.yaml"
    weblist.write_text(
        """
sources:
  - id: mock_board
    kind: greenhouse
    board_token: example
""".strip(),
        encoding="utf-8",
    )
    position = tmp_path / "position.yaml"
    position.write_text(
        """
titles:
  acceptable:
    - Engineer
  not_acceptable: []
location_constraints:
  countries_onsite_or_hybrid_ok:
    - Canada
""".strip(),
        encoding="utf-8",
    )
    query_out = tmp_path / "query.yaml"
    csv_out = tmp_path / "jobs.csv"

    fake_posting = JobPosting(
        url="https://example.com/job/1",
        title="Platform Engineer",
        location="Toronto, Canada",
        source_id="mock_board",
        provider_kind="greenhouse",
    )

    with patch(
        "job_hunter.job_listings.run_listings_export.fetch_jobs_for_source",
        return_value=([fake_posting], None),
    ):
        result = run_listings_export(
            weblist_path=weblist,
            position_path=position,
            query_output_path=query_out,
            csv_output_path=csv_out,
            debug=False,
        )

    assert result == csv_out.resolve()
    assert query_out.is_file()
    text = query_out.read_text(encoding="utf-8")
    assert "fetch_tasks" in text
    assert "title_query_matrix" in text
    assert csv_out.is_file()
    assert csv_out.read_text(encoding="utf-8").startswith("url,job_title,location")
