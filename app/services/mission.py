"""The mission day as the crew sees it."""

from __future__ import annotations

from config import Config

from ..models import Mission


def mission_day(config: Config, mission: Mission | None) -> int:
    """The Demo panel's jump wins, then MISSION_DAY_OVERRIDE, then the calendar."""
    if mission is not None and mission.day_override is not None:
        return mission.day_override
    return config.mission_day
