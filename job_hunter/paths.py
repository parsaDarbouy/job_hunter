"""Default filesystem locations for CLI commands that write artifacts."""

from __future__ import annotations

from pathlib import Path

# Root directory for generated files (YAML exports, future reports, etc.).
DATA_DIRECTORY = Path("data")


def default_resume_yaml_path() -> Path:
    """Default path for normalized resume output from ``resume:ingest``."""
    return DATA_DIRECTORY / "resume.yaml"


def default_weblist_yaml_path() -> Path:
    """User-edited job board list (gitignored under ``data/`` when present)."""
    return DATA_DIRECTORY / "weblist.yaml"


def default_weblist_example_yaml_path() -> Path:
    """Tracked template for ``weblist.yaml``."""
    return DATA_DIRECTORY / "weblist.example.yaml"


def default_position_yaml_path() -> Path:
    """User-edited position criteria (gitignored under ``data/`` when present)."""
    return DATA_DIRECTORY / "position.yaml"


def default_position_example_yaml_path() -> Path:
    """Tracked template for ``position.yaml``."""
    return DATA_DIRECTORY / "position.example.yaml"


def default_query_yaml_path() -> Path:
    """Generated query plan consumed by the listing export command."""
    return DATA_DIRECTORY / "query.yaml"


def default_jobs_export_csv_path() -> Path:
    """Default CSV path for matched job rows from ``listings:export``."""
    return DATA_DIRECTORY / "jobs_export.csv"
