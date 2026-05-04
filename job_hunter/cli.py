"""Command-line entry point for job-hunter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from job_hunter.paths import default_resume_yaml_path
from job_hunter.resume_ingest.normalize import normalize_extracted_resume
from job_hunter.resume_ingest.pdf_loader import load_pdf_text
from job_hunter.resume_ingest.resume_parser import parse_resume_with_gemini_cli
from job_hunter.resume_ingest.text_cleaner import clean_resume_text
from job_hunter.resume_ingest.yaml_writer import build_resume_document, write_resume_yaml


def _run_resume_ingest(arguments: argparse.Namespace) -> int:
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
        help="Extract a PDF resume via Gemini CLI and write resume.yaml",
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
        default="gemini",
        help="Gemini CLI executable name or path (default: gemini)",
    )
    ingest.add_argument(
        "--model",
        default="flash",
        help="Gemini CLI model alias or id (default: flash)",
    )
    ingest.set_defaults(func=_run_resume_ingest)

    namespace = parser.parse_args(argv)
    handler = getattr(namespace, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(namespace))


if __name__ == "__main__":
    sys.exit(main())
