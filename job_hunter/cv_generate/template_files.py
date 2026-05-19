"""Read and write LaTeX files under the working CV template directory."""

from __future__ import annotations

from pathlib import Path

EDITABLE_RELATIVE_PATHS = (
    "resume.tex",
    "sections/objective.tex",
    "sections/skills.tex",
    "sections/experience.tex",
    "sections/education.tex",
    "sections/previous.tex",
    "sections/Accomplishments.tex",
)


def read_editable_template_files(working_dir: Path) -> dict[str, str]:
    """Load editable LaTeX paths relative to ``working_dir``."""
    files: dict[str, str] = {}
    for relative in EDITABLE_RELATIVE_PATHS:
        path = working_dir / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing template file: {path}")
        files[relative] = path.read_text(encoding="utf-8")
    return files


def write_tailored_files(working_dir: Path, files: dict[str, str]) -> None:
    """Write tailored LaTeX files, rejecting path traversal."""
    root = working_dir.resolve()
    for relative, content in files.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"Unsafe template path: {relative}")
        destination = (root / relative_path).resolve()
        if not str(destination).startswith(str(root)):
            raise ValueError(f"Unsafe template path: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
