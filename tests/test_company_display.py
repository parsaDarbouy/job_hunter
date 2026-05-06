"""Tests for company display labels on export rows."""

from __future__ import annotations

from job_hunter.job_listings.company_display import greenhouse_company_display, humanize_board_identifier


def test_humanize_board_identifier_splits_separators() -> None:
    assert humanize_board_identifier("getyourguide") == "Getyourguide"
    assert humanize_board_identifier("traderepublicbank") == "Traderepublicbank"
    assert humanize_board_identifier("lakera.ai") == "Lakera Ai"
    assert humanize_board_identifier("run_pod") == "Run Pod"


def test_greenhouse_prefers_api_company_name() -> None:
    assert greenhouse_company_display({"company_name": "Vercel"}, board_token="ignored") == "Vercel"


def test_greenhouse_fallback_to_token() -> None:
    job: dict[str, str] = {}
    assert greenhouse_company_display(job, board_token="acme-corp") == "Acme Corp"
