"""Musculoskeletal Loading Index (Section 11), trailing 7 days.

    volume_ratio    = clip(active_minutes / weekly_active_min_target, 0, 1)
    frequency_ratio = clip(distinct_exercise_days / target_days, 0, 1)
    intensity_ratio = clip(mean_MET / target_met, 0, 1)
    form_ratio      = clip(mean_form_score / 80, 0, 1)      (camera sets only; 1.0 if none)
    loading_index   = 100 · (0.40·volume + 0.30·frequency + 0.20·intensity + 0.10·form)

A camera cannot measure bone density: this scores the mechanical loading exercise that
protects bone and muscle in reduced gravity. Prototype scale, not a clinical measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import ExerciseSession, ExerciseSet
from .summary import load_environments

MET = {"pushup": 3.8, "pullup": 4.0, "squat": 5.0}
RUN_MET = 8.0
REFERENCE_CADENCE = 165.0
SECONDS_PER_REP = 3


@dataclass(frozen=True)
class SetSummary:
    exercise_type: str
    day: datetime
    reps: int | None = None
    duration_s: float | None = None
    cadence_spm: float | None = None
    form_score: float | None = None
    effort_1_10: int | None = None


def active_minutes(item: SetSummary) -> float:
    if item.exercise_type in ("device_log", "run"):
        return (item.duration_s or 0) / 60
    return max(item.duration_s or 0, (item.reps or 0) * SECONDS_PER_REP) / 60


def met(item: SetSummary) -> float:
    if item.exercise_type == "device_log":
        return 3 + 0.5 * (item.effort_1_10 or 5)
    if item.exercise_type == "run":
        if not item.cadence_spm:
            return RUN_MET * 0.75
        return RUN_MET * max(0.6, min(1.2, item.cadence_spm / REFERENCE_CADENCE))
    return MET.get(item.exercise_type, 3.0)


def compute(sets: list[SetSummary], environment: str) -> dict:
    env = load_environments().get(environment, {})
    target_minutes = env.get("weekly_active_min_target", 300)
    target_days = env.get("target_days", 5)
    target_met = env.get("target_met", 5.0)
    minutes = sum(active_minutes(item) for item in sets)
    days = len({item.day.date() for item in sets if active_minutes(item) > 0})
    weighted = sum(met(item) * active_minutes(item) for item in sets)
    mean_met = weighted / minutes if minutes else 0.0
    forms = [item.form_score for item in sets if item.form_score is not None
             and item.exercise_type in ("pushup", "pullup", "squat")]
    form_ratio = min(1.0, (sum(forms) / len(forms)) / 80) if forms else 1.0
    volume = min(1.0, minutes / target_minutes) if target_minutes else 0.0
    frequency = min(1.0, days / target_days) if target_days else 0.0
    intensity = min(1.0, mean_met / target_met) if target_met else 0.0
    score = 100 * (0.40 * volume + 0.30 * frequency + 0.20 * intensity + 0.10 * form_ratio)
    if not sets:
        score = 0.0
    return {"score": round(score), "minutes": round(minutes), "days": days, "mean_met": round(mean_met, 1),
            "volume": round(volume, 2), "frequency": round(frequency, 2), "intensity": round(intensity, 2),
            "form": round(form_ratio, 2), "target_minutes": target_minutes, "target_days": target_days}


def trailing_sets(astronaut_id: int, now: datetime, extra: list[SetSummary] | None = None) -> list[SetSummary]:
    since = now - timedelta(days=7)
    rows = (ExerciseSet.query.join(ExerciseSession)
            .filter(ExerciseSession.astronaut_id == astronaut_id, ExerciseSession.started_at >= since,
                    ExerciseSession.started_at <= now).all())
    sets = [SetSummary(row.exercise_type, row.session.started_at, row.reps, row.duration_s, row.cadence_spm,
                       row.form_score, row.effort_1_10) for row in rows]
    return sets + (extra or [])


def days_since_exercise(astronaut_id: int, now: datetime) -> int | None:
    latest = (ExerciseSession.query.filter(ExerciseSession.astronaut_id == astronaut_id,
                                           ExerciseSession.ended_at.isnot(None))
              .order_by(ExerciseSession.started_at.desc()).first())
    return None if latest is None else (now.date() - latest.started_at.date()).days
