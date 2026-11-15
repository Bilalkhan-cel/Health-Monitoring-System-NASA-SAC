"""Make sure a script runs with the project's dependencies available.

``scripts/setup.py`` installs everything into ``<project>/.venv`` so the system
Python stays clean. ``run.py`` and the other scripts call ``ensure_environment``
so that plain ``python run.py`` still works without activating that environment.
Standard library only: this file must import before anything is installed.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
_GUARD = "ASTROVITAL_REEXEC"


def venv_python(venv_dir: Path = VENV_DIR) -> Path:
    """Path of the Python executable inside a virtual environment."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def in_any_venv() -> bool:
    return sys.prefix != sys.base_prefix


def in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def ensure_environment(probe: str = "flask") -> None:
    """Make sure the pinned packages are the ones in use.

    When ``.venv`` exists and the script was started with the system Python, the
    script is re-run inside ``.venv`` even if the system Python happens to have
    Flask, because only ``.venv`` holds the pinned versions. A virtual environment
    the user activated themself is respected.
    """
    python = venv_python()
    outside = not in_any_venv() and os.environ.get(_GUARD) != "1"
    if python.exists() and outside:
        env = dict(os.environ, **{_GUARD: "1"})
        try:
            code = subprocess.call([str(python), *sys.argv], env=env)
        except KeyboardInterrupt:
            code = 130
        raise SystemExit(code)
    if importlib.util.find_spec(probe) is None:
        sys.stderr.write("AstroVital is not set up yet. Run:  python scripts/setup.py\n")
        raise SystemExit(1)
