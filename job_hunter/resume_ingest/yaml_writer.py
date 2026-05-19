"""Write canonical resume.yaml with stable key order and formatting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from job_hunter.resume_ingest.resume_settings import merge_cv_generation_settings


def build_resume_document(
    normalized: Mapping[str, Any],
    *,
    source_file: str,
    parsed_by: str = "gemini-cli-agent",
) -> dict[str, Any]:
    """Assemble the final on-disk schema with metadata."""
    return {
        "profile": normalized["profile"],
        "summary": normalized["summary"],
        "skills": normalized["skills"],
        "experience": normalized["experience"],
        "education": normalized["education"],
        "accomplishments": list(normalized.get("accomplishments") or []),
        "metadata": {
            "parsed_by": parsed_by,
            "source_file": source_file,
        },
    }


def write_resume_yaml(document: Mapping[str, Any], output_path: Path) -> None:
    """
    Serialize resume document to strict YAML suitable for downstream agents.

    Uses block style, fixed key order from build_resume_document, and no Python tags.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_cv_generation_settings(document, existing_output_path=output_path)
    payload = yaml.safe_dump(
        merged,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    output_path.write_text(payload, encoding="utf-8")
