"""Validate tailored LaTeX against cv_layout word and bullet limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from job_hunter.cv_generate.latex_text_metrics import (
    count_plain_words,
    count_textbf_spans,
    extract_zitemize_bullets,
    parse_skills_table_categories,
    strip_latex_to_plain_text,
)
from job_hunter.cv_generate.layout_constraints import (
    SKILLS_MAX_CATEGORIES,
    SKILLS_MAX_CHARACTERS_PER_SKILL,
    CvLayoutConstraints,
)

_LAYOUT_PART_LABELS: dict[str, str] = {
    "about_me": "objective / about me (sections/objective.tex)",
    "experience_bullet_count": "experience bullet count (sections/experience.tex)",
    "experience_bullet_words": "experience bullet word count (sections/experience.tex)",
    "experience_bullet_bold": "experience bullet keywords (sections/experience.tex)",
    "skills_category_count": "skills category count (sections/skills.tex)",
    "skills_skill_length": "skills skill name length (sections/skills.tex)",
}


@dataclass(frozen=True)
class LayoutViolation:
    """One ``cv_layout`` limit breach with a stable part id for logging and retries."""

    part: str
    message: str

    @property
    def part_label(self) -> str:
        return _LAYOUT_PART_LABELS.get(self.part, self.part)


def layout_violation_parts(violations: list[LayoutViolation]) -> list[str]:
    """Unique human-readable part labels in first-seen order."""
    seen: set[str] = set()
    labels: list[str] = []
    for violation in violations:
        label = violation.part_label
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def format_layout_violations_error(violations: list[LayoutViolation]) -> str:
    joined = "; ".join(violation.message for violation in violations)
    return f"Tailored LaTeX violates cv_layout limits: {joined}"


def collect_layout_violations(
    *,
    files: Mapping[str, str],
    layout: CvLayoutConstraints,
    resume_max_pages: int,
) -> list[LayoutViolation]:
    """Return all ``cv_layout`` limit breaches without raising."""
    violations: list[LayoutViolation] = []

    objective = files.get("sections/objective.tex", "")
    objective_words = count_plain_words(strip_latex_to_plain_text(objective))
    if objective_words < layout.about_me_words_min or objective_words > layout.about_me_words_max:
        violations.append(
            LayoutViolation(
                part="about_me",
                message=(
                    "sections/objective.tex (about me) has "
                    f"{objective_words} words; required "
                    f"{layout.about_me_words_min}–{layout.about_me_words_max}"
                ),
            )
        )

    experience_tex = files.get("sections/experience.tex", "")
    all_bullets: list[tuple[str, str]] = []
    for bullet in extract_zitemize_bullets(experience_tex):
        all_bullets.append(("sections/experience.tex", bullet))

    required_bullets = layout.max_total_experience_bullets(resume_max_pages)
    bullet_count = len(all_bullets)
    if bullet_count != required_bullets:
        violations.append(
            LayoutViolation(
                part="experience_bullet_count",
                message=(
                    f"sections/experience.tex has {bullet_count} \\item lines; "
                    f"must be exactly {required_bullets} "
                    f"(experience_bullets_per_page={layout.experience_bullets_per_page} × "
                    f"resume_max_pages={resume_max_pages})"
                ),
            )
        )

    for path, bullet in all_bullets:
        words = count_plain_words(bullet)
        if words < layout.experience_bullet_words_min or words > layout.experience_bullet_words_max:
            violations.append(
                LayoutViolation(
                    part="experience_bullet_words",
                    message=(
                        f"{path} bullet has {words} words; required "
                        f"{layout.experience_bullet_words_min}–{layout.experience_bullet_words_max}: "
                        f"{bullet[:80]}{'…' if len(bullet) > 80 else ''}"
                    ),
                )
            )
        bold_count = count_textbf_spans(bullet)
        if bold_count < 1 or bold_count > 2:
            violations.append(
                LayoutViolation(
                    part="experience_bullet_bold",
                    message=(
                        f"{path} bullet must have 1–2 \\textbf{{}} keywords (found {bold_count}): "
                        f"{bullet[:80]}{'…' if len(bullet) > 80 else ''}"
                    ),
                )
            )

    skills_tex = files.get("sections/skills.tex", "")
    skill_categories = parse_skills_table_categories(skills_tex)
    if len(skill_categories) > SKILLS_MAX_CATEGORIES:
        violations.append(
            LayoutViolation(
                part="skills_category_count",
                message=(
                    f"sections/skills.tex has {len(skill_categories)} skill categories; "
                    f"maximum is {SKILLS_MAX_CATEGORIES}"
                ),
            )
        )
    for category, skills in skill_categories:
        for skill in skills:
            if len(skill) > SKILLS_MAX_CHARACTERS_PER_SKILL:
                violations.append(
                    LayoutViolation(
                        part="skills_skill_length",
                        message=(
                            f"sections/skills.tex skill {skill!r} in category {category!r} has "
                            f"{len(skill)} characters; maximum is {SKILLS_MAX_CHARACTERS_PER_SKILL}"
                        ),
                    )
                )

    return violations


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
    violations = collect_layout_violations(
        files=files,
        layout=layout,
        resume_max_pages=resume_max_pages,
    )
    if violations:
        raise ValueError(format_layout_violations_error(violations))
