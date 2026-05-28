"""Tests for cv_layout parsing and LaTeX layout validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.cv_generate.latex_text_metrics import (
    cap_latex_item_bullets,
    count_latex_item_bullets,
    count_plain_words,
    count_textbf_spans,
    extract_zitemize_bullets,
    parse_skills_table_categories,
)
from job_hunter.cv_generate.layout_constraints import CvLayoutConstraints, parse_cv_layout_constraints
from job_hunter.cv_generate.validate_layout import (
    collect_layout_violations,
    layout_violation_parts,
    validate_tailored_layout,
)


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
            r"\item Operated \textbf{reliable} systems with metrics and alerts for on-call."
            r"\item Improved \textbf{deployment} pipelines using automation and review."
            r"\end{zitemize}"
        ),
        "sections/previous.tex": "",
    }
    validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_validate_tailored_layout_rejects_too_many_textbf_in_bullet() -> None:
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
            r"\item Operated \textbf{one} and \textbf{two} and \textbf{three} systems here today."
            r"\end{zitemize}"
        ),
    }
    with pytest.raises(ValueError, match="1–2"):
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
    with pytest.raises(ValueError, match="must be exactly 1"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_validate_tailored_layout_rejects_too_few_bullets() -> None:
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
            r"\item \textbf{Only} one bullet with enough words here today."
            r"\end{zitemize}"
        ),
    }
    with pytest.raises(ValueError, match="must be exactly 2"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_cap_latex_item_bullets_enforces_max() -> None:
    latex = (
        r"\begin{zitemize}"
        + "\n".join(rf"\item bullet number {index} here today now" for index in range(5))
        + r"\end{zitemize}"
    )
    capped = cap_latex_item_bullets(latex, 3)
    assert count_latex_item_bullets(capped) == 3


def test_layout_as_dict_includes_max_total_bullets() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=50,
        about_me_words_max=70,
        experience_bullets_per_page=17,
        experience_bullet_words_min=9,
        experience_bullet_words_max=12,
    )
    payload = layout.as_dict(resume_max_pages=1)
    assert payload["experience_max_total_bullets"] == 17
    assert payload["skills_max_categories"] == 5
    assert payload["skills_max_characters_per_skill"] == 40


def test_parse_skills_table_categories_counts_template_rows() -> None:
    skills_tex = (Path(__file__).resolve().parents[1] / "data/cv_template/sections/skills.tex").read_text(
        encoding="utf-8",
    )
    categories = parse_skills_table_categories(skills_tex)
    assert len(categories) == 5
    for _, skills in categories:
        assert skills
        assert all(len(skill) <= 40 for skill in skills)


def test_validate_tailored_layout_rejects_too_many_skill_categories() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=50,
        experience_bullets_per_page=1,
        experience_bullet_words_min=5,
        experience_bullet_words_max=30,
    )
    rows = "\n".join(
        rf"\skills{{Category {index}}} & & {{ Skill A}}, {{ Skill B}} \\" for index in range(6)
    )
    files = {
        "sections/objective.tex": "Short summary here today with enough words.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item \textbf{Only} one bullet with enough words here today."
            r"\end{zitemize}"
        ),
        "sections/skills.tex": rows,
    }
    with pytest.raises(ValueError, match="6 skill categories"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_layout_violation_parts_lists_unique_sections() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=50,
        experience_bullets_per_page=1,
        experience_bullet_words_min=5,
        experience_bullet_words_max=30,
    )
    long_skill = "A" * 41
    files = {
        "sections/objective.tex": "Short summary here today with enough words.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item \textbf{Only} one bullet with enough words here today."
            r"\end{zitemize}"
        ),
        "sections/skills.tex": rf"\skills{{Languages}} & & {{{long_skill}}} \\",
    }
    violations = collect_layout_violations(files=files, layout=layout, resume_max_pages=1)
    parts = layout_violation_parts(violations)
    assert len(parts) == 1
    assert "skills" in parts[0]


def test_validate_tailored_layout_rejects_skill_exceeding_character_limit() -> None:
    layout = CvLayoutConstraints(
        about_me_words_min=5,
        about_me_words_max=50,
        experience_bullets_per_page=1,
        experience_bullet_words_min=5,
        experience_bullet_words_max=30,
    )
    long_skill = "A" * 41
    files = {
        "sections/objective.tex": "Short summary here today with enough words.",
        "sections/experience.tex": (
            r"\begin{zitemize}"
            r"\item \textbf{Only} one bullet with enough words here today."
            r"\end{zitemize}"
        ),
        "sections/skills.tex": rf"\skills{{Languages}} & & {{{long_skill}}} \\",
    }
    with pytest.raises(ValueError, match="41 characters"):
        validate_tailored_layout(files=files, layout=layout, resume_max_pages=1)


def test_count_textbf_spans() -> None:
    assert count_textbf_spans(r"\item One \textbf{AWS} only here.") == 1
    assert count_textbf_spans(r"\item \textbf{A} and \textbf{B} here.") == 2
    assert count_textbf_spans(r"\item No bold here today.") == 0


def test_extract_zitemize_bullets() -> None:
    latex = r"\begin{zitemize}\item Alpha one two three four.\item Beta five six seven eight.\end{zitemize}"
    bullets = extract_zitemize_bullets(latex)
    assert len(bullets) == 2
    assert count_plain_words(bullets[0]) >= 4
