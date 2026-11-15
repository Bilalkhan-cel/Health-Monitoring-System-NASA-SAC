"""Heart check sessions (Section 10).

A session goes rest → measure → saved. During the 5-minute rest countdown and the 90 s
measurement, wearable frames arrive through the DeviceGateway's frame listener; Bluetooth
strap readings and manual entries arrive through ``/cardio/reading``; blood pressure,
glucose and respiration come from the PhysiologyModel. Everything is saved through
``measurements.record()`` with ``context = resting``.

Rules enforced here:
* rest_verified = countdown completed + ≥ 80 % valid heart-rate frames in its last 60 s +
  the six 10 s medians of that minute within 15 bpm (prototype check: no motion sensor);
* a wearable metric is saved only if ≥ 60 % of the session's seconds were valid for it;
* temperature only if the probe was settled for ≥ 30 s of the session;
* wearable heart rate becomes "Get help now" only through the AlertGate run (Section 9.7);
* any ticked symptom makes the whole check "Get help now".
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, median

from config import Config

from ..extensions import db
from ..models import Astronaut, CardioSession, Device, Measurement, Notification, utcnow
from ..services import gamification, measurements, thresholds
from ..services.alert_gate import GateInput
from ..services.live import LiveRuntime
from ..services.readiness import load_indicators
from ..services.sensors.physiology import PhysiologyModel, stable_seed
from ..services.sensors.quality import FrameResult
from ..services.summary import duration_text, load_environments, number_text, unit_text

REST_SECONDS = 300
MIN_COVERAGE = 0.6
MIN_TEMP_SETTLED_S = 30
MAX_PAUSE_S = 60
SYMPTOMS = {
    "chest_pain": "chest pain",
    "severe_headache": "a severe headache",
    "vision_changes": "vision changes",
    "short_of_breath": "severe shortness of breath",
    "fainting": "fainting",
}
GLUCOSE_CONTEXTS = ("fasting", "post_meal", "random")
MANUAL_METRICS = ("heart_rate", "blood_pressure", "glucose", "spo2", "temperature_c", "respiration")


@dataclass
class Second:
    ts: datetime
    finger: bool
    hr: float | None
    spo2: float | None
    q: float
    temp_state: str
    temp_c: float | None


@dataclass
class CardioRun:
    session_id: int
    astronaut_id: int
    phase: str  # rest | measure
    glucose_context: str
    symptoms: list[str]
    rest_started: datetime
    rest_skipped: bool = False
    measure_started: datetime | None = None
    duration_s: int = 90
    rest_verified: bool | None = None
    paused_s: float = 0.0
    paused_at: datetime | None = None
    rest_frames: list[Second] = field(default_factory=list)
    frames: list[Second] = field(default_factory=list)
    ble: list[tuple[datetime, float]] = field(default_factory=list)
    manual: dict[str, dict] = field(default_factory=dict)
    gate_critical: bool = False
    modes: dict[str, str] = field(default_factory=dict)


class CardioRuns:
    """Active sessions per astronaut, in memory (single process, like the stream hub)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.runs: dict[int, CardioRun] = {}

    def get(self, astronaut_id: int) -> CardioRun | None:
        with self._lock:
            return self.runs.get(astronaut_id)

    def put(self, run: CardioRun) -> None:
        with self._lock:
            self.runs[run.astronaut_id] = run

    def pop(self, astronaut_id: int) -> CardioRun | None:
        with self._lock:
            return self.runs.pop(astronaut_id, None)


def runs(runtime: LiveRuntime) -> CardioRuns:
    existing = getattr(runtime, "cardio_runs", None)
    if existing is None:
        existing = runtime.cardio_runs = CardioRuns()
        runtime.listeners.append(lambda astronaut_id, result, buffered:
                                 on_frame(runtime, astronaut_id, result, buffered))
    return existing


def on_frame(runtime: LiveRuntime, astronaut_id: int, result: FrameResult, buffered: bool) -> None:
    """Frame listener: collect wearable seconds for an active session and run the HR gate."""
    if buffered:
        return
    run = runs(runtime).get(astronaut_id)
    if run is None:
        return
    second = Second(result.ts, result.finger, result.hr if result.hr_valid else None,
                    result.spo2 if result.spo2_valid else None, result.q, result.temp_state, result.temp_c)
    if run.phase == "rest":
        run.rest_frames.append(second)
        return
    run.frames.append(second)
    if result.hr_valid and result.hr is not None:
        from ..services.measurements import get_gate

        status = thresholds.classify("heart_rate", result.hr, "resting")["status"]
        outcome = get_gate().evaluate(GateInput(
            astronaut_id=astronaut_id, metric="heart_rate", status=status, origin="wearable",
            ts=result.ts.timestamp(), quality=result.q, in_resting_session=True,
            rest_verified=bool(run.rest_verified), device_key="cardio"))
        if outcome.status == "CRITICAL":
            run.gate_critical = True
    elif not result.finger:
        from ..services.measurements import get_gate

        get_gate().reset_run(astronaut_id, "cardio")


