"""Tests for cv_layout parsing and LaTeX layout validation."""

from __future__ import annotations

import pytest

from job_hunter.cv_generate.latex_text_metrics import count_plain_words, extract_zitemize_bullets
from job_hunter.cv_generate.layout_constraints import CvLayoutConstraints, parse_cv_layout_constraints
from job_hunter.cv_generate.validate_layout import validate_tailored_layout


def test_parse_cv_layout_constraints() -> None:
    layout = parse_cv_layout_constraints(
        {
            "cv_layout": {
                "about_me_word_count": {"min": 50, "max": 70},
                "experience_bullets_per_page": 8,
                "experience_bullet_word_count": {"min": 15, "max": 30},
            }
        }
    )
    assert layout.about_me_words_min == 50
    assert layout.max_total_experience_bullets(1) == 8


def test_validate_tailored_layout_accepts_compliant_files() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=20,
        experience_bullets_per_page=2,
        experience_bullet_words_min=5,
        experience_bullet_words_max=20,
    )
    files = {
        "sections/objective.tex": "One two three four five six seven eight.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item Operated \textbf{reliable} systems with \textbf{metrics} and alerts for on-call."
            r"\item Improved \textbf{deployment} pipelines using \textbf{automation} and review."
            r"\end{zitemize}"
        ),
        "sections/previous.tex": "",
    }
    validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_validate_tailored_layout_requires_textbf_in_bullets() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=50,
        experience_bullets_per_page=2,
        experience_bullet_words_min=5,
        experience_bullet_words_max=30,
    )
    files = {
        "sections/objective.tex": "Short summary here today with enough words.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item Operated reliable systems with metrics and alerts for on-call."
            r"\end{zitemize}"
        ),
    }
    with pytest.raises(ValueError, match=r"\\textbf"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_validate_tailored_layout_rejects_too_many_bullets() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=50,
        experience_bullets_per_page=1,
        experience_bullet_words_min=5,
        experience_bullet_words_max=30,
    )
    files = {
        "sections/objective.tex": "Short summary here today with enough words.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item \textbf{First} bullet with enough words here today."
            r"\item \textbf{Second} bullet with enough words here today."
            r"\end{zitemize}"
        ),
    }
    with pytest.raises(ValueError, match="maximum is 1"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_extract_zitemize_bullets() -> None:
    latex = r"\begin{zitemize}\item Alpha one two three four.\item Beta five six seven eight.\end{zitemize}"
    bullets = extract_zitemize_bullets(latex)
    assert len(bullets) == 2
    assert count_plain_words(bullets[0]) >= 4
