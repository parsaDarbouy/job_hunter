"""Load weblist and position YAML from disk with sensible defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from job_hunter.paths import (
    default_position_example_yaml_path,
    default_query_yaml_path,
    default_weblist_example_yaml_path,
    default_weblist_yaml_path,
    default_jobs_export_csv_path,
    default_position_yaml_path,
)


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML file and require a top-level mapping."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at root: {path}")
    return data


def resolve_weblist_path(explicit: Path | None) -> Path:
    """Prefer ``data/weblist.yaml`` when present; otherwise fall back to the tracked example."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    candidate = default_weblist_yaml_path()
    if candidate.exists():
        return candidate.resolve()
    return default_weblist_example_yaml_path().resolve()


def resolve_position_path(explicit: Path | None) -> Path:
    """Prefer ``data/position.yaml`` when present; otherwise fall back to ``position.example.yaml``."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    candidate = default_position_yaml_path()
    if candidate.exists():
        return candidate.resolve()
    return default_position_example_yaml_path().resolve()


def parse_weblist(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the ``sources`` list from a weblist document."""
    sources = document.get("sources")
    if sources is None:
        raise ValueError("weblist YAML must contain a top-level 'sources' list")
    if not isinstance(sources, list):
        raise ValueError("'sources' must be a YAML list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            raise ValueError(f"weblist.sources[{index}] must be a mapping")
        normalized.append(dict(item))
    return normalized


def default_query_output_path() -> Path:
    """Default path for generated ``query.yaml``."""
    return default_query_yaml_path()


def default_csv_output_path() -> Path:
    """Default path for the jobs CSV export."""
    return default_jobs_export_csv_path()