def wearable_state(runtime: LiveRuntime, astronaut_id: int, now: datetime) -> dict:
    linked = Device.query.filter_by(astronaut_id=astronaut_id).first() is not None
    return runtime.live.snapshot(astronaut_id, now, linked=linked)


def verify_rest(run: CardioRun, rules: dict) -> bool:
    """The prototype rest check of Section 10 step 3. It cannot prove stillness."""
    checks = rules["alert_confirm"]["heart_rate"]["wearable"]["rest_verification"]
    if run.rest_skipped and checks.get("countdown_completed", True):
        return False
    end = run.rest_frames[-1].ts if run.rest_frames else run.rest_started
    last_minute = [s for s in run.rest_frames if (end - s.ts).total_seconds() < 60]
    valid = [s for s in last_minute if s.hr is not None]
    if len(valid) < checks["min_valid_coverage"] * 60:
        return False
    medians = []
    for block in range(6):
        values = [s.hr for s in valid if block * 10 <= 60 - (end - s.ts).total_seconds() - 1 < (block + 1) * 10]
        if values:
            medians.append(median(values))
    return len(medians) >= 5 and max(medians) - min(medians) <= checks["max_hr_range_bpm"]


def start(runtime: LiveRuntime, astronaut: Astronaut, *, glucose_context: str, symptoms: list[str],
          config: Config, now: datetime | None = None) -> CardioRun:
    now = now or utcnow()
    existing = runs(runtime).get(astronaut.id)
    if existing is not None:
        runs(runtime).pop(astronaut.id)
    session = CardioSession(astronaut_id=astronaut.id, started_at=now, glucose_context=glucose_context,
                            symptom_flags_json=json.dumps(symptoms))
    db.session.add(session)
    db.session.commit()
    run = CardioRun(session_id=session.id, astronaut_id=astronaut.id, phase="rest", glucose_context=glucose_context,
                    symptoms=symptoms, rest_started=now, duration_s=config.cardio_session_seconds)
    runs(runtime).put(run)
    return run


def begin_measuring(runtime: LiveRuntime, run: CardioRun, *, skipped: bool, now: datetime | None = None) -> CardioRun:
    now = now or utcnow()
    run.rest_skipped = skipped or (now - run.rest_started).total_seconds() < REST_SECONDS - 2
    run.rest_verified = verify_rest(run, thresholds.load_rules())
    run.phase = "measure"
    run.measure_started = now
    session = db.session.get(CardioSession, run.session_id)
    session.rest_verified = run.rest_verified
    db.session.commit()
    return run


def elapsed(run: CardioRun, now: datetime) -> float:
    if run.measure_started is None:
        return 0.0
    paused = run.paused_s + ((now - run.paused_at).total_seconds() if run.paused_at else 0.0)
    return max(0.0, (now - run.measure_started).total_seconds() - paused)


def model_for(astronaut: Astronaut, config: Config) -> PhysiologyModel:
    return PhysiologyModel(stable_seed(astronaut.astro_id, config.mission_name), config.meal_times)


