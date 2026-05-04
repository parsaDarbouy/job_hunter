"""Default filesystem locations for CLI commands that write artifacts."""

from __future__ import annotations

from pathlib import Path

# Root directory for generated files (YAML exports, future reports, etc.).
DATA_DIRECTORY = Path("data")


def default_resume_yaml_path() -> Path:
    """Default path for normalized resume output from ``resume:ingest``."""
    return DATA_DIRECTORY / "resume.yaml"
