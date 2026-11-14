"""Environment-aware advice for each body system (Section 9.4a).

The environment changes wording, exercise options and the comms delay. It never
changes the clinical thresholds.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from config import BASE_DIR

from .summary import load_environments

PATH = BASE_DIR / "config" / "recommendations.yaml"


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def exercise_text(environment: str) -> str:
    names = load()["exercise_names"]
    options = load_environments().get(environment, {}).get("exercise", [])
    words = [names.get(option, option) for option in options]
    if len(words) > 1:
        return ", ".join(words[:-1]) + " and " + words[-1]
    return words[0] if words else "logged device sessions"


def _fill(text: str, environment: str, delay_text: str) -> str:
    note = load_environments().get(environment, {}).get("advice_notes", "")
    return text.format(env_note=note, exercise=exercise_text(environment), delay=delay_text)


def steps(system: str, status: str | None, environment: str, delay_text: str) -> list[str]:
    """Three plain steps for a system at a status."""
    table = load()[system]
    return [_fill(step, environment, delay_text) for step in table[status or "STABLE"]]


def protocol(environment: str, delay_text: str) -> list[str]:
    return [_fill(step, environment, delay_text) for step in load()["protocol"]]