def live_reading(runtime: LiveRuntime, run: CardioRun, astronaut: Astronaut, config: Config, now: datetime,
                 model: PhysiologyModel | None = None) -> dict:
    """One `reading` event: the latest valid value per metric, in the resting context."""
    model = model or model_for(astronaut, config)
    snap = runtime.live.snapshot(astronaut.id, now, linked=True)
    ble_hr = next((value for ts, value in reversed(run.ble) if (now - ts).total_seconds() <= 5), None)
    hr = ble_hr if run.modes.get("heart_rate") == "ble" and ble_hr else snap["hr"]
    if run.manual.get("heart_rate"):
        hr = run.manual["heart_rate"]["value"]
    sample = model.sample(now, hr_live=hr)
    readings: dict[str, dict] = {}

    def put(metric: str, value, value2=None, context=None, origin=None):
        if value is None:
            readings[metric] = {"value": None}
            return
        verdict = thresholds.classify_measurement(metric, value, value2, context or "resting",
                                                  "wearable" if origin == "wearable" else None)
        status = verdict["status"] if verdict else None
        if metric == "heart_rate" and origin == "wearable" and status == "CRITICAL" and not run.gate_critical:
            status = "CAUTION"  # a CRITICAL-range value shows Needs attention until the gate passes
        readings[metric] = {"value": number_text(metric, value, value2), "unit": unit_text(metric),
                            "status": None if status is None else thresholds.describe(status, verdict["direction"])}

    put("heart_rate", hr, origin="wearable" if hr == snap["hr"] and hr is not None else None)
    spo2 = run.manual.get("spo2", {}).get("value", snap["spo2"])
    put("spo2", spo2, origin="wearable" if "spo2" not in run.manual else None)
    temp = run.manual.get("temperature_c", {}).get("value", snap["temp"]["value_c"])
    put("temperature_c", temp, origin="wearable" if "temperature_c" not in run.manual else None)
    bp = run.manual.get("blood_pressure")
    put("blood_pressure", bp["value"] if bp else sample["systolic"], bp["value2"] if bp else sample["diastolic"])
    glucose = run.manual.get("glucose", {}).get("value", sample["glucose"])
    put("glucose", glucose, context=run.glucose_context)
    put("respiration", run.manual.get("respiration", {}).get("value", sample["respiration"]))

    remaining = max(0, run.duration_s - elapsed(run, now)) if run.phase == "measure" else None
    waiting_for_finger = run.phase == "measure" and run.modes.get("heart_rate", "wearable") == "wearable" \
        and snap["state"] == "no_finger"
    return {"phase": run.phase, "remaining_s": None if remaining is None else round(remaining),
            "paused": run.paused_at is not None, "finger": snap["finger"], "wearable_state": snap["state"],
            "bpm": hr, "ppg": None, "readings": readings, "waiting_for_finger": waiting_for_finger,
            "temp_state": snap["temp"]["state"]}


def add_reading(runtime: LiveRuntime, run: CardioRun, astronaut: Astronaut, data: dict, now: datetime) -> dict:
    """A Bluetooth strap value or a hand-entered value during the session."""
    via = data.get("via")  # "strap" (Bluetooth) or "hand" (typed in)
    metric = data.get("metric")
    if via == "strap":
        if metric != "heart_rate":
            raise ValueError("only heart rate is read from a Bluetooth strap")
        value = float(data.get("value"))
        measurements.validate("heart_rate", value)
        run.ble.append((now, value))
        run.modes["heart_rate"] = "ble"
        return {"ok": True}
    if via != "hand" or metric not in MANUAL_METRICS:
        raise ValueError("unknown reading")
    value = float(data.get("value"))
    value2 = float(data["value2"]) if data.get("value2") not in (None, "") else None
    context = run.glucose_context if metric == "glucose" else ("resting" if thresholds.requires_rest(metric) else None)
    symptom = bool(run.symptoms) and bool(data.get("symptom"))
    result = measurements.record(astronaut.id, metric, value, value2=value2, source="manual", context=context,
                                 origin="manual", created_at=now, session_type="cardio", session_id=run.session_id,
                                 symptom=symptom)
    run.manual[metric] = {"value": value, "value2": value2, "status": result.status}
    run.modes[metric] = "manual"
    reply = {"ok": True, "status": result.status, "confirmed": result.confirmed,
             "needs_remeasure": result.needs_remeasure}
    if result.needs_remeasure:
        reply["message"] = ("This reading is very low. Please re-measure to confirm. If you feel short of breath, "
                            "tick a symptom below or tell your crew medical officer.")
        reply["min_gap_s"] = thresholds.load_rules()["alert_confirm"]["spo2"]["manual"]["min_gap_s"]
    return reply


def _coverage(values: list, seconds: int) -> float:
    return len(values) / max(1, seconds)


