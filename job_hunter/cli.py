"""Command-line entry point for job-hunter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from job_hunter.paths import default_jobs_export_csv_path, default_query_yaml_path, default_resume_yaml_path
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

    def _run_listings_export(arguments: argparse.Namespace) -> int:
        from job_hunter.job_listings.run_listings_export import run_listings_export

        csv_path = run_listings_export(
            weblist_path=arguments.weblist,
            position_path=arguments.position,
            query_output_path=arguments.query_output,
            csv_output_path=arguments.csv_output,
            debug=arguments.debug,
            gemini_binary=arguments.listings_gemini_binary,
            gemini_model=arguments.listings_gemini_model,
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
    listings.add_argument(
        "--gemini-binary",
        dest="listings_gemini_binary",
        default=None,
        help="Override Gemini CLI for location rescue (fallback: gemini_binary in position YAML, then gemini)",
    )
    listings.add_argument(
        "--gemini-model",
        dest="listings_gemini_model",
        default=None,
        help="Override Gemini model for location rescue (fallback: position YAML, then flash)",
    )
    listings.set_defaults(func=_run_listings_export)

    namespace = parser.parse_args(argv)
    handler = getattr(namespace, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(namespace))


if __name__ == "__main__":
    sys.exit(main())
