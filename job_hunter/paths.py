"""Default filesystem locations for CLI commands that write artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def default_filtered_jobs_csv_path(target_date: Any) -> Path:
    """Default CSV path for AI-filtered jobs from ``jobs:filter``."""
    date_text = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    return DATA_DIRECTORY / f"filtered_jobs_{date_text}.csv"


def default_cv_template_path() -> Path:
    """Tracked LaTeX CV template (example profile) for ``cv:generate``."""
    return DATA_DIRECTORY / "cv_template"


def working_cv_template_dir() -> Path:
    """Gitignored working copy where Gemini edits LaTeX before compile."""
    return DATA_DIRECTORY / ".cv_template"


def cv_output_dir() -> Path:
    """Directory for tailored PDFs and fetched job descriptions."""
    return DATA_DIRECTORY / "cv"


def job_description_path() -> Path:
    """Plain-text job description saved by ``cv:generate``."""
    return cv_output_dir() / "job_description.txt"