def finish(runtime: LiveRuntime, run: CardioRun, astronaut: Astronaut, config: Config,
           now: datetime | None = None) -> dict:
    """Save the session and return the results payload."""
    now = now or utcnow()
    runs(runtime).pop(astronaut.id)
    session = db.session.get(CardioSession, run.session_id)
    seconds = max(1, int(round(elapsed(run, now))) or len(run.frames))
    model = model_for(astronaut, config)
    saved: dict[str, Measurement] = {}
    messages: list[str] = []
    valid_pct: dict[str, int] = {}

    def save(metric, value, value2=None, *, source, context=None, origin=None, gate=None):
        result = measurements.record(astronaut.id, metric, value, value2=value2, source=source, context=context,
                                     origin=origin, created_at=now, session_type="cardio",
                                     session_id=run.session_id, gate_context=gate, commit=False)
        saved[metric] = result.measurement
        return result

    hr_values = [s.hr for s in run.frames if s.hr is not None]
    if "heart_rate" not in run.manual:
        if run.modes.get("heart_rate") == "ble" and run.ble:
            ble = [value for ts, value in run.ble if ts >= (run.measure_started or now)]
            valid_pct["heart_rate"] = round(100 * min(1.0, _coverage(ble, seconds)))
            if _coverage(ble, seconds) >= MIN_COVERAGE:
                save("heart_rate", round(mean(ble), 1), source="sensor", context="resting", origin="ble")
            else:
                messages.append("Not enough clean readings for heart rate. Try again with the strap snug.")
        elif run.frames or hr_values:
            valid_pct["heart_rate"] = round(100 * min(1.0, _coverage(hr_values, seconds)))
            if _coverage(hr_values, seconds) >= MIN_COVERAGE:
                save("heart_rate", round(mean(hr_values), 1), source="sensor", context="resting",
                     origin="wearable_session", gate={"run_passed": run.gate_critical})
            else:
                messages.append("Not enough clean readings for heart rate. Try again with your hand still.")
    spo2_values = [s.spo2 for s in run.frames if s.spo2 is not None]
    if "spo2" not in run.manual and run.frames:
        valid_pct["spo2"] = round(100 * min(1.0, _coverage(spo2_values, seconds)))
        if _coverage(spo2_values, seconds) >= MIN_COVERAGE:
            save("spo2", round(mean(spo2_values), 1), source="sensor", origin="wearable")
        else:
            messages.append("Not enough clean readings for oxygen. Keep your finger still next time.")
    settled = [s.temp_c for s in run.frames if s.temp_state == "settled" and s.temp_c is not None]
    if "temperature_c" not in run.manual and run.frames:
        if len(settled) >= MIN_TEMP_SETTLED_S:
            save("temperature_c", round(median(settled), 2), source="derived", origin="wearable",
                 gate={"settled": True})
        else:
            messages.append("Temperature was not steady long enough. Keep the probe under your arm for 10 minutes.")

    sample = model.sample(now, hr_live=mean(hr_values) if hr_values else None)
    if "blood_pressure" not in run.manual:
        save("blood_pressure", sample["systolic"], sample["diastolic"], source="simulated", context="resting",
             origin="generated")
    if "glucose" not in run.manual:
        save("glucose", sample["glucose"], source="simulated", context=run.glucose_context, origin="generated")
    if "respiration" not in run.manual:
        save("respiration", sample["respiration"], source="simulated", context="resting", origin="generated")
    db.session.flush()

    rows = Measurement.query.filter_by(session_type="cardio", session_id=run.session_id).all()
    statuses = [row.status for row in rows]
    overall = thresholds.worst(statuses) or "STABLE"
    symptom_text = ""
    if run.symptoms:
        overall = "CRITICAL"
        names = [SYMPTOMS[s] for s in run.symptoms if s in SYMPTOMS]
        symptom_text = "You reported " + " and ".join(names) + "."
        db.session.add(Notification(
            astronaut_id=astronaut.id, type="critical", severity="alert", title="Get help now: symptoms reported",
            message=f"{symptom_text} Tell your crew medical officer now and follow the onboard protocol.",
            action_url="/cardio", dedupe_key=f"symptoms:{run.session_id}", created_at=now))

    by_metric = {row.metric: row for row in rows}
    session.ended_at = now
    session.avg_hr = by_metric["heart_rate"].value if "heart_rate" in by_metric else None
    if "blood_pressure" in by_metric:
        session.avg_sys, session.avg_dia = by_metric["blood_pressure"].value, by_metric["blood_pressure"].value2
    session.avg_spo2 = by_metric["spo2"].value if "spo2" in by_metric else None
    session.avg_temp = by_metric["temperature_c"].value if "temperature_c" in by_metric else None
    session.avg_glucose = by_metric["glucose"].value if "glucose" in by_metric else None
    session.avg_resp = by_metric["respiration"].value if "respiration" in by_metric else None
    session.input_modes_json = json.dumps(run.modes)
    session.valid_pct_json = json.dumps(valid_pct)
    session.overall_status = overall
    session.summary = explain(overall, by_metric)
    outcome = gamification.complete_task(astronaut, "cardio", now)
    from ..services.summary import store_readiness

    store_readiness(astronaut.id, now.date(), as_of=now)
    db.session.commit()
    return results_payload(astronaut, session, by_metric, messages, symptom_text, outcome.xp_gained, config)


