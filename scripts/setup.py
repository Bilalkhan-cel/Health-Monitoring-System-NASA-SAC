"""One-command bootstrap for AstroVital. Safe to run again at any time.

    python scripts/setup.py

Steps: check Python, create ``.venv`` (unless you are already inside a virtual
environment), install the pinned packages, create ``.env`` with fresh secrets,
fetch missing fonts and ML models, then run the quick self-check.

A failed download is reported and skipped; the app still starts and uses its
fallbacks. Only a failure to install the core web packages stops the setup.

Options:
    --no-venv       install into the Python that runs this script
    --skip-ml       skip the large ML packages (torch, transformers, faster-whisper)
    --skip-models   skip the model downloads (about 1 GB)

Standard library only: this runs before anything is installed.
"""

from __future__ import annotations

import argparse
import re
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap_env import ROOT, VENV_DIR, in_any_venv, venv_python  # noqa: E402

SUPPORTED = ((3, 10), (3, 13))
SECRET_KEYS = {
    "FLASK_SECRET_KEY": lambda: secrets.token_hex(32),
    "OPENHOME_BRIDGE_TOKEN": lambda: secrets.token_urlsafe(32),
    "DEVICE_TOKEN": lambda: secrets.token_urlsafe(32),
}


def say(message: str = "") -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def step(number: int, total: int, title: str) -> None:
    say(f"\n[{number}/{total}] {title}")


def check_python() -> bool:
    """Warn (never stop) when the interpreter is outside the tested range."""
    current = sys.version_info[:2]
    label = f"Python {current[0]}.{current[1]}"
    if SUPPORTED[0] <= current <= SUPPORTED[1]:
        say(f"  {label} is supported.")
        return True
    say(f"  {label} is outside the tested range 3.10 to 3.13. Continuing, but packages may not install.")
    return False


def ensure_venv(use_venv: bool) -> Path:
    """Return the Python to install into, creating ``.venv`` when needed."""
    if not use_venv or in_any_venv():
        say(f"  Using this Python: {sys.executable}")
        return Path(sys.executable)
    python = venv_python()
    if python.exists():
        say("  Virtual environment found: .venv")
        return python
    say("  Creating virtual environment: .venv")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    return python


def pip_install(python: Path, requirements: str) -> bool:
    """Install one requirements file. Returns False instead of raising."""
    command = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(ROOT / requirements)]
    say(f"  Installing {requirements} ...")
    return subprocess.call(command) == 0


def _is_empty(raw_value: str) -> bool:
    value = raw_value.strip()
    return not value or value.startswith("#")


def fill_secrets(text: str) -> tuple[str, list[str]]:
    """Fill every empty secret in ``.env`` text. Existing values are never changed."""
    filled: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if not match or match.group(1) not in SECRET_KEYS:
            continue
        if _is_empty(match.group(2)):
            key = match.group(1)
            lines[index] = f"{key}={SECRET_KEYS[key]()}"
            filled.append(key)
    return "\n".join(lines) + "\n", filled


def ensure_env_file(root: Path = ROOT) -> list[str]:
    """Create ``.env`` from ``.env.example`` and generate any missing secrets."""
    env_path, example_path = root / ".env", root / ".env.example"
    actions: list[str] = []
    if not env_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        actions.append("created .env from .env.example")
    updated, filled = fill_secrets(env_path.read_text(encoding="utf-8"))
    if filled:
        env_path.write_text(updated, encoding="utf-8")
        actions.append("generated " + ", ".join(filled))
    return actions


def run_script(python: Path, name: str, *args: str) -> int:
    return subprocess.call([str(python), str(ROOT / "scripts" / name), *args])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up AstroVital on this computer.")
    parser.add_argument("--no-venv", action="store_true", help="install into the current Python")
    parser.add_argument("--skip-ml", action="store_true", help="skip torch, transformers and faster-whisper")
    parser.add_argument("--skip-models", action="store_true", help="skip the model downloads (about 1 GB)")
    args = parser.parse_args(argv)
    total = 6
    notes: list[str] = []

    say("ASTROVITAL setup")
    step(1, total, "Python")
    check_python()

    step(2, total, "Environment")
    try:
        python = ensure_venv(use_venv=not args.no_venv)
    except (subprocess.CalledProcessError, OSError) as error:
        say(f"  Could not create .venv ({error}). Re-run with --no-venv to use this Python instead.")
        return 1

    step(3, total, "Packages")
    if not pip_install(python, "requirements-core.txt"):
        say("  The core packages did not install, so the app cannot start.")
        say("  Check your internet connection (or proxy settings) and run this script again.")
        return 1
    if args.skip_ml:
        notes.append("ML packages skipped: voice check-in and mood analysis use their fallbacks.")
    elif not pip_install(python, "requirements-ml.txt"):
        notes.append("ML packages did not install: voice check-in and mood analysis use their fallbacks. "
                     "Re-run this script when you are online.")

    step(4, total, "Settings (.env)")
    actions = ensure_env_file()
    say("  " + ("; ".join(actions) if actions else ".env already complete, nothing changed"))

    step(5, total, "Fonts and models")
    run_script(python, "fetch_assets.py")
    if args.skip_models or args.skip_ml:
        notes.append("Model downloads skipped: run python scripts/download_models.py when you want them.")
    else:
        run_script(python, "download_models.py")

    step(6, total, "Self-check")
    code = run_script(python, "verify.py", "--quick")

    say()
    for note in notes:
        say(f"Note: {note}")
    if code == 0:
        say("Setup complete. Start the app with:  python run.py")
    else:
        say("Setup finished with problems (see the self-check above).")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
