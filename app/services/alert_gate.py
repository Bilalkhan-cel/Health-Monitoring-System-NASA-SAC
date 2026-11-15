"""AlertGate: decides whether a CRITICAL classification may become "Get help now".

Section 9.7. How many readings a CRITICAL needs depends on how the reading arrived:

    symptom          immediately (the astronaut reported it)
    manual, SpO2     never from one value: a second entry 60 s to 10 min later confirms it
    manual, other    immediately
    ble / other      the first CRITICAL reading
    wearable HR      only a sustained, good-quality run inside a rest-verified session
    session HR       the stored session average: CRITICAL only if such a run happened during it
    wearable SpO2    never (classify already caps it at CAUTION)
    wearable temp    two consecutive settled aggregates
    generated        two consecutive CRITICAL readings at least 5 s apart
    scenario / seed  written directly (Judge Mode and demo history)

The gate can only LOWER a status, never raise one. Pure Python, no I/O; every count
and window comes from the ``alert_confirm`` block of thresholds.yaml.

PROTOTYPE SAFETY LOGIC: these rules make the prototype cautious, not clinically
validated. An alert, or the absence of one, is never medical advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .thresholds import load_rules, rank

GENERATED_MIN_GAP_S = 5.0
DIRECT_ORIGINS = ("symptom", "ble", "scenario", "seed")


@dataclass(frozen=True)
class GateInput:
    """One classified reading on its way to being stored."""

    astronaut_id: int
    metric: str
    status: str | None
    origin: str  # manual | wearable | generated | ble | symptom | scenario | seed
    ts: float  # epoch seconds of the reading
    symptom: bool = False
    valid: bool = True
    quality: float | None = None
    in_resting_session: bool = False
    rest_verified: bool = False
    settled: bool = True
    device_key: str = ""
    run_passed: bool = False  # origin "wearable_session": a qualifying run happened during the session


@dataclass(frozen=True)
class GateResult:
    status: str | None
    confirmed: bool = True
    reason: str = ""
    needs_remeasure: bool = False


@dataclass
class _Run:
    count: int = 0
    first_ts: float = 0.0
    last_ts: float = 0.0


@dataclass
class AlertGate:
    """Holds the small amount of in-memory state the gates need."""

    rules: Mapping | None = None
    _pending_spo2: dict[int, float] = field(default_factory=dict)
    _runs: dict[tuple, _Run] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._confirm = (self.rules or load_rules())["alert_confirm"]

    @property
    def unmet_status(self) -> str:
        return self._confirm["unmet_status"]

    # ── public API ────────────────────────────────────────
    def evaluate(self, reading: GateInput) -> GateResult:
        """Return the effective status that is stored, shown and alerted on."""
        result = self._evaluate(reading)
        if rank(result.status) > rank(reading.status):  # safety net: a gate never raises
            return GateResult(reading.status, result.confirmed, result.reason, result.needs_remeasure)
        return result

    def reset_run(self, astronaut_id: int, device_key: str = "") -> None:
        """Forget a heart-rate run (finger off, new boot, stale gap, session end)."""
        self._runs.pop(("hr", astronaut_id, device_key), None)

    def spo2_pending(self, astronaut_id: int, now: float) -> bool:
        """True while a first low manual SpO2 entry is waiting for its confirmation."""
        first = self._pending_spo2.get(astronaut_id)
        if first is None:
            return False
        if now - first > self._confirm["spo2"]["manual"]["window_min"] * 60:
            del self._pending_spo2[astronaut_id]
            return False
        return True

    # ── rules ─────────────────────────────────────────────
    def _evaluate(self, r: GateInput) -> GateResult:
        if r.origin == "manual" and r.metric == "spo2":
            return self._manual_spo2(r)
        if r.origin == "wearable" and r.metric == "heart_rate":
            return self._wearable_heart_rate(r)
        if r.origin == "wearable_session":
            if r.status == "CRITICAL" and not r.run_passed:
                return GateResult(self.unmet_status, False, "no sustained run during the session")
            return GateResult(r.status)
        if r.status != "CRITICAL":
            self._runs.pop((r.origin, r.astronaut_id, r.metric, r.device_key), None)
            return GateResult(r.status)
        if r.symptom or r.origin in DIRECT_ORIGINS or r.origin == "manual":
            return GateResult("CRITICAL")
        if r.origin == "generated":
            return self._consecutive(r, self._confirm["generated_readings"], GENERATED_MIN_GAP_S)
        if r.origin == "wearable" and r.metric == "temperature_c":
            if not r.settled:
                return GateResult(self.unmet_status, False, "probe not settled")
            return self._consecutive(r, self._confirm["wearable_temperature_aggregates"], 0.0)
        if r.origin == "wearable":
            return GateResult(self.unmet_status, False, "wearable readings are capped")
        return GateResult("CRITICAL")

    def _manual_spo2(self, r: GateInput) -> GateResult:
        cfg = self._confirm["spo2"]["manual"]
        if r.status != "CRITICAL":
            self._pending_spo2.pop(r.astronaut_id, None)  # a normal second entry clears the prompt
            return GateResult(r.status)
        if r.symptom and cfg.get("symptom_override_confirms", True):
            self._pending_spo2.pop(r.astronaut_id, None)
            return GateResult("CRITICAL")
        first = self._pending_spo2.get(r.astronaut_id)
        if first is not None and r.ts - first > cfg["window_min"] * 60:
            first = None  # the first entry expired
        if first is None:
            self._pending_spo2[r.astronaut_id] = r.ts
            return GateResult(self.unmet_status, False, "first low entry", needs_remeasure=True)
        if r.ts - first < cfg["min_gap_s"]:
            return GateResult(self.unmet_status, False, "confirming entry came too soon", needs_remeasure=True)
        del self._pending_spo2[r.astronaut_id]
        return GateResult("CRITICAL")

    def _wearable_heart_rate(self, r: GateInput) -> GateResult:
        cfg = self._confirm["heart_rate"]["wearable"]
        key = ("hr", r.astronaut_id, r.device_key)
        good_quality = r.quality is not None and r.quality >= cfg["min_quality"]
        if not r.valid or r.status != "CRITICAL" or not good_quality:
            self._runs.pop(key, None)
            if r.status == "CRITICAL":
                return GateResult(self.unmet_status, False, "signal quality too low")
            return GateResult(r.status)
        run = self._runs.setdefault(key, _Run(first_ts=r.ts))
        run.count += 1
        run.last_ts = r.ts
        sustained = run.count >= cfg["consecutive_frames"] and (run.last_ts - run.first_ts) >= cfg["min_span_s"] - 1
        in_session = r.in_resting_session or not cfg["require_resting_session"]
        rested = r.rest_verified or not cfg["require_rest_verified"]
        if sustained and in_session and rested:
            return GateResult("CRITICAL")
        reason = "not sustained yet" if not sustained else "outside a rest-verified session"
        return GateResult(self.unmet_status, False, reason)

    def _consecutive(self, r: GateInput, needed: int, min_gap_s: float) -> GateResult:
        key = (r.origin, r.astronaut_id, r.metric, r.device_key)
        run = self._runs.get(key)
        if run is None:
            run = self._runs[key] = _Run(count=1, first_ts=r.ts, last_ts=r.ts)
        elif r.ts - run.last_ts >= min_gap_s:
            run.count += 1
            run.last_ts = r.ts
        if run.count >= needed:
            return GateResult("CRITICAL")
        return GateResult(self.unmet_status, False, f"{run.count} of {needed} readings")
