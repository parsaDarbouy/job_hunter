"""Copy tracked LaTeX template into the working directory."""

from __future__ import annotations

import shutil
from pathlib import Path


def copy_cv_template(*, source_dir: Path, working_dir: Path) -> None:
    """
    Replace ``working_dir`` with a fresh copy of ``source_dir``.

    Raises FileNotFoundError when the source tree is missing.
    """
    source = source_dir.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"CV template directory not found: {source}")

    destination = working_dir.expanduser().resolve()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
