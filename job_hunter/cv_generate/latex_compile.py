"""Compile the working LaTeX resume into a PDF."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_PDFLATEX_CANDIDATE_PATHS = (
    Path("/Library/TeX/texbin/pdflatex"),
    Path("/usr/local/texlive/2024/bin/universal-darwin/pdflatex"),
    Path("/usr/local/texlive/2023/bin/universal-darwin/pdflatex"),
)


def _candidate_pdflatex_paths() -> list[Path]:
    paths: list[Path] = []
    env_override = os.environ.get("JOB_HUNTER_PDFLATEX", "").strip()
    if env_override:
        paths.append(Path(env_override).expanduser())
    paths.extend(_PDFLATEX_CANDIDATE_PATHS)
    which_result = shutil.which("pdflatex")
    if which_result:
        paths.append(Path(which_result))
    return paths


def find_pdflatex(*, explicit_path: str | None = None) -> str:
    """
    Resolve a ``pdflatex`` executable.

    Checks ``explicit_path``, ``JOB_HUNTER_PDFLATEX``, ``PATH``, and common macOS
    MacTeX / BasicTeX locations.
    """
    if explicit_path:
        resolved = Path(explicit_path).expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
        raise FileNotFoundError(f"pdflatex not executable: {resolved}")

    for candidate in _candidate_pdflatex_paths():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())

    raise FileNotFoundError(
        "pdflatex not found. Install a LaTeX distribution (e.g. MacTeX or BasicTeX) "
        "and ensure pdflatex is on PATH, or install Tectonic (`brew install tectonic`). "
        "On macOS after BasicTeX: eval \"$(/usr/libexec/path_helper)\""
    )


def find_tectonic(*, explicit_path: str | None = None) -> str:
    """Resolve a ``tectonic`` executable."""
    if explicit_path:
        resolved = Path(explicit_path).expanduser().resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
        raise FileNotFoundError(f"tectonic not executable: {resolved}")

    env_override = os.environ.get("JOB_HUNTER_TECTONIC", "").strip()
    if env_override:
        candidate = Path(env_override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())

    which_result = shutil.which("tectonic")
    if which_result:
        return which_result

    raise FileNotFoundError("tectonic not found")


def resolve_latex_compilers(
    *,
    pdflatex_path: str | None = None,
    prefer: str | None = None,
) -> list[tuple[str, str]]:
    """
    Return an ordered list of ``(engine, executable_path)`` to try.

    Default order: Tectonic first (auto-downloads LaTeX packages), then pdflatex.
    Explicit ``prefer`` selects a single engine.
    """
    preference = (prefer or os.environ.get("JOB_HUNTER_LATEX_ENGINE", "")).strip().lower()

    if preference == "tectonic":
        return [("tectonic", find_tectonic())]
    if preference == "pdflatex":
        return [("pdflatex", find_pdflatex(explicit_path=pdflatex_path))]

    compilers: list[tuple[str, str]] = []
    try:
        compilers.append(("tectonic", find_tectonic()))
    except FileNotFoundError:
        pass
    try:
        compilers.append(("pdflatex", find_pdflatex(explicit_path=pdflatex_path)))
    except FileNotFoundError:
        pass
    if not compilers:
        raise FileNotFoundError(
            "No LaTeX compiler found. Install Tectonic (`brew install tectonic`) "
            "or a TeX distribution with pdflatex."
        )
    return compilers


def resolve_latex_compiler(
    *,
    pdflatex_path: str | None = None,
    prefer: str | None = None,
) -> tuple[str, str]:
    """Return the first compiler from :func:`resolve_latex_compilers`."""
    return resolve_latex_compilers(pdflatex_path=pdflatex_path, prefer=prefer)[0]


def _run_pdflatex(executable: str, *, cwd: Path, runs: int) -> None:
    command = [
        executable,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "resume.tex",
    ]
    for _ in range(max(runs, 1)):
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"pdflatex failed in {cwd}: {stderr}")


def _run_tectonic(executable: str, *, cwd: Path) -> None:
    command = [executable, "resume.tex"]
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"tectonic failed in {cwd}: {stderr}")


def _compile_with_engine(engine: str, executable: str, *, cwd: Path, runs: int) -> None:
    if engine == "pdflatex":
        _run_pdflatex(executable, cwd=cwd, runs=runs)
    else:
        _run_tectonic(executable, cwd=cwd)


def compile_resume_pdf(
    *,
    working_dir: Path,
    runs: int = 2,
    pdflatex_path: str | None = None,
    latex_engine: str | None = None,
) -> Path:
    """
    Compile ``resume.tex`` inside ``working_dir``.

    Tries Tectonic before pdflatex by default. On failure, attempts the next
    available engine (unless ``latex_engine`` pins a single engine).
    Returns the path to ``resume.pdf``.
    """
    cwd = working_dir.expanduser().resolve()
    main_tex = cwd / "resume.tex"
    if not main_tex.is_file():
        raise FileNotFoundError(f"resume.tex not found in {cwd}")

    compilers = resolve_latex_compilers(
        pdflatex_path=pdflatex_path,
        prefer=latex_engine,
    )
    errors: list[str] = []
    for engine, executable in compilers:
        try:
            _compile_with_engine(engine, executable, cwd=cwd, runs=runs)
            pdf_path = cwd / "resume.pdf"
            if not pdf_path.is_file():
                raise RuntimeError(f"{engine} did not produce {pdf_path}")
            return pdf_path
        except RuntimeError as exc:
            errors.append(f"{engine}: {exc}")
            if latex_engine:
                raise
            continue

    joined = "\n\n".join(errors)
    raise RuntimeError(
        "All LaTeX compilers failed. "
        "BasicTeX often needs extra packages; Tectonic (`brew install tectonic`) "
        f"usually works without manual `tlmgr install`. Details:\n{joined}"
    )
