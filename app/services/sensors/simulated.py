"""SimRecorder (Section 10A.9): keeps the generated attributes' charts filled without a scheduler.

``catch_up`` writes any missing 5-minute slots of generated blood pressure, glucose and
respiration for the last 24 h, idempotently, through ``measurements.record()``. It never
back-fills real-sensor metrics (heart rate, SpO₂, temperature): a missing wearable is a
visible gap, not invented data.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from config import Config

from ...extensions import db
from ...models import Astronaut, Measurement
from .. import measurements
from .physiology import PhysiologyModel, stable_seed

SOURCE = "simulated"
GENERATED = ("blood_pressure", "glucose", "respiration")
MIN_INTERVAL_S = 30
MAX_BACKFILL = timedelta(hours=24)
SCENARIO_SOURCE = "scenario"
SCENARIO_HOLD = timedelta(minutes=30)  # a Demo-panel reading is not overwritten for this long


class SimRecorder:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._locks: dict[int, threading.Lock] = {}
        self._last_run: dict[int, float] = {}
        self._guard = threading.Lock()

    def model(self, astronaut: Astronaut) -> PhysiologyModel:
        return PhysiologyModel(stable_seed(astronaut.astro_id, self.config.mission_name), self.config.meal_times)

    def _lock_for(self, astronaut_id: int) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(astronaut_id, threading.Lock())

    def slots(self, now: datetime, since: datetime) -> list[datetime]:
        step = timedelta(minutes=self.config.sim_record_interval_min)
        start = max(since, now - MAX_BACKFILL)
        midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
        offset = (start - midnight) // step + 1
        slot = midnight + offset * step
        out = []
        while slot <= now:
            out.append(slot)
            slot += step
        return out

    @staticmethod
    def _held_until(astronaut_id: int, now: datetime) -> dict[str, datetime]:
        """Per generated metric: the end of the hold after a recent Demo-panel reading.

        Slots up to that moment are skipped (left empty), so a forced or scenario reading
        stays the latest value instead of being replaced by the next generated slot.
        """
        rows = (db.session.query(Measurement.metric, db.func.max(Measurement.created_at))
                .filter(Measurement.astronaut_id == astronaut_id, Measurement.source == SCENARIO_SOURCE,
                        Measurement.metric.in_(GENERATED), Measurement.created_at >= now - SCENARIO_HOLD)
                .group_by(Measurement.metric).all())
        return {metric: at + SCENARIO_HOLD for metric, at in rows}

    def catch_up(self, astronaut: Astronaut, now: datetime, hr_live: float | None = None, *,
                 force: bool = False) -> int:
        """Write the missing slots. Returns how many slots were added (0 when rate-limited)."""
        lock = self._lock_for(astronaut.id)
        if not lock.acquire(blocking=False):
            return 0
        try:
            if not force and time.monotonic() - self._last_run.get(astronaut.id, -1e9) < MIN_INTERVAL_S:
                return 0
            self._last_run[astronaut.id] = time.monotonic()
            last = (db.session.query(db.func.max(Measurement.created_at))
                    .filter(Measurement.astronaut_id == astronaut.id, Measurement.metric.in_(GENERATED),
                            Measurement.source == SOURCE).scalar())
            slots = self.slots(now, last or now - MAX_BACKFILL)
            model = self.model(astronaut)
            held = self._held_until(astronaut.id, now)
            for slot in slots:
                sample = model.sample(slot, hr_live=hr_live if slot >= now - timedelta(minutes=1) else None)
                common = {"source": SOURCE, "created_at": slot, "live": False, "commit": False}
                if slot > held.get("blood_pressure", datetime.min):
                    measurements.record(astronaut.id, "blood_pressure", sample["systolic"],
                                        value2=sample["diastolic"], context="resting", **common)
                if slot > held.get("glucose", datetime.min):
                    measurements.record(astronaut.id, "glucose", sample["glucose"],
                                        context=sample["glucose_context"], **common)
                if slot > held.get("respiration", datetime.min):
                    measurements.record(astronaut.id, "respiration", sample["respiration"], context="resting",
                                        **common)
            if slots:
                from ..stream_hub import queue_event
                from ..summary import store_readiness

                store_readiness(astronaut.id, now.date(), as_of=now)
                queue_event(db.session, astronaut.id, "summary", {"metrics": list(GENERATED)})
            db.session.commit()
            return len(slots)
        finally:
            lock.release()

    def catch_up_all(self, now: datetime) -> int:
        total = 0
        for astronaut in Astronaut.query.filter_by(is_surgeon=False).all():
            total += self.catch_up(astronaut, now, force=True)
        return total