def explain(overall: str, by_metric: dict[str, Measurement]) -> str:
    indicators = load_indicators()["metrics"]
    flagged = [m for m in by_metric.values() if m.status in ("CAUTION", "CRITICAL")]
    if overall == "CRITICAL":
        return "Something needs help now. Tell your crew medical officer and follow the onboard protocol."
    if not flagged:
        return "Your heart numbers look steady. Keep drinking water and check again tomorrow."
    names = [indicators[m.metric]["short"].lower() for m in flagged]
    return f"Your {' and '.join(names)} need{'s' if len(names) == 1 else ''} attention today."


ACTIONS = {
    "heart_rate": "Drink a glass of water now and sit quietly for five minutes.",
    "blood_pressure": "Cut back on salty food today and avoid caffeine before your next check.",
    "spo2": "Warm your hands and re-measure while keeping your finger still.",
    "temperature_c": "Rest, drink water and measure again in an hour.",
    "glucose": "Eat at your usual meal times and re-check before your next meal.",
    "respiration": "Breathe in for four counts and out for six, for two minutes.",
}


def results_payload(astronaut: Astronaut, session: CardioSession, by_metric: dict[str, Measurement],
                    messages: list[str], symptom_text: str, xp: int, config: Config) -> dict:
    indicators = load_indicators()["metrics"]
    rows = []
    for metric in ("heart_rate", "blood_pressure", "spo2", "glucose", "respiration", "temperature_c"):
        row = by_metric.get(metric)
        if row is None:
            continue
        verdict = thresholds.classify_measurement(metric, row.value, row.value2, row.context)
        rows.append({"metric": metric, "label": indicators[metric]["short"],
                     "value": number_text(metric, row.value, row.value2), "unit": unit_text(metric),
                     "status": thresholds.describe(row.status, verdict["direction"] if verdict else None)
                     if row.status else None})
    flagged = [m for m in by_metric.values() if m.status in ("CAUTION", "CRITICAL")]
    actions = [ACTIONS[m.metric] for m in flagged if m.metric in ACTIONS][:3]
    defaults = ["Keep drinking water through your shift.", "Do your exercise session as planned.",
                "Check your heart again tomorrow morning."]
    actions += [step for step in defaults if step not in actions][: 3 - len(actions)]
    environment = astronaut.mission.environment
    delay = astronaut.mission.comms_delay_s
    if delay is None:
        delay = load_environments().get(environment, {}).get("comms_delay_one_way_s", 0)
    if session.overall_status == "CRITICAL":
        actions = ["Tell your crew medical officer now.", "Follow the onboard medical protocol and stay seated.",
                   f"Contact the ground flight surgeon. Messages to Earth take {duration_text(delay)}."]
    previous = (CardioSession.query.filter(CardioSession.astronaut_id == astronaut.id,
                                           CardioSession.ended_at.isnot(None), CardioSession.id != session.id)
                .order_by(CardioSession.ended_at.desc()).limit(7).all())
    history = [{"t": s.ended_at.isoformat(timespec="minutes") + "Z", "hr": s.avg_hr, "sys": s.avg_sys,
                "dia": s.avg_dia} for s in reversed(previous)]
    history.append({"t": session.ended_at.isoformat(timespec="minutes") + "Z", "hr": session.avg_hr,
                    "sys": session.avg_sys, "dia": session.avg_dia, "current": True})
    remeasure = {"CRITICAL": "Re-measure in 5 minutes if you are able to.",
                 "CAUTION": "Check your heart again in 2 hours.",
                 "STABLE": "Check again tomorrow morning.", "NOMINAL": "Check again tomorrow morning."}
    return {
        "session_id": session.id, "overall": thresholds.describe(session.overall_status),
        "explanation": session.summary, "symptoms": symptom_text, "rows": rows, "messages": messages,
        "actions": actions, "remeasure": remeasure[session.overall_status], "history": history, "xp": xp,
        "rest_note": None if session.rest_verified else
        "The rest countdown was skipped or your heart rate was not steady, so readings may be higher than at rest.",
    }


def recent_symptom_alerts(astronaut_id: int, now: datetime) -> list[CardioSession]:
    since = now - timedelta(hours=6)
    return [s for s in CardioSession.query.filter(CardioSession.astronaut_id == astronaut_id,
                                                  CardioSession.ended_at >= since).all()
            if json.loads(s.symptom_flags_json or "[]")]
