"""Command-line entry point for job-hunter."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path

from job_hunter.agent_cli import DEFAULT_AGENT_BINARY
from job_hunter.paths import (
    default_filtered_jobs_csv_path,
    default_jobs_export_csv_path,
    default_position_yaml_path,
    default_query_yaml_path,
    default_resume_yaml_path,
)


def _iso_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def _run_resume_ingest(arguments: argparse.Namespace) -> int:
    for module_name in ("dateutil", "pypdf"):
        try:
            __import__(module_name)
        except ImportError as exc:
            raise SystemExit(
                f"resume:ingest requires {module_name!r}. "
                "From the repo root: pip install -e \".[dev]\""
            ) from exc

    from job_hunter.resume_ingest.normalize import normalize_extracted_resume
    from job_hunter.resume_ingest.pdf_loader import load_pdf_text
    from job_hunter.resume_ingest.resume_parser import parse_resume_with_gemini_cli
    from job_hunter.resume_ingest.text_cleaner import clean_resume_text
    from job_hunter.resume_ingest.yaml_writer import build_resume_document, write_resume_yaml

    pdf_path = arguments.pdf_path.expanduser().resolve()
    output_path = arguments.output.expanduser().resolve()

    raw_text = load_pdf_text(pdf_path)
    cleaned = clean_resume_text(raw_text)
    if arguments.debug:
        print("[debug] cleaned text length:", len(cleaned))

    extracted = parse_resume_with_gemini_cli(
        cleaned,
        gemini_binary=arguments.gemini_binary,
        model=arguments.model,
        debug=arguments.debug,
    )
    normalized = normalize_extracted_resume(extracted)
    document = build_resume_document(
        normalized,
        source_file=str(pdf_path),
    )
    write_resume_yaml(document, output_path)

    print(output_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-hunter", description="Agentic job-hunting CLI utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "resume:ingest",
        help="Extract a PDF resume via Antigravity CLI and write resume.yaml",
    )
    ingest.add_argument(
        "pdf_path",
        type=Path,
        help="Path to the resume PDF (e.g. ./resume.pdf)",
    )
    ingest.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_resume_yaml_path(),
        help="Output YAML path (default: ./data/resume.yaml)",
    )
    ingest.add_argument(
        "--debug",
        action="store_true",
        help="Print diagnostic details (including excerpt lengths); does not print full resume unless parser logs it",
    )
    ingest.add_argument(
        "--gemini-binary",
        default=DEFAULT_AGENT_BINARY,
        help="Antigravity CLI (agy) or legacy Gemini CLI executable (default: agy)",
    )
    ingest.add_argument(
        "--model",
        default="flash",
        help="Agent CLI model alias or id (default: flash)",
    )
    ingest.set_defaults(func=_run_resume_ingest)

    def _run_listings_export(arguments: argparse.Namespace) -> int:
        from job_hunter.job_listings.run_listings_export import run_listings_export

        csv_path = run_listings_export(
            weblist_path=arguments.weblist,
            position_path=arguments.position,
            query_output_path=arguments.query_output,
            csv_output_path=arguments.csv_output,
            debug=arguments.debug,
        )
        print(csv_path)
        return 0

    listings = subparsers.add_parser(
        "listings:export",
        help="Build query.yaml from weblist + position, fetch boards, filter, write jobs_export.csv",
    )
    listings.add_argument(
        "--weblist",
        type=Path,
        default=None,
        help="Weblist YAML (default: data/weblist.yaml if it exists, else data/weblist.example.yaml)",
    )
    listings.add_argument(
        "--position",
        type=Path,
        default=None,
        help="Position criteria YAML (default: data/position.yaml if it exists, else data/position.example.yaml)",
    )
    listings.add_argument(
        "--query-output",
        type=Path,
        default=None,
        help=f"Output query plan YAML (default: {default_query_yaml_path()})",
    )
    listings.add_argument(
        "--csv-output",
        type=Path,
        default=None,
        help=f"Output CSV path (default: {default_jobs_export_csv_path()})",
    )
    listings.add_argument(
        "--debug",
        action="store_true",
        help="Print per-source fetch diagnostics to stderr",
    )
    listings.set_defaults(func=_run_listings_export)

    def _run_jobs_filter(arguments: argparse.Namespace) -> int:
        from job_hunter.job_filtering.run_job_filtering import run_job_filtering

        logging.basicConfig(
            level=logging.DEBUG if arguments.debug else logging.INFO,
            format="%(levelname)s %(message)s",
            stream=sys.stderr,
            force=True,
        )

        output_path = run_job_filtering(
            target_date=arguments.date,
            jobs_csv_path=arguments.jobs_csv,
            resume_path=arguments.resume,
            position_path=arguments.position,
            output_path=arguments.output,
            gemini_binary=arguments.gemini_binary,
            model=arguments.model,
            max_description_chars=arguments.max_description_chars,
            debug=arguments.debug,
        )
        print(output_path)
        return 0

    filtering = subparsers.add_parser(
        "jobs:filter",
        help="AI-filter jobs_export.csv rows added on a specific date",
    )
    filtering.add_argument(
        "--date",
        type=_iso_date,
        required=True,
        help="Only evaluate rows whose added_to_list_date matches this YYYY-MM-DD date",
    )
    filtering.add_argument(
        "--jobs-csv",
        type=Path,
        default=None,
        help=f"Input jobs CSV (default: {default_jobs_export_csv_path()})",
    )
    filtering.add_argument(
        "--resume",
        type=Path,
        default=default_resume_yaml_path(),
        help=f"Resume YAML (default: {default_resume_yaml_path()})",
    )
    filtering.add_argument(
        "--position",
        type=Path,
        default=default_position_yaml_path(),
        help=f"Position criteria YAML (default: {default_position_yaml_path()})",
    )
    filtering.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Filtered CSV output path (default: {default_filtered_jobs_csv_path('YYYY-MM-DD')})",
    )
    filtering.add_argument(
        "--gemini-binary",
        default=DEFAULT_AGENT_BINARY,
        help="Antigravity CLI (agy) or legacy Gemini CLI executable (default: agy)",
    )
    filtering.add_argument(
        "--model",
        default="flash",
        help="Agent CLI model alias or id (default: flash)",
    )
    filtering.add_argument(
        "--max-description-chars",
        type=int,
        default=30_000,
        help="Maximum job_description characters sent to Gemini per job (default: 30000)",
    )
    filtering.add_argument(
        "--debug",
        action="store_true",
        help="Print per-job fetch and agent CLI diagnostics to stderr",
    )
    filtering.set_defaults(func=_run_jobs_filter)

    def _run_cv_generate(arguments: argparse.Namespace) -> int:
        from job_hunter.cv_generate.run_cv_generate import run_cv_generate

        logging.basicConfig(
            level=logging.DEBUG if arguments.debug else logging.INFO,
            format="%(levelname)s %(message)s",
            stream=sys.stderr,
            force=True,
        )

        pdf_path = run_cv_generate(
            resume_path=arguments.resume,
            template_path=arguments.template,
            output_dir=arguments.output_dir,
            gemini_binary=arguments.gemini_binary,
            model=arguments.model,
            debug=arguments.debug,
            pdflatex_path=arguments.pdflatex,
            latex_engine=arguments.latex_engine,
        )
        print(pdf_path)
        return 0

    cv_generate = subparsers.add_parser(
        "cv:generate",
        help="Tailor LaTeX CV from resume.yaml and target_job_url, compile to PDF",
    )
    cv_generate.add_argument(
        "--resume",
        type=Path,
        default=default_resume_yaml_path(),
        help=f"Resume YAML with resume_max_pages and target_job_url (default: {default_resume_yaml_path()})",
    )
    cv_generate.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Source LaTeX template directory (default: data/cv_template)",
    )
    cv_generate.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output PDF (default: data/cv)",
    )
    cv_generate.add_argument(
        "--gemini-binary",
        default=DEFAULT_AGENT_BINARY,
        help="Antigravity CLI (agy) or legacy Gemini CLI executable (default: agy)",
    )
    cv_generate.add_argument(
        "--model",
        default="flash",
        help="Agent CLI model alias or id (default: flash)",
    )
    cv_generate.add_argument(
        "--debug",
        action="store_true",
        help="Print agent CLI diagnostics to stderr",
    )
    cv_generate.add_argument(
        "--pdflatex",
        dest="pdflatex",
        default=None,
        help="Path to pdflatex (default: PATH, then /Library/TeX/texbin/pdflatex)",
    )
    cv_generate.add_argument(
        "--latex-engine",
        choices=("pdflatex", "tectonic"),
        default=None,
        help="LaTeX engine (default: pdflatex if found, else tectonic)",
    )
    cv_generate.set_defaults(func=_run_cv_generate)

    namespace = parser.parse_args(argv)
    handler = getattr(namespace, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(namespace))


if __name__ == "__main__":
    sys.exit(main())
