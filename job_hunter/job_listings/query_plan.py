"""Build the ``query.yaml`` document from weblist sources and position criteria."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from job_hunter.job_listings.board_urls import (
    ashby_job_board_url,
    greenhouse_jobs_url,
    workable_apply_jobs_url,
)


def _acceptable_titles(position: Mapping[str, Any]) -> list[str]:
    titles = position.get("titles") or {}
    raw = titles.get("acceptable")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("position.titles.acceptable must be a list of strings when present")
    return [str(item) for item in raw if str(item).strip()]


def _not_acceptable_titles(position: Mapping[str, Any]) -> list[str]:
    titles = position.get("titles") or {}
    raw = titles.get("not_acceptable")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("position.titles.not_acceptable must be a list of strings when present")
    return [str(item) for item in raw if str(item).strip()]


def _criteria_snapshot(position: Mapping[str, Any]) -> dict[str, Any]:
    """Embed a stable snapshot of filters for auditing next to each query plan."""
    location_constraints = position.get("location_constraints") or {}
    compensation = position.get("compensation") or {}
    seniority = position.get("acceptable_seniority_levels")
    seniority_blocked = position.get("not_acceptable_seniority_levels")
    experience = position.get("acceptable_years_experience_on_job") or {}
    return {
        "location_constraints": dict(location_constraints) if isinstance(location_constraints, dict) else {},
        "compensation": dict(compensation) if isinstance(compensation, dict) else {},
        "acceptable_seniority_levels": list(seniority) if isinstance(seniority, list) else [],
        "not_acceptable_seniority_levels": (
            list(seniority_blocked) if isinstance(seniority_blocked, list) else []
        ),
        "acceptable_years_experience_on_job": dict(experience) if isinstance(experience, dict) else {},
        "titles": {
            "acceptable": _acceptable_titles(position),
            "not_acceptable": _not_acceptable_titles(position),
        },
    }


def _fetch_task_for_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Build one fetch task entry for a single weblist source."""
    kind = source.get("kind")
    source_id = source.get("id")
    if not source_id:
        raise ValueError("Each weblist source must include a non-empty 'id' string")
    enabled = source.get("enabled") is not False
    if not enabled:
        return {
            "task_id": str(source_id),
            "kind": str(kind),
            "enabled": False,
            "request": None,
            "parameters": {key: value for key, value in source.items() if key != "kind"},
        }
    if kind == "greenhouse":
        token = source.get("board_token")
        if not token:
            raise ValueError(f"greenhouse source {source_id!r} requires 'board_token'")
        url = greenhouse_jobs_url(str(token))
        parameters: dict[str, Any] = {"board_token": str(token)}
        parent = source.get("expansion_parent_id")
        if isinstance(parent, str) and parent.strip():
            parameters["expansion_parent_id"] = parent.strip()
        return {
            "task_id": str(source_id),
            "kind": "greenhouse",
            "enabled": True,
            "request": {"method": "GET", "url": url},
            "parameters": parameters,
        }
    if kind == "ashby":
        slug = source.get("organization_slug")
        if not slug:
            raise ValueError(f"ashby source {source_id!r} requires 'organization_slug'")
        url = ashby_job_board_url(str(slug))
        parameters = {"organization_slug": str(slug)}
        parent = source.get("expansion_parent_id")
        if isinstance(parent, str) and parent.strip():
            parameters["expansion_parent_id"] = parent.strip()
        return {
            "task_id": str(source_id),
            "kind": "ashby",
            "enabled": True,
            "request": {"method": "GET", "url": url},
            "parameters": parameters,
        }
    if kind == "workable":
        slug = source.get("apply_account_slug")
        if not slug:
            raise ValueError(f"workable source {source_id!r} requires 'apply_account_slug'")
        url = workable_apply_jobs_url(str(slug))
        parameters = {"apply_account_slug": str(slug)}
        parent = source.get("expansion_parent_id")
        if isinstance(parent, str) and parent.strip():
            parameters["expansion_parent_id"] = parent.strip()
        return {
            "task_id": str(source_id),
            "kind": "workable",
            "enabled": True,
            "request": {"method": "GET", "url": url},
            "parameters": parameters,
        }
    if kind == "custom_career_page":
        display_name = source.get("display_name") or source_id
        page_url = source.get("careers_page_url")
        parameters = {
            "display_name": str(display_name),
            "careers_page_url": str(page_url) if page_url else "",
        }
        parent = source.get("expansion_parent_id")
        if isinstance(parent, str) and parent.strip():
            parameters["expansion_parent_id"] = parent.strip()
        return {
            "task_id": str(source_id),
            "kind": "custom_career_page",
            "enabled": True,
            "request": None,
            "parameters": parameters,
        }
    raise ValueError(f"Unsupported weblist source kind {kind!r} for source id {source_id!r}")


def _title_query_matrix(sources: list[Mapping[str, Any]], acceptable_titles: list[str]) -> list[dict[str, Any]]:
    """Cartesian-style rows: each source × each acceptable title (plus career URLs for manual review)."""
    rows: list[dict[str, Any]] = []
    for source in sources:
        if source.get("enabled") is False:
            continue
        source_id = str(source.get("id", ""))
        kind = source.get("kind")
        if kind == "custom_career_page":
            page_url = str(source.get("careers_page_url") or "").strip()
            for title in acceptable_titles:
                rows.append(
                    {
                        "source_id": source_id,
                        "provider_kind": str(kind),
                        "acceptable_title": title,
                        "careers_page_url": page_url,
                        "match_strategy": "manual_review_or_future_fetch_from_careers_page",
                    }
                )
            continue
        for title in acceptable_titles:
            rows.append(
                {
                    "source_id": source_id,
                    "provider_kind": str(kind),
                        "acceptable_title": title,
                        "match_strategy": (
                            "job_title_matches_acceptable_title_phrase_case_insensitive_word_boundaries"
                        ),
                    }
            )
    return rows


def build_query_plan(
    *,
    weblist_path: str,
    position_path: str,
    csv_output_path: str,
    sources: list[dict[str, Any]],
    position: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the full ``query.yaml`` payload."""
    acceptable = _acceptable_titles(position)
    fetch_tasks = [_fetch_task_for_source(source) for source in sources]
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "weblist_path": weblist_path,
            "position_path": position_path,
            "csv_output_path": csv_output_path,
        },
        "criteria_snapshot": _criteria_snapshot(position),
        "fetch_tasks": fetch_tasks,
        "title_query_matrix": _title_query_matrix(sources, acceptable),
    }
