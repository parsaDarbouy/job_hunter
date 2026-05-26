"""Orchestrate query generation, network fetch, filtering, and CSV export."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, TextIO

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


def _format_progress_line(
    *,
    current: int,
    total: int,
    fetched: int,
    matched: int,
    bar_width: int = 24,
) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = min(bar_width, int(bar_width * current / total))
    bar = "#" * filled + "-" * (bar_width - filled)
    return f"[{bar}] {current}/{total} sources | {fetched} fetched | {matched} matched"


def run_listings_export(
    *,
    weblist_path: Path | None = None,
    position_path: Path | None = None,
    query_output_path: Path | None = None,
    csv_output_path: Path | None = None,
    debug: bool = False,
    enable_progress: bool = True,
    progress_stream: TextIO | None = None,
) -> Path:
    """
    Build ``query.yaml``, fetch listings, filter by ``position.yaml``, merge into ``jobs_export.csv``.

    When ``enable_progress`` is True, a single-line progress indicator is written to
    ``progress_stream`` (default stderr), cleared with a newline when fetching finishes.

    Returns the absolute path to the CSV file.
    """
    stream = progress_stream if progress_stream is not None else sys.stderr
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

    fetch_sources = [source for source in sources if source.get("enabled") is not False]
    total_sources = len(fetch_sources)

    def _write_progress(*, processed: int, fetched: int, matched: int) -> None:
        if not enable_progress:
            return
        line = (
            "listings:export "
            f"{_format_progress_line(current=processed, total=total_sources, fetched=fetched, matched=matched)}"
        )
        stream.write(f"\r{line}")
        stream.flush()

    aggregated: list[JobPosting] = []
    matched_count = 0
    if enable_progress and total_sources > 0:
        _write_progress(processed=0, fetched=0, matched=0)

    for index, source in enumerate(fetch_sources, start=1):
        postings, warning = fetch_jobs_for_source(source)
        if debug and warning:
            print(f"[debug] source={source.get('id')!r}: {warning}", file=sys.stderr)
        aggregated.extend(postings)
        matched_count += sum(
            1 for posting in postings if posting_matches_position(posting, position_document)
        )
        _write_progress(processed=index, fetched=len(aggregated), matched=matched_count)

    if enable_progress and total_sources > 0:
        stream.write("\n")
        stream.flush()

    matched = [posting for posting in aggregated if posting_matches_position(posting, position_document)]
    deduped = dedupe_job_postings_by_url(matched)
    write_jobs_csv(deduped, csv_out)
    return csv_out
