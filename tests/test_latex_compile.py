"""Tests for LaTeX PDF compilation discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from job_hunter.cv_generate.latex_compile import (
    find_pdflatex,
    find_tectonic,
    resolve_latex_compiler,
)


def test_find_pdflatex_explicit_path(tmp_path: Path) -> None:
    binary = tmp_path / "pdflatex"
    binary.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    binary.chmod(0o755)
    assert find_pdflatex(explicit_path=str(binary)) == str(binary.resolve())


def test_resolve_latex_compiler_falls_back_to_tectonic() -> None:
    with patch(
        "job_hunter.cv_generate.latex_compile.find_pdflatex",
        side_effect=FileNotFoundError("missing"),
    ):
        with patch(
            "job_hunter.cv_generate.latex_compile.find_tectonic",
            return_value="/opt/homebrew/bin/tectonic",
        ):
            engine, path = resolve_latex_compiler()
    assert engine == "tectonic"
    assert path == "/opt/homebrew/bin/tectonic"


def test_resolve_latex_compiler_prefers_tectonic_when_both_available() -> None:
    with patch(
        "job_hunter.cv_generate.latex_compile.find_pdflatex",
        return_value="/Library/TeX/texbin/pdflatex",
    ):
        with patch(
            "job_hunter.cv_generate.latex_compile.find_tectonic",
            return_value="/opt/homebrew/bin/tectonic",
        ):
            engine, path = resolve_latex_compiler()
    assert engine == "tectonic"
    assert path == "/opt/homebrew/bin/tectonic"


def test_compile_resume_pdf_falls_back_to_tectonic(tmp_path: Path) -> None:
    from job_hunter.cv_generate.latex_compile import compile_resume_pdf

    (tmp_path / "resume.tex").write_text("\\documentclass{article}\n", encoding="utf-8")

    def fail_pdflatex(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("pdflatex failed: missing sty")

    def ok_tectonic(executable: str, *, cwd: Path) -> None:
        (cwd / "resume.pdf").write_bytes(b"%PDF")

    with patch(
        "job_hunter.cv_generate.latex_compile.resolve_latex_compilers",
        return_value=[
            ("pdflatex", "/Library/TeX/texbin/pdflatex"),
            ("tectonic", "/opt/homebrew/bin/tectonic"),
        ],
    ):
        with patch(
            "job_hunter.cv_generate.latex_compile._run_pdflatex",
            side_effect=fail_pdflatex,
        ):
            with patch(
                "job_hunter.cv_generate.latex_compile._run_tectonic",
                side_effect=ok_tectonic,
            ):
                pdf_path = compile_resume_pdf(working_dir=tmp_path)

    assert pdf_path == tmp_path / "resume.pdf"


def test_find_pdflatex_macos_path_when_executable(tmp_path: Path) -> None:
    fake = tmp_path / "pdflatex"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    with patch(
        "job_hunter.cv_generate.latex_compile._PDFLATEX_CANDIDATE_PATHS",
        (fake,),
    ):
        with patch("job_hunter.cv_generate.latex_compile.shutil.which", return_value=None):
            assert find_pdflatex() == str(fake.resolve())


def test_find_pdflatex_raises_when_missing() -> None:
    with patch("job_hunter.cv_generate.latex_compile.shutil.which", return_value=None):
        with patch(
            "job_hunter.cv_generate.latex_compile._candidate_pdflatex_paths",
            return_value=[],
        ):
            with pytest.raises(FileNotFoundError, match="pdflatex not found"):
                find_pdflatex()
