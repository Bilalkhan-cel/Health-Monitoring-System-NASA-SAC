"""Settings → Demo panel (Section 16): forced statuses, mission-day jump and Judge Mode scenarios.

Everything here is available only with DEMO_MODE=true, always triggered by a person and
always written to the audit log. Scenario readings go through ``measurements.record()`` with
``origin="scenario"`` so they are classified, alerted and scored exactly like any other
reading. Real wearable metrics can be forced only after Wearable mode is switched to Demo
data (Section 10A.11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..extensions import db
from ..models import Astronaut, AuditLog, SleepLog
from . import measurements
from .stream_hub import queue_event
from .summary import store_readiness

GENERATED = ("blood_pressure", "glucose", "respiration")
WEARABLE = ("heart_rate", "spo2", "temperature_c")
STATUS_KEYS = ("good", "okay", "watch", "alert")
# One representative reading per status. Blood pressure is (systolic, diastolic).
FORCE_VALUES = {
    "blood_pressure": {"good": (114, 74), "okay": (125, 78), "watch": (146, 92), "alert": (186, 118)},
    "glucose": {"good": 88, "okay": 105, "watch": 168, "alert": 290},
    "respiration": {"good": 15, "okay": 20, "watch": 23, "alert": 28},
    "heart_rate": {"good": 72, "okay": 95, "watch": 112, "alert": 138},
    "spo2": {"good": 98, "okay": 95, "watch": 92, "alert": 88},
    "temperature_c": {"good": 36.8, "okay": 37.4, "watch": 38.2, "alert": 39.4},
}
CONTEXT = {"blood_pressure": "resting", "glucose": "fasting", "respiration": "resting", "heart_rate": "resting"}
SOURCE = "scenario"  # internal only; SimRecorder holds its own writes for a while after one


@dataclass(frozen=True)
class Scenario:
    code: str
    title: str
    story: str
    environment: str | None = None
    comms_delay_s: float | None = None
    day: int | None = None
    readings: tuple[tuple[str, float, float | None, str | None], ...] = ()
    sleep_nights: tuple[float, ...] = field(default=())


SCENARIOS = {
    "mars_transit": Scenario(
        "mars_transit", "Day 142, Mars transit",
        "Three short nights push the heart rate up and the mood down.",
        environment="Spacecraft", comms_delay_s=600, day=142,
        readings=(("heart_rate", 104, None, "resting"), ("wellbeing", 50, None, None)),
        sleep_nights=(5.2, 5.5, 4.9)),
    "lunar_base": Scenario(
        "lunar_base", "Lunar base",
        "No exercise for four days, so the exercise load needs attention.",
        environment="Lunar Base", readings=(("loading_index", 46, None, None),)),
    "critical_bp": Scenario(
        "critical_bp", "Critical BP event, 14-min comms delay",
        "Blood pressure 186/118 with a 14-minute delay to Earth.",
        comms_delay_s=840, readings=(("blood_pressure", 186, 118, "resting"),
                                     ("blood_pressure", 187, 119, "resting"))),
}


class DemoError(ValueError):
    """A request the Demo panel refuses, with a message for the astronaut."""


def _audit(astronaut: Astronaut, action: str, meta: dict) -> None:
    db.session.add(AuditLog(actor=astronaut.astro_id, action=action, target_astronaut_id=astronaut.id,
                            meta_json=json.dumps(meta)))


def _finish(astronaut: Astronaut, now: datetime, metrics: list[str]) -> None:
    store_readiness(astronaut.id, now.date(), as_of=now)
    queue_event(db.session, astronaut.id, "summary", {"metrics": metrics})
    db.session.commit()


def force_status(astronaut: Astronaut, metric: str, status: str, now: datetime) -> str:
    """Write one reading that lands in the chosen status. Returns the stored status."""
    if metric not in FORCE_VALUES or status not in STATUS_KEYS:
        raise DemoError("Pick a metric and a status from the list.")
    if metric in WEARABLE and astronaut.mission.sensor_mode != "demo":
        raise DemoError("Switch Wearable mode to Demo data before forcing a wearable reading.")
    value = FORCE_VALUES[metric][status]
    first, second = value if isinstance(value, tuple) else (value, None)
    # Scenario readings are direct (Section 9.7), so one forced reading is enough.
    result = measurements.record(astronaut.id, metric, first, value2=second, context=CONTEXT.get(metric),
                                 source=SOURCE, origin="scenario", created_at=now, commit=False)
    stored = result.status
    _audit(astronaut, "demo_force_status", {"metric": metric, "status": status})
    _finish(astronaut, now, [metric])
    return stored


def jump_day(astronaut: Astronaut, day: int | None) -> int | None:
    """Show a different mission day (``None`` returns to the calendar day)."""
    if day is not None and not 1 <= day <= 2000:
        raise DemoError("The mission day must be between 1 and 2000.")
    mission = astronaut.mission
    previous = mission.day_override
    mission.day_override = day
    _audit(astronaut, "demo_jump_day", {"from": previous, "to": day})
    db.session.commit()
    return day


def run_scenario(astronaut: Astronaut, code: str, now: datetime) -> Scenario:
    """Apply a Judge Mode preset: environment, comms delay, mission day and readings."""
    scenario = SCENARIOS.get(code)
    if scenario is None:
        raise DemoError("Unknown scenario.")
    mission = astronaut.mission
    if scenario.environment:
        mission.environment = scenario.environment
        mission.comms_delay_s = None
    if scenario.comms_delay_s is not None:
        mission.comms_delay_s = scenario.comms_delay_s
    if scenario.day is not None:
        mission.day_override = scenario.day
    metrics = []
    for offset, hours in enumerate(reversed(scenario.sleep_nights)):
        day = now.date() - timedelta(days=offset)
        log = SleepLog.query.filter_by(astronaut_id=astronaut.id, date=day).first()
        if log is None:
            log = SleepLog(astronaut_id=astronaut.id, date=day, hours=hours)
            db.session.add(log)
        log.hours, log.source = hours, SOURCE
        at = min(now, datetime.combine(day, datetime.min.time()) + timedelta(hours=7))
        measurements.record(astronaut.id, "sleep_hours", hours, source=SOURCE, origin="scenario", created_at=at,
                            commit=False, notify=offset == 0)
        metrics.append("sleep_hours")
    count = len(scenario.readings)
    for index, (metric, value, value2, context) in enumerate(scenario.readings):
        # Spaced 6 s apart and ending now, so the last one is the latest reading.
        measurements.record(astronaut.id, metric, value, value2=value2, context=context, source=SOURCE,
                            origin="scenario", created_at=now - timedelta(seconds=6 * (count - 1 - index)),
                            commit=False)
        metrics.append(metric)
    _audit(astronaut, "demo_scenario", {"scenario": code})
    _finish(astronaut, now, sorted(set(metrics)))
    return scenario
