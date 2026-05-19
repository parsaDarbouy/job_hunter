"""Validate tailored LaTeX against cv_layout word and bullet limits."""

from __future__ import annotations

from typing import Mapping

from job_hunter.cv_generate.latex_text_metrics import (
    count_plain_words,
    count_textbf_spans,
    extract_zitemize_bullets,
    strip_latex_to_plain_text,
)
from job_hunter.cv_generate.layout_constraints import CvLayoutConstraints


def validate_tailored_layout(
    *,
    files: Mapping[str, str],
    layout: CvLayoutConstraints,
    resume_max_pages: int,
) -> None:
    """
    Ensure objective and experience sections respect ``cv_layout`` limits.

    Raises ValueError when any limit is violated.
    """
    violations: list[str] = []

    objective = files.get("sections/objective.tex", "")
    objective_words = count_plain_words(strip_latex_to_plain_text(objective))
    if objective_words < layout.about_me_words_min or objective_words > layout.about_me_words_max:
        violations.append(
            "sections/objective.tex (about me) has "
            f"{objective_words} words; required "
            f"{layout.about_me_words_min}–{layout.about_me_words_max}"
        )

    experience_tex = files.get("sections/experience.tex", "")
    all_bullets: list[tuple[str, str]] = []
    for bullet in extract_zitemize_bullets(experience_tex):
        all_bullets.append(("sections/experience.tex", bullet))

    required_bullets = layout.max_total_experience_bullets(resume_max_pages)
    bullet_count = len(all_bullets)
    if bullet_count != required_bullets:
        violations.append(
            f"sections/experience.tex has {bullet_count} \\item lines; "
            f"must be exactly {required_bullets} "
            f"(experience_bullets_per_page={layout.experience_bullets_per_page} × "
            f"resume_max_pages={resume_max_pages})"
        )

    for path, bullet in all_bullets:
        words = count_plain_words(bullet)
        if words < layout.experience_bullet_words_min or words > layout.experience_bullet_words_max:
            violations.append(
                f"{path} bullet has {words} words; required "
                f"{layout.experience_bullet_words_min}–{layout.experience_bullet_words_max}: "
                f"{bullet[:80]}{'…' if len(bullet) > 80 else ''}"
            )
        bold_count = count_textbf_spans(bullet)
        if bold_count < 1 or bold_count > 2:
            violations.append(
                f"{path} bullet must have 1–2 \\textbf{{}} keywords (found {bold_count}): "
                f"{bullet[:80]}{'…' if len(bullet) > 80 else ''}"
            )

    if violations:
        joined = "; ".join(violations)
        raise ValueError(f"Tailored LaTeX violates cv_layout limits: {joined}")
