"""Display units (Settings → Units). Data is always stored in °C and mg/dL (Section 16).

The preference is read once per request for the logged-in astronaut and cached on ``g``.
Outside a request (the OpenHome context, scripts, tests without a login) the stored units
are used.
"""

from __future__ import annotations

from flask import g, has_request_context

GLUCOSE_FACTOR = 18.016  # mg/dL per mmol/L
DEFAULTS = {"temp": "C", "glucose": "mg/dL"}


def current_units() -> dict[str, str]:
    if not has_request_context():
        return DEFAULTS
    cached = getattr(g, "astro_units", None)
    if cached is not None:
        return cached
    units = dict(DEFAULTS)
    from ..auth.services import current_crew
    from ..models import UserSettings

    crew = current_crew()
    if crew is not None:
        row = UserSettings.query.filter_by(astronaut_id=crew.id).first()
        if row is not None:
            units = {"temp": row.temp_unit if row.temp_unit in ("C", "F") else "C",
                     "glucose": row.glucose_unit if row.glucose_unit in ("mg/dL", "mmol/L") else "mg/dL"}
    g.astro_units = units
    return units


def forget() -> None:
    """Drop the cached preference (after Settings changes it)."""
    if has_request_context() and hasattr(g, "astro_units"):
        del g.astro_units


def display(metric: str, value: float) -> tuple[float, int | None, str | None]:
    """(value, decimals, unit) in the viewer's units, or (value, None, None) when unchanged."""
    units = current_units()
    if metric == "temperature_c" and units["temp"] == "F":
        return value * 9 / 5 + 32, 1, "°F"
    if metric == "glucose" and units["glucose"] == "mmol/L":
        return value / GLUCOSE_FACTOR, 1, "mmol/L"
    return value, None, None


def to_stored(metric: str, value: float) -> float:
    """A value typed in the viewer's units, converted to the stored unit."""
    units = current_units()
    if metric == "temperature_c" and units["temp"] == "F":
        return (value - 32) * 5 / 9
    if metric == "glucose" and units["glucose"] == "mmol/L":
        return value * GLUCOSE_FACTOR
    return value
