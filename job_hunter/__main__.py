"""``python -m job_hunter`` entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REEXEC_ENV = "JOB_HUNTER_VENV_REEXEC"
# PyYAML is required by most commands; resume:ingest additionally needs dateutil and pypdf.
_CORE_DEPENDENCY_MODULES = ("yaml",)


def _project_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    candidate = package_dir.parent
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def _venv_python(project_root: Path) -> Path | None:
    for relative in (Path(".venv/bin/python"), Path(".venv/bin/python3")):
        candidate = project_root / relative
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def _missing_project_dependencies() -> list[str]:
    missing: list[str] = []
    for module_name in _CORE_DEPENDENCY_MODULES:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def _reexec_with_project_venv_if_needed() -> None:
    if os.environ.get(_REEXEC_ENV):
        return

    project_root = _project_root()
    if project_root is None:
        return

    venv_python = _venv_python(project_root)
    if venv_python is None:
        return

    if Path(sys.executable).resolve() == venv_python:
        return

    if not _missing_project_dependencies():
        return

    os.environ[_REEXEC_ENV] = "1"
    os.execv(
        str(venv_python),
        [str(venv_python), "-m", "job_hunter", *sys.argv[1:]],
    )


def _dependency_hint(project_root: Path | None) -> str:
    root_line = f"  cd {project_root}" if project_root else "  cd /path/to/job_hunter"
    return (
        "Project dependencies are not installed for this Python.\n"
        f"{root_line}\n"
        "  python3 -m venv .venv && source .venv/bin/activate\n"
        "  pip install -e \".[dev]\"\n"
        "Then run: .venv/bin/python -m job_hunter …"
    )


def main() -> int:
    _reexec_with_project_venv_if_needed()

    missing = _missing_project_dependencies()
    if missing:
        print(_dependency_hint(_project_root()), file=sys.stderr)
        print(f"Missing modules: {', '.join(missing)}", file=sys.stderr)
        return 1

    from job_hunter.cli import main as cli_main

    return int(cli_main())


if __name__ == "__main__":
    raise SystemExit(main())
