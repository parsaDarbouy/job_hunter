"""Orchestrate query generation, network fetch, filtering, and CSV export."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

import yaml

from job_hunter.job_listings.board_fetchers import dedupe_job_postings_by_url, fetch_jobs_for_source
from job_hunter.job_listings.models import JobPosting
from job_hunter.job_listings.config_sources import (
    default_csv_output_path,
    default_query_output_path,
    load_yaml_mapping,
    parse_weblist,
    resolve_position_path,
    resolve_weblist_path,
)
from job_hunter.job_listings.location_description_rescue import LocationDescriptionRescueRunner
from job_hunter.job_listings.position_filters import posting_matches_position
from job_hunter.job_listings.query_plan import build_query_plan
from job_hunter.job_listings.weblist_expand import expand_weblist_sources
from job_hunter.job_listings.write_jobs_csv import write_jobs_csv


def _write_query_yaml(document: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        dict(document),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    output_path.write_text(rendered, encoding="utf-8")


def run_listings_export(
    *,
    weblist_path: Path | None = None,
    position_path: Path | None = None,
    query_output_path: Path | None = None,
    csv_output_path: Path | None = None,
    debug: bool = False,
    gemini_binary: str | None = None,
    gemini_model: str | None = None,
) -> Path:
    """
    Build ``query.yaml``, fetch listings, filter by ``position.yaml``, write ``jobs_export.csv``.

    Optional ``gemini_*`` overrides apply when ``location_constraints.gemini_description_rescue.enabled``
    is true in ``position.yaml``.

    Returns the absolute path to the CSV file.
    """
    resolved_weblist = resolve_weblist_path(weblist_path)
    resolved_position = resolve_position_path(position_path)
    query_out = (query_output_path or default_query_output_path()).expanduser().resolve()
    csv_out = (csv_output_path or default_csv_output_path()).expanduser().resolve()

    weblist_document = load_yaml_mapping(resolved_weblist)
    position_document = load_yaml_mapping(resolved_position)
    sources = expand_weblist_sources(parse_weblist(weblist_document), weblist_path=resolved_weblist)

    plan = build_query_plan(
        weblist_path=str(resolved_weblist),
        position_path=str(resolved_position),
        csv_output_path=str(csv_out),
        sources=sources,
        position=position_document,
    )
    _write_query_yaml(plan, query_out)

    aggregated: list[JobPosting] = []
    for source in sources:
        if source.get("enabled") is False:
            continue
        postings, warning = fetch_jobs_for_source(source)
        if debug and warning:
            print(f"[debug] source={source.get('id')!r}: {warning}", file=sys.stderr)
        aggregated.extend(postings)

    rescue_runner = LocationDescriptionRescueRunner.maybe_build(
        position_document,
        gemini_binary=gemini_binary,
        model=gemini_model,
        debug=debug,
    )
    matched = [
        posting
        for posting in aggregated
        if posting_matches_position(posting, position_document, location_rescue_runner=rescue_runner)
    ]
    deduped = dedupe_job_postings_by_url(matched)
    write_jobs_csv(deduped, csv_out)
    return csv_out
