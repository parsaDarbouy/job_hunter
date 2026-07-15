"""Orchestrate tailored CV PDF generation."""

from __future__ import annotations

import logging
import sys
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

import yaml

from job_hunter.cv_generate.experience_notes import collect_experience_notes
from job_hunter.cv_generate.latex_text_metrics import cap_latex_item_bullets, count_latex_item_bullets
from job_hunter.cv_generate.filename import build_cv_pdf_filename
from job_hunter.agent_cli import DEFAULT_AGENT_BINARY
from job_hunter.cv_generate.gemini_ats import assess_resume_vs_job_with_gemini_cli
from job_hunter.cv_generate.gemini_tailor import GeminiCvTailorResult, tailor_cv_with_gemini_cli
from job_hunter.cv_generate.job_description import fetch_and_save_job_description
from job_hunter.cv_generate.latex_compile import compile_resume_pdf
from job_hunter.cv_generate.template_copy import copy_cv_template
from job_hunter.cv_generate.template_files import read_editable_template_files, write_tailored_files
from job_hunter.cv_generate.layout_constraints import CvLayoutConstraints, parse_cv_layout_constraints
from job_hunter.cv_generate.validate_layout import (
    collect_layout_violations,
    format_layout_violations_error,
    layout_violation_parts,
    validate_tailored_layout,
)
from job_hunter.cv_generate.validate_previous import validate_previous_experience_format
from job_hunter.cv_generate.validate_tailored import validate_employers_in_latex
from job_hunter.paths import (
    cv_output_dir,
    default_cv_template_path,
    default_resume_yaml_path,
    job_description_path,
    working_cv_template_dir,
)
from job_hunter.resume_ingest.resume_settings import (
    parse_about_me_note,
    parse_resume_max_pages,
    parse_target_job_url,
)

_logger = logging.getLogger(__name__)

# Initial tailor attempt plus this many retries after cv_layout validation failures.
_LAYOUT_VIOLATION_MAX_RETRIES = 3


def _cap_experience_bullets(
    *,
    tailored_files: dict[str, str],
    cv_layout: CvLayoutConstraints,
    resume_max_pages: int,
    run_id: str,
) -> dict[str, str]:
    experience_tex_key = "sections/experience.tex"
    max_experience_bullets = cv_layout.max_total_experience_bullets(resume_max_pages)
    if experience_tex_key not in tailored_files:
        return tailored_files
    before_count = count_latex_item_bullets(tailored_files[experience_tex_key])
    capped_tex = cap_latex_item_bullets(tailored_files[experience_tex_key], max_experience_bullets)
    if count_latex_item_bullets(capped_tex) >= before_count:
        return tailored_files
    _logger.info(
        "cv_generate.cap_experience_bullets run_id=%s before=%s max=%s",
        run_id,
        before_count,
        max_experience_bullets,
    )
    updated = dict(tailored_files)
    updated[experience_tex_key] = capped_tex
    return updated


def run_cv_generate(
    *,
    resume_path: Path | None = None,
    template_path: Path | None = None,
    output_dir: Path | None = None,
    gemini_binary: str = DEFAULT_AGENT_BINARY,
    model: str = "flash",
    debug: bool = False,
    pdflatex_path: str | None = None,
    latex_engine: str | None = None,
    tailor_cv: Callable[..., GeminiCvTailorResult] = tailor_cv_with_gemini_cli,
    compile_pdf: Callable[..., Path] = compile_resume_pdf,
    assess_ats: Callable[..., object] = assess_resume_vs_job_with_gemini_cli,
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
    about_me_note = parse_about_me_note(resume_document)

    layout_revision_message: str | None = None
    tailor_result: GeminiCvTailorResult | None = None
    tailored_files: dict[str, str] = {}
    max_layout_attempts = 1 + _LAYOUT_VIOLATION_MAX_RETRIES

    for layout_attempt in range(max_layout_attempts):
        tailor_result = tailor_cv(
            resume_yaml_text=resume_yaml_text,
            job_description_text=job_description_text,
            resume_max_pages=resume_max_pages,
            template_files=template_files,
            experience_note_hints=experience_note_hints,
            about_me_note=about_me_note,
            cv_layout_constraints=cv_layout,
            layout_revision_message=layout_revision_message,
            gemini_binary=gemini_binary,
            model=model,
            debug=debug,
        )
        tailored_files = _cap_experience_bullets(
            tailored_files=dict(tailor_result.files),
            cv_layout=cv_layout,
            resume_max_pages=resume_max_pages,
            run_id=run_id,
        )
        validate_employers_in_latex(
            resume_document=resume_document,
            files=tailored_files,
        )
        validate_previous_experience_format(tailored_files)
        layout_violations = collect_layout_violations(
            files=tailored_files,
            layout=cv_layout,
            resume_max_pages=resume_max_pages,
        )
        if not layout_violations:
            break
        if layout_attempt >= max_layout_attempts - 1:
            raise ValueError(format_layout_violations_error(layout_violations))

        retry_number = layout_attempt + 1
        parts = layout_violation_parts(layout_violations)
        layout_revision_message = format_layout_violations_error(layout_violations)
        _logger.warning(
            "cv_generate.layout_retry run_id=%s retry=%s/%s parts=%s",
            run_id,
            retry_number,
            _LAYOUT_VIOLATION_MAX_RETRIES,
            " | ".join(parts),
        )
        for violation in layout_violations:
            _logger.warning(
                "cv_generate.layout_retry_part run_id=%s retry=%s/%s part=%s detail=%s",
                run_id,
                retry_number,
                _LAYOUT_VIOLATION_MAX_RETRIES,
                violation.part_label,
                violation.message,
            )

    assert tailor_result is not None
    write_tailored_files(working_dir, tailored_files)

    built_pdf = compile_pdf(
        working_dir=working_dir,
        pdflatex_path=pdflatex_path,
        latex_engine=latex_engine,
    )
    relative_pdf_path = build_cv_pdf_filename(
        company_name=tailor_result.company_name,
        position_title=tailor_result.position_title,
    )
    destination = pdf_output_dir / relative_pdf_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_pdf, destination)

    # After generating the tailored CV, run an ATS-style comparison of the
    # candidate resume (resume.yaml) against the target job description.
    try:
        ats_report = assess_ats(
            resume_yaml_text=resume_yaml_text,
            job_description_text=job_description_text,
            gemini_binary=gemini_binary,
            model=model,
            debug=debug,
        )
        # Keep this short and clearly separated from normal logs.
        missing = ", ".join(getattr(ats_report, "missing_keywords", []) or [])
        if missing:
            missing_line = f"Missing keywords: {missing}"
        else:
            missing_line = "Missing keywords: None found"
        note = str(getattr(ats_report, "note", "") or "").strip()
        note_line = f"Resume lacks: {note}" if note else ""
        print("\n==================== ATS REPORT ====================", file=sys.stderr)
        print(f"Score: {getattr(ats_report, 'score', 0)}/100", file=sys.stderr)
        print(missing_line, file=sys.stderr)
        if note_line:
            print(note_line, file=sys.stderr)
        print("======================================================\n", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - ATS is best-effort
        _logger.warning("cv_generate.ats_failed run_id=%s error=%s", run_id, exc)

    elapsed = time.monotonic() - started
    _logger.info(
        "cv_generate.complete run_id=%s pdf=%s job_description=%s elapsed_seconds=%.2f",
        run_id,
        destination,
        description_file,
        elapsed,
    )
    return destination.resolve()
