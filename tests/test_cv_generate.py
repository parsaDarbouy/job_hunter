"""Tests for tailored CV generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from job_hunter.cv_generate.filename import build_cv_pdf_filename, slugify_filename_part
from job_hunter.cv_generate.gemini_tailor import GeminiCvTailorResult
from job_hunter.cv_generate.run_cv_generate import run_cv_generate
from job_hunter.cv_generate.template_copy import copy_cv_template
from job_hunter.cv_generate.template_files import write_tailored_files
from job_hunter.cv_generate.validate_tailored import validate_employers_in_latex
from job_hunter.resume_ingest.resume_settings import merge_cv_generation_settings
from job_hunter.resume_ingest.yaml_writer import build_resume_document, write_resume_yaml


def test_merge_cv_generation_settings_preserves_top_level_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "resume.yaml"
    output_path.write_text(
        yaml.safe_dump(
            {
                "resume_max_pages": 1,
                "target_job_url": "https://example.com/jobs/1",
                "about_me_note": "Keep this angle",
                "profile": {"name": "Old"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    document = build_resume_document(
        {
            "profile": {
                "name": "New",
                "email": "",
                "phone": "",
                "location": "",
                "links": {"github": "", "linkedin": ""},
            },
            "accomplishments": [],
            "summary": {"total_years_experience": None, "domains": []},
            "skills": {
                "languages": [],
                "frameworks": [],
                "cloud": [],
                "tools": [],
                "other": [],
            },
            "experience": [],
            "education": [],
        },
        source_file="/tmp/resume.pdf",
    )
    merged = merge_cv_generation_settings(document, existing_output_path=output_path)
    assert merged["resume_max_pages"] == 1
    assert merged["target_job_url"] == "https://example.com/jobs/1"
    assert merged["about_me_note"] == "Keep this angle"
    assert merged["profile"]["name"] == "New"
    keys = list(merged.keys())
    assert keys.index("resume_max_pages") < keys.index("profile")


def test_write_resume_yaml_preserves_cv_settings(tmp_path: Path) -> None:
    output_path = tmp_path / "resume.yaml"
    output_path.write_text(
        "resume_max_pages: 2\ntarget_job_url: https://jobs.example/42\nprofile:\n  name: Keep\n",
        encoding="utf-8",
    )
    document = build_resume_document(
        {
            "profile": {
                "name": "Updated",
                "email": "",
                "phone": "",
                "location": "",
                "links": {"github": "", "linkedin": ""},
            },
            "accomplishments": [],
            "summary": {"total_years_experience": None, "domains": []},
            "skills": {
                "languages": [],
                "frameworks": [],
                "cloud": [],
                "tools": [],
                "other": [],
            },
            "experience": [],
            "education": [],
        },
        source_file="/tmp/resume.pdf",
    )
    write_resume_yaml(document, output_path)
    loaded = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert loaded["resume_max_pages"] == 2
    assert loaded["target_job_url"] == "https://jobs.example/42"
    assert loaded["profile"]["name"] == "Updated"


def test_slugify_filename_part() -> None:
    assert slugify_filename_part("Acme Corp!") == "Acme_Corp"
    assert build_cv_pdf_filename(company_name="Acme Corp", position_title="SRE / Platform") == (
        "Acme_Corp_SRE_Platform.pdf"
    )


def test_copy_cv_template_replaces_working_dir(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "resume.tex").write_text("% source", encoding="utf-8")
    working = tmp_path / "working"
    working.mkdir()
    (working / "stale.tex").write_text("% stale", encoding="utf-8")

    copy_cv_template(source_dir=source, working_dir=working)

    assert (working / "resume.tex").read_text(encoding="utf-8") == "% source"
    assert not (working / "stale.tex").exists()


def test_validate_employers_accepts_shortened_company_from_resume() -> None:
    resume = {
        "experience": [
            {"company": "Rahkar Andishan Tose Fanavari Raya Shiraz", "title": "DevOps"},
        ],
    }
    files = {
        "sections/previous.tex": (
            r"\textit{Rahkar Andishan Tose Fanavari Raya Shiraz}, \textit{Shiraz} \hfill {\bf 2023}"
        ),
    }
    validate_employers_in_latex(resume_document=resume, files=files)


def test_validate_employers_ignores_location_slot_city() -> None:
    resume = {
        "profile": {"location": "Vancouver"},
        "experience": [
            {"company": "Rahkar Andishan Tose Fanavari Raya Shiraz", "title": "DevOps"},
        ],
    }
    files = {
        "sections/previous.tex": (
            r"\textit{Rahkar Andishan Tose Fanavari Raya Shiraz}, \textit{Shiraz} \hfill {\bf 2023}"
        ),
    }
    validate_employers_in_latex(resume_document=resume, files=files)


def test_validate_employers_ignores_remote_in_subtext_location() -> None:
    resume = {
        "experience": [{"company": "Kleros", "title": "SRE"}],
    }
    files = {
        "sections/experience.tex": r"\subtext{Kleros \hfill Remote}",
    }
    validate_employers_in_latex(resume_document=resume, files=files)


def test_validate_employers_rejects_unknown_company() -> None:
    resume = {
        "experience": [{"company": "Northwind Systems", "title": "SRE"}],
    }
    files = {
        "sections/experience.tex": r"\subtext{Evil Corp \hfill Remote}",
    }
    with pytest.raises(ValueError, match="Evil Corp"):
        validate_employers_in_latex(resume_document=resume, files=files)


def test_write_tailored_files_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        write_tailored_files(tmp_path, {"../escape.tex": "bad"})


def test_run_cv_generate_end_to_end_mocked(tmp_path: Path) -> None:
    template_dir = tmp_path / "cv_template"
    template_dir.mkdir()
    (template_dir / "resume.tex").write_text("\\documentclass{article}", encoding="utf-8")
    sections = template_dir / "sections"
    sections.mkdir()
    for name in (
        "objective.tex",
        "skills.tex",
        "experience.tex",
        "education.tex",
        "previous.tex",
        "Accomplishments.tex",
    ):
        (sections / name).write_text("% section", encoding="utf-8")

    resume_path = tmp_path / "resume.yaml"
    resume_path.write_text(
        yaml.safe_dump(
            {
                "resume_max_pages": 2,
                "target_job_url": "https://example.com/jobs/99",
                "cv_layout": {
                    "about_me_word_count": {"min": 5, "max": 100},
                    "experience_bullets_per_page": 10,
                    "experience_bullet_word_count": {"min": 3, "max": 50},
                },
                "profile": {"name": "Alex", "email": "a@example.com", "links": {}},
                "summary": {},
                "skills": {},
                "experience": [{"company": "Northwind Systems", "title": "SRE"}],
                "education": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    working_dir = tmp_path / "working"
    output_dir = tmp_path / "cv"
    description_path = output_dir / "job_description.txt"

    def fake_tailor(**_kwargs: object) -> GeminiCvTailorResult:
        return GeminiCvTailorResult(
            company_name="Acme Corp",
            position_title="Site Reliability Engineer",
            files={
                "resume.tex": "\\documentclass{article}",
                "sections/objective.tex": "Short objective with enough words for validation here.",
                "sections/skills.tex": "% ok",
                "sections/experience.tex": r"\subtext{Northwind Systems \hfill Remote}",
                "sections/education.tex": "% ok",
                "sections/previous.tex": "% ok",
                "sections/Accomplishments.tex": "% ok",
            },
        )

    def fake_compile(*, working_dir: Path, **_kwargs: object) -> Path:
        pdf = working_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        return pdf

    with (
        patch(
            "job_hunter.cv_generate.run_cv_generate.working_cv_template_dir",
            return_value=working_dir,
        ),
        patch(
            "job_hunter.cv_generate.run_cv_generate.job_description_path",
            return_value=description_path,
        ),
        patch(
            "job_hunter.cv_generate.run_cv_generate.fetch_and_save_job_description",
            side_effect=lambda **_kwargs: (
                description_path.parent.mkdir(parents=True, exist_ok=True),
                description_path.write_text("Build reliable systems.", encoding="utf-8"),
                "Build reliable systems.",
            )[-1],
        ),
        patch(
            "job_hunter.cv_generate.run_cv_generate.read_editable_template_files",
            return_value={"resume.tex": "% t"},
        ),
    ):
        pdf_path = run_cv_generate(
            resume_path=resume_path,
            template_path=template_dir,
            output_dir=output_dir,
            tailor_cv=fake_tailor,
            compile_pdf=fake_compile,
        )

    assert pdf_path.name == "Acme_Corp_Site_Reliability_Engineer.pdf"
    assert pdf_path.is_file()
    assert description_path.read_text(encoding="utf-8") == "Build reliable systems."
