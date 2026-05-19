"""Tests for previous-experience section format validation."""

from __future__ import annotations

import pytest

from job_hunter.cv_generate.validate_previous import validate_previous_experience_format


def test_validate_previous_accepts_compact_template_lines() -> None:
    files = {
        "sections/previous.tex": (
            r"\skills{Software Developer},"
            r"\textit{Acme Corp}, \textit{Remote} \hfill {\bf 2021 - 2022}"
        ),
    }
    validate_previous_experience_format(files)


def test_validate_previous_rejects_item_bullets() -> None:
    files = {
        "sections/previous.tex": (
            r"\begin{zitemize}\item Did something at \textbf{Acme}.\end{zitemize}"
        ),
    }
    with pytest.raises(ValueError, match="no bullets"):
        validate_previous_experience_format(files)
