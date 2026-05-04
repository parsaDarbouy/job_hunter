"""Tests for ``query_plan``."""

from __future__ import annotations

from job_hunter.job_listings.query_plan import build_query_plan


def test_build_query_plan_disabled_source_has_no_request() -> None:
    sources = [
        {
            "id": "off",
            "kind": "greenhouse",
            "board_token": "acme",
            "enabled": False,
        },
        {
            "id": "on",
            "kind": "greenhouse",
            "board_token": "acme",
        },
    ]
    position = {"titles": {"acceptable": ["Engineer"], "not_acceptable": []}}
    plan = build_query_plan(
        weblist_path="/tmp/weblist.yaml",
        position_path="/tmp/position.yaml",
        csv_output_path="/tmp/out.csv",
        sources=sources,
        position=position,
    )
    tasks = {task["task_id"]: task for task in plan["fetch_tasks"]}
    assert tasks["off"]["enabled"] is False
    assert tasks["off"]["request"] is None
    assert tasks["on"]["enabled"] is True
    assert tasks["on"]["request"]["url"].startswith("https://boards-api.greenhouse.io/")


def test_title_query_matrix_skips_disabled_sources() -> None:
    sources = [
        {"id": "off", "kind": "greenhouse", "board_token": "acme", "enabled": False},
        {"id": "on", "kind": "greenhouse", "board_token": "acme"},
    ]
    position = {"titles": {"acceptable": ["A", "B"], "not_acceptable": []}}
    plan = build_query_plan(
        weblist_path="w",
        position_path="p",
        csv_output_path="e.csv",
        sources=sources,
        position=position,
    )
    source_ids = {row["source_id"] for row in plan["title_query_matrix"]}
    assert source_ids == {"on"}
