"""CV layout limits from resume.yaml (about-me length, bullets per page, words per bullet)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CvLayoutConstraints:
    """Strict layout limits for ``cv:generate``."""

    about_me_words_min: int
    about_me_words_max: int
    experience_bullets_per_page: int
    experience_bullet_words_min: int
    experience_bullet_words_max: int

    def max_total_experience_bullets(self, resume_max_pages: int) -> int:
        return self.experience_bullets_per_page * max(resume_max_pages, 1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "about_me_word_count": {
                "min": self.about_me_words_min,
                "max": self.about_me_words_max,
            },
            "experience_bullets_per_page": self.experience_bullets_per_page,
            "experience_bullet_word_count": {
                "min": self.experience_bullet_words_min,
                "max": self.experience_bullet_words_max,
            },
        }


def _parse_word_range(
    value: Any,
    *,
    field_label: str,
) -> tuple[int, int]:
    if not isinstance(value, dict):
        raise ValueError(f"cv_layout.{field_label} must be a mapping with min and max")
    try:
        minimum = int(value.get("min"))
        maximum = int(value.get("max"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cv_layout.{field_label}.min and .max must be integers") from exc
    if minimum < 1 or maximum < 1:
        raise ValueError(f"cv_layout.{field_label} min and max must be at least 1")
    if minimum > maximum:
        raise ValueError(f"cv_layout.{field_label}.min must be <= max")
    return minimum, maximum


def parse_cv_layout_constraints(resume_document: Mapping[str, Any]) -> CvLayoutConstraints:
    """Load ``cv_layout`` from the top of resume.yaml."""
    layout = resume_document.get("cv_layout")
    if not isinstance(layout, dict):
        raise ValueError(
            "cv_layout must be set at the top of resume.yaml with "
            "about_me_word_count, experience_bullets_per_page, and experience_bullet_word_count"
        )

    about_min, about_max = _parse_word_range(
        layout.get("about_me_word_count"),
        field_label="about_me_word_count",
    )

    try:
        bullets_per_page = int(layout.get("experience_bullets_per_page"))
    except (TypeError, ValueError) as exc:
        raise ValueError("cv_layout.experience_bullets_per_page must be a positive integer") from exc
    if bullets_per_page < 1:
        raise ValueError("cv_layout.experience_bullets_per_page must be at least 1")

    bullet_min, bullet_max = _parse_word_range(
        layout.get("experience_bullet_word_count"),
        field_label="experience_bullet_word_count",
    )

    return CvLayoutConstraints(
        about_me_words_min=about_min,
        about_me_words_max=about_max,
        experience_bullets_per_page=bullets_per_page,
        experience_bullet_words_min=bullet_min,
        experience_bullet_words_max=bullet_max,
    )
