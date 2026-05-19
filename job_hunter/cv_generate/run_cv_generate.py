"""Orchestrate tailored CV PDF generation."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

import yaml

from job_hunter.cv_generate.experience_notes import collect_experience_notes
from job_hunter.cv_generate.filename import build_cv_pdf_filename
from job_hunter.cv_generate.gemini_tailor import GeminiCvTailorResult, tailor_cv_with_gemini_cli
from job_hunter.cv_generate.job_description import fetch_and_save_job_description
from job_hunter.cv_generate.latex_compile import compile_resume_pdf
from job_hunter.cv_generate.template_copy import copy_cv_template
from job_hunter.cv_generate.template_files import read_editable_template_files, write_tailored_files
from job_hunter.cv_generate.layout_constraints import parse_cv_layout_constraints
from job_hunter.cv_generate.validate_layout import validate_tailored_layout
from job_hunter.cv_generate.validate_tailored import validate_employers_in_latex
from job_hunter.paths import (
    cv_output_dir,
    default_cv_template_path,
    default_resume_yaml_path,
    job_description_path,
    working_cv_template_dir,
)
from job_hunter.resume_ingest.resume_settings import parse_resume_max_pages, parse_target_job_url

_logger = logging.getLogger(__name__)


def run_cv_generate(
    *,
    resume_path: Path | None = None,
    template_path: Path | None = None,
    output_dir: Path | None = None,
    gemini_binary: str = "gemini",
    model: str = "flash",
    debug: bool = False,
    pdflatex_path: str | None = None,
    latex_engine: str | None = None,
    tailor_cv: Callable[..., GeminiCvTailorResult] = tailor_cv_with_gemini_cli,
    compile_pdf: Callable[..., Path] = compile_resume_pdf,
) -> Path:
    """
    Generate a tailored CV PDF from resume.yaml and target_job_url.

    Returns the absolute path to the output PDF.
    """
    run_id = uuid.uuid4().hex[:12]
    started = time.monotonic()

    resume_file = (resume_path or default_resume_yaml_path()).expanduser().resolve()
    source_template = (template_path or default_cv_template_path()).expanduser().resolve()
    pdf_output_dir = (output_dir or cv_output_dir()).expanduser().resolve()
    working_dir = working_cv_template_dir().expanduser().resolve()
    description_file = job_description_path().expanduser().resolve()

    if not resume_file.is_file():
        raise FileNotFoundError(f"Resume YAML not found: {resume_file}")

    resume_document = yaml.safe_load(resume_file.read_text(encoding="utf-8"))
    if not isinstance(resume_document, dict):
        raise ValueError(f"Resume YAML must be a mapping: {resume_file}")

    resume_max_pages = parse_resume_max_pages(resume_document)
    target_job_url = parse_target_job_url(resume_document)
    cv_layout = parse_cv_layout_constraints(resume_document)
    resume_yaml_text = resume_file.read_text(encoding="utf-8")

    _logger.info(
        "cv_generate.start run_id=%s resume=%s template=%s output_dir=%s max_pages=%s",
        run_id,
        resume_file,
        source_template,
        pdf_output_dir,
        resume_max_pages,
    )

    copy_cv_template(source_dir=source_template, working_dir=working_dir)
    job_description_text = fetch_and_save_job_description(
        job_url=target_job_url,
        output_path=description_file,
    )
    template_files = read_editable_template_files(working_dir)

    experience_note_hints = collect_experience_notes(resume_document)

    tailor_result = tailor_cv(
        resume_yaml_text=resume_yaml_text,
        job_description_text=job_description_text,
        resume_max_pages=resume_max_pages,
        template_files=template_files,
        experience_note_hints=experience_note_hints,
        cv_layout_constraints=cv_layout,
        gemini_binary=gemini_binary,
        model=model,
        debug=debug,
    )
    validate_employers_in_latex(
        resume_document=resume_document,
        files=tailor_result.files,
    )
    validate_tailored_layout(
        files=tailor_result.files,
        layout=cv_layout,
        resume_max_pages=resume_max_pages,
    )
    write_tailored_files(working_dir, tailor_result.files)

    built_pdf = compile_pdf(
        working_dir=working_dir,
        pdflatex_path=pdflatex_path,
        latex_engine=latex_engine,
    )
    pdf_output_dir.mkdir(parents=True, exist_ok=True)
    output_name = build_cv_pdf_filename(
        company_name=tailor_result.company_name,
        position_title=tailor_result.position_title,
    )
    destination = pdf_output_dir / output_name
    shutil.copy2(built_pdf, destination)

    elapsed = time.monotonic() - started
    _logger.info(
        "cv_generate.complete run_id=%s pdf=%s job_description=%s elapsed_seconds=%.2f",
        run_id,
        destination,
        description_file,
        elapsed,
    )
    return destination.resolve()
