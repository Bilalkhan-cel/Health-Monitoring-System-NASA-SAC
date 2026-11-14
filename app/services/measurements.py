"""``record()``: the ONE way a Measurement is saved.

classify -> AlertGate -> save -> notifications -> readiness (and an SSE ``summary`` event once the
live hub exists). Daily tasks are ticked by the module that finishes the task.
Manual entry, the cardio session, the wearable aggregator, the generator and the
seed script all call it, so there is a single code path for every reading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from flask import current_app

from ..extensions import db
from ..models import Measurement, Notification, utcnow
from . import readiness as readiness_service
from . import thresholds
from .alert_gate import AlertGate, GateInput

log = logging.getLogger(__name__)

UNITS = {
    "heart_rate": "bpm", "blood_pressure": "mmHg", "glucose": "mg/dL", "temperature_c": "°C", "spo2": "%",
    "respiration": "br/min", "sleep_hours": "h", "wellbeing": "score", "loading_index": "score",
    "hydration_ml": "mL",
}
# Plausibility limits for anything typed in or received (not clinical ranges).
LIMITS = {
    "heart_rate": (20, 250), "blood_pressure": (40, 300), "glucose": (20, 600), "temperature_c": (30, 45),
    "spo2": (50, 100), "respiration": (2, 60), "sleep_hours": (0, 24), "wellbeing": (0, 100),
    "loading_index": (0, 100), "hydration_ml": (0, 10000),
}
ORIGIN_BY_SOURCE = {"manual": "manual", "simulated": "generated"}


class InvalidReading(ValueError):
    """Raised when a value is not a plausible reading for its metric."""


@dataclass(frozen=True)
class RecordResult:
    measurement: Measurement
    status: str | None
    confirmed: bool
    needs_remeasure: bool


def get_gate() -> AlertGate:
    """The app-wide AlertGate (it keeps small in-memory counters)."""
    gate = current_app.extensions.get("alert_gate")
    if gate is None:
        gate = current_app.extensions["alert_gate"] = AlertGate()
    return gate


def validate(metric: str, value: float, value2: float | None = None) -> None:
    if metric not in UNITS:
        raise InvalidReading(f"unknown metric '{metric}'")
    lo, hi = LIMITS[metric]
    for number in (value, value2) if metric == "blood_pressure" else (value,):
        if number is None or number != number or not lo <= number <= hi:
            raise InvalidReading(f"{metric} must be between {lo} and {hi}")
    if metric == "blood_pressure" and value2 >= value:
        raise InvalidReading("the first blood pressure number must be the larger one")


def _notify(astronaut_id: int, measurement: Measurement, needs_remeasure: bool) -> None:
    """Add one notification per metric, status and day (deduplicated)."""
    status = measurement.status
    if status not in ("CAUTION", "CRITICAL"):
        return
    indicators = readiness_service.load_indicators()["metrics"]
    label = indicators[measurement.metric]["short"].lower()
    shown = display_value(measurement)
    day = measurement.created_at.date().isoformat()
    key = f"{measurement.metric}:{status}:{day}"
    if db.session.query(Notification.id).filter_by(astronaut_id=astronaut_id, dedupe_key=key).first():
        return
    if status == "CRITICAL":
        title = f"Get help now: {label}"
        message = f"Your {label} reads {shown}. Tell your crew medical officer now and follow the onboard protocol."
        kind = "critical"
    elif needs_remeasure:
        title = f"Re-measure your {label}"
        message = (f"Your {label} reads {shown}, which is very low. Please re-measure to confirm. If you feel "
                   "short of breath, tell your crew medical officer.")
        kind = "attention"
    else:
        title = f"Needs attention: {label}"
        message = f"Your {label} reads {shown}. Open Today to see what to do."
        kind = "attention"
    db.session.add(Notification(astronaut_id=astronaut_id, type=kind,
                                severity=thresholds.STATUS_META[status]["key"], title=title, message=message,
                                action_url="/dashboard", dedupe_key=key, created_at=measurement.created_at))


def display_value(measurement: Measurement) -> str:
    """A reading as plain text, for example '121/78 mmHg'."""
    if measurement.metric == "blood_pressure":
        return f"{measurement.value:.0f}/{measurement.value2:.0f} mmHg"
    decimals = readiness_service.load_indicators()["metrics"][measurement.metric]["decimals"]
    unit = measurement.unit if measurement.unit != "score" else ""
    return f"{measurement.value:.{decimals}f} {unit}".strip()


def record(
    astronaut_id: int,
    metric: str,
    value: float,
    *,
    source: str,
    value2: float | None = None,
    context: str | None = None,
    origin: str | None = None,
    created_at: datetime | None = None,
    symptom: bool = False,
    session_type: str | None = None,
    session_id: int | None = None,
    device_pk: int | None = None,
    quality: float | None = None,
    n_samples: int | None = None,
    window_s: int | None = None,
    raw_value: float | None = None,
    gate_context: dict | None = None,
    live: bool = True,
    commit: bool = True,
) -> RecordResult:
    """Classify, gate and store one reading.

    ``live=False`` is for demo history and back-filled data: it skips the gate,
    notifications and the readiness refresh (the caller handles those in bulk).
    ``origin`` says how the reading arrived (manual | wearable | generated | ble |
    scenario | seed) and is derived from ``source`` when omitted.
    """
    validate(metric, value, value2)
    when = created_at or utcnow()
    origin = origin or ("wearable" if device_pk else ORIGIN_BY_SOURCE.get(source, "ble"))
    if not live:
        origin = "seed"

    verdict = thresholds.classify_measurement(metric, value, value2, context,
                                              "wearable" if origin == "wearable" else None)
    status = verdict["status"] if verdict else None
    if symptom:
        status = "CRITICAL"  # the astronaut reported a symptom: escalate regardless of the number

    confirmed, needs_remeasure = True, False
    if live and status is not None:
        outcome = get_gate().evaluate(GateInput(
            astronaut_id=astronaut_id, metric=metric, status=status, origin="symptom" if symptom else origin,
            ts=when.timestamp(), symptom=symptom, quality=quality, **(gate_context or {}),
        ))
        status, confirmed, needs_remeasure = outcome.status, outcome.confirmed, outcome.needs_remeasure

    measurement = Measurement(
        astronaut_id=astronaut_id, metric=metric, value=float(value),
        value2=float(value2) if value2 is not None else None, unit=UNITS[metric], status=status,
        threshold_version=thresholds.load_rules()["version"] if status else None, source=source, context=context,
        confirmed=confirmed, session_type=session_type, session_id=session_id, device_pk=device_pk,
        quality=quality, n_samples=n_samples, window_s=window_s, raw_value=raw_value, created_at=when,
    )
    db.session.add(measurement)

    if live:
        _notify(astronaut_id, measurement, needs_remeasure)
        if status is not None:
            from .stream_hub import queue_event

            queue_event(db.session, astronaut_id, "summary", {"metrics": [metric]})
        db.session.flush()
        from .summary import store_readiness  # local import: summary reads measurements

        store_readiness(astronaut_id, when.date(), as_of=when)
    if commit:
        db.session.commit()
    return RecordResult(measurement, status, confirmed, needs_remeasure)
