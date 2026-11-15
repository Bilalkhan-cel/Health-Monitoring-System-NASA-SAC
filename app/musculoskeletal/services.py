"""Exercise sessions: sets from camera keypoints or the device log, then the loading index."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from ..extensions import db
from ..models import Astronaut, ExerciseSession, ExerciseSet, utcnow
from ..services import gamification, measurements, pose_service, thresholds
from ..services.loading_index import SetSummary, compute, trailing_sets
from ..services.summary import load_environments, store_readiness

PLANS = {
    "zero_g": [{"exercise": "run", "label": "Harnessed treadmill", "target": "20 min"},
               {"exercise": "device_log", "label": "ARED or cycle (log it)", "target": "30 min"}],
    "surface": [{"exercise": "run", "label": "Running in place", "target": "6 min"},
                {"exercise": "pushup", "label": "Push-ups", "target": "3 × 15"},
                {"exercise": "pullup", "label": "Pull-ups", "target": "3 × 6"},
                {"exercise": "squat", "label": "Squats", "target": "3 × 15"}],
}
NAMES = {"run": "Running", "pushup": "Push-ups", "pullup": "Pull-ups", "squat": "Squats",
         "device_log": "Device session", "treadmill_harness": "Harnessed treadmill"}
DEVICES = ("ARED", "Cycle ergometer", "Treadmill")
MAX_FRAMES_PER_POST = 30


def allowed_exercises(environment: str) -> list[str]:
    options = load_environments().get(environment, {}).get("exercise", ["device_log"])
    allowed = []
    for option in options:
        mapped = "run" if option == "treadmill_harness" else option
        if mapped not in allowed:
            allowed.append(mapped)
    return allowed


def plan_for(environment: str) -> list[dict]:
    gravity = load_environments().get(environment, {}).get("gravity_g", 0)
    allowed = allowed_exercises(environment)
    plan = PLANS["zero_g" if not gravity else "surface"]
    return [item for item in plan if item["exercise"] in allowed]


@dataclass
class CurrentSet:
    exercise: str
    started_t: float | None = None
    last_t: float | None = None
    counter: object = None
    cue: str | None = None


@dataclass
class ExerciseRun:
    session_id: int
    astronaut_id: int
    environment: str
    current: CurrentSet | None = None
    finished_sets: list[dict] = field(default_factory=list)
    before: int | None = None


class ExerciseRuns:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.runs: dict[int, ExerciseRun] = {}

    def get(self, astronaut_id: int) -> ExerciseRun | None:
        with self._lock:
            return self.runs.get(astronaut_id)

    def put(self, run: ExerciseRun) -> None:
        with self._lock:
            self.runs[run.astronaut_id] = run

    def pop(self, astronaut_id: int) -> ExerciseRun | None:
        with self._lock:
            return self.runs.pop(astronaut_id, None)


def runs(runtime) -> ExerciseRuns:
    existing = getattr(runtime, "exercise_runs", None)
    if existing is None:
        existing = runtime.exercise_runs = ExerciseRuns()
    return existing


def latest_loading(astronaut_id: int) -> int | None:
    from ..models import Measurement

    row = (Measurement.query.filter_by(astronaut_id=astronaut_id, metric="loading_index")
           .order_by(Measurement.created_at.desc()).first())
    return round(row.value) if row else None


def start(runtime, astronaut: Astronaut, now: datetime | None = None) -> ExerciseRun:
    now = now or utcnow()
    existing = runs(runtime).get(astronaut.id)
    if existing is not None:
        return existing
    environment = astronaut.mission.environment
    session = ExerciseSession(astronaut_id=astronaut.id, started_at=now, environment=environment)
    db.session.add(session)
    db.session.commit()
    run = ExerciseRun(session.id, astronaut.id, environment, before=latest_loading(astronaut.id))
    runs(runtime).put(run)
    return run


def begin_set(run: ExerciseRun, exercise: str) -> CurrentSet:
    if exercise not in allowed_exercises(run.environment) or exercise == "device_log":
        raise ValueError("That exercise is not available here.")
    if run.current is not None:
        close_set(run)
    run.current = CurrentSet(exercise, counter=pose_service.make_counter(exercise))
    return run.current


def feed(run: ExerciseRun, frames: list[dict]) -> dict:
    """Process a batch of keypoint frames for the current set."""
    current = run.current
    if current is None:
        raise ValueError("Start a set first.")
    rep_done, update = False, None
    for raw in frames[:MAX_FRAMES_PER_POST]:
        t = raw.get("t")
        keypoints = pose_service.parse_keypoints(raw.get("kp"))
        if not isinstance(t, (int, float)) or keypoints is None:
            continue
        if current.started_t is None:
            current.started_t = float(t)
        current.last_t = float(t)
        update = current.counter.update(float(t), keypoints)
        rep_done = rep_done or update.rep_done
        if update.cue:
            current.cue = update.cue
    counter = current.counter
    return {
        "exercise": current.exercise, "reps": counter.reps, "rep_done": rep_done,
        "cue": update.cue if update else None, "form": counter.form,
        "cadence": update.cadence if update else None, "steps": getattr(counter, "steps", None),
        "duration_s": round((current.last_t or 0) - (current.started_t or 0), 1),
        "state": update.state if update else None,
    }


def close_set(run: ExerciseRun) -> dict | None:
    current = run.current
    run.current = None
    if current is None or current.started_t is None:
        return None
    counter = current.counter
    duration = max(0.0, (current.last_t or 0) - current.started_t)
    item = {"exercise_type": current.exercise, "reps": None if current.exercise == "run" else counter.reps,
            "duration_s": round(duration, 1), "form_score": counter.form,
            "cadence_spm": counter.cadence(current.last_t) if current.exercise == "run" else None}
    if current.exercise == "run":
        item["steps"] = counter.steps
    if (item["reps"] or 0) == 0 and current.exercise != "run":
        return None
    if current.exercise == "run" and duration < 10:
        return None
    run.finished_sets.append(item)
    return item


def log_device(run: ExerciseRun, device: str, minutes: float, effort: int) -> dict:
    if device not in DEVICES:
        raise ValueError("Choose ARED, cycle ergometer or treadmill.")
    if not 1 <= minutes <= 240 or not 1 <= effort <= 10:
        raise ValueError("Minutes must be 1 to 240 and effort 1 to 10.")
    item = {"exercise_type": "device_log", "reps": None, "duration_s": minutes * 60, "form_score": None,
            "cadence_spm": None, "effort_1_10": effort, "device": device}
    run.finished_sets.append(item)
    return item


def finish(runtime, astronaut: Astronaut, now: datetime | None = None) -> dict:
    now = now or utcnow()
    run = runs(runtime).get(astronaut.id)
    if run is None:
        raise LookupError("No exercise session is running.")
    close_set(run)
    runs(runtime).pop(astronaut.id)
    session = db.session.get(ExerciseSession, run.session_id)
    session.ended_at = now
    for item in run.finished_sets:
        db.session.add(ExerciseSet(session_id=session.id, exercise_type=item["exercise_type"], reps=item["reps"],
                                   duration_s=item["duration_s"], cadence_spm=item["cadence_spm"],
                                   form_score=item["form_score"], effort_1_10=item.get("effort_1_10")))
    db.session.flush()
    if not run.finished_sets:
        db.session.delete(session)
        db.session.commit()
        return {"saved": False, "message": "No exercise was recorded, so nothing was saved."}
    result = compute(trailing_sets(astronaut.id, now), run.environment)
    session.loading_index = result["score"]
    camera = any(item["exercise_type"] != "device_log" for item in run.finished_sets)
    record = measurements.record(astronaut.id, "loading_index", result["score"], source="cv" if camera else "manual",
                                 created_at=now, session_type="exercise", session_id=session.id, commit=False)
    session.overall_status = record.status
    names = ", ".join(sorted({NAMES[item["exercise_type"]] for item in run.finished_sets}))
    session.summary = f"{names}: {len(run.finished_sets)} set(s), {result['minutes']} active minutes this week"
    outcome = gamification.complete_task(astronaut, "exercise", now)
    store_readiness(astronaut.id, now.date(), as_of=now)
    db.session.commit()
    previous = (ExerciseSession.query.filter(ExerciseSession.astronaut_id == astronaut.id,
                                             ExerciseSession.id != session.id,
                                             ExerciseSession.ended_at.isnot(None))
                .order_by(ExerciseSession.started_at.desc()).first())
    status = thresholds.describe(record.status) if record.status else None
    tips = []
    if result["frequency"] < 1:
        tips.append(f"Exercise on {result['target_days']} days a week: you are at {result['days']}.")
    if result["volume"] < 1:
        tips.append(f"Aim for {result['target_minutes']} active minutes a week: you have {result['minutes']}.")
    if result["form"] < 1:
        tips.append("Slow, full-range reps protect your joints and load your bones better.")
    tips.append(load_environments().get(run.environment, {}).get("advice_notes", ""))
    return {
        "saved": True, "loading_index": result["score"], "before": run.before, "status": status,
        "sets": [{**item, "name": NAMES[item["exercise_type"]]} for item in run.finished_sets],
        "breakdown": result, "xp": outcome.xp_gained, "tips": [tip for tip in tips if tip][:3],
        "previous": None if previous is None else {"date": previous.started_at.date().isoformat(),
                                                   "loading_index": previous.loading_index,
                                                   "summary": previous.summary},
    }


def preview(astronaut_id: int, run: ExerciseRun, now: datetime) -> int:
    """What the loading index would be if the workout ended now (for "78 → 84 after today")."""
    extra = [SetSummary(item["exercise_type"], now, item["reps"], item["duration_s"], item["cadence_spm"],
                        item["form_score"], item.get("effort_1_10")) for item in run.finished_sets]
    if run.current is not None and run.current.started_t is not None:
        counter = run.current.counter
        extra.append(SetSummary(run.current.exercise, now, counter.reps,
                                (run.current.last_t or 0) - run.current.started_t, None, counter.form))
    return compute(trailing_sets(astronaut_id, now, extra), run.environment)["score"]
