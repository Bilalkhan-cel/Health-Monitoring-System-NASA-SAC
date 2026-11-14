"""Demo history: 30 days of realistic, deterministic data per astronaut.

Every row is stored with ``source = simulated`` (which the UI never shows) and is
written through ``measurements.record(live=False)``, so it gets the same
classification as any other reading. The data tells a story on first launch:

* astronaut 1: a sleep-debt streak, a rising resting heart rate and a mood dip
  over the last three days, plus one blood-pressure emergency 18 days ago;
* astronaut 2: no exercise for four days, so the exercise load drops;
* astronaut 3: steady, with one short night.

Blood pressure, glucose and respiration come from ``PhysiologyModel`` so seeded and
live generated values share one character. Idempotent: an astronaut who already has
readings is skipped.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from config import Config

from .extensions import db
from .models import (Astronaut, AuditLog, CardioSession, ChatMessage, DailyTask, ExerciseSession, ExerciseSet,
                     HealthProfile, IntakeLog, Measurement, MentalCheckin, Notification, ReadinessDaily, SleepLog,
                     utcnow)
from .services import gamification, measurements
from .services.readiness import load_indicators
from .services.sensors.physiology import PhysiologyModel, _unit, smooth_noise, stable_seed
from .services.summary import store_readiness

log = logging.getLogger(__name__)

SOURCE = "simulated"
BP_EVENT_DAYS_AGO = 18
PROFILES = (
    {"age": 41, "sex": "female", "height_cm": 168, "weight_kg": 63, "hr_base": 72, "sleep_base": 7.4,
     "mood_base": 78, "story": "sleep_debt"},
    {"age": 37, "sex": "male", "height_cm": 181, "weight_kg": 79, "hr_base": 64, "sleep_base": 7.6,
     "mood_base": 81, "story": "exercise_gap"},
    {"age": 34, "sex": "female", "height_cm": 172, "weight_kg": 66, "hr_base": 68, "sleep_base": 7.8,
     "mood_base": 84, "story": "steady"},
)
SLEEP_DEBT = {2: 5.6, 1: 5.2, 0: 5.4}      # days ago -> hours slept
HR_CLIMB = {2: 88, 1: 96, 0: 104}          # days ago -> resting heart rate
MOOD_DIP = {3: 71, 2: 66, 1: 62}           # days ago -> wellbeing score


def _wobble(seed: int, day: int, channel: int, size: float) -> float:
    """Deterministic day-to-day variation in [-size, size]."""
    return (_unit(seed, channel, day) * 2 - 1) * size


def _exercised(profile: dict, seed: int, days_ago: int) -> bool:
    if profile["story"] == "exercise_gap" and days_ago <= 3:
        return False
    rest_day = (days_ago + seed) % 7 in (2, 5)
    return not rest_day


def _loading_index(profile: dict, seed: int, days_ago: int, total_days: int) -> float:
    """Prototype loading index from the trailing 7 days (the full formula arrives with the exercise module)."""
    active = sum(_exercised(profile, seed, d) for d in range(days_ago, min(days_ago + 7, total_days)))
    volume, frequency = min(1.0, active * 45 / 300), min(1.0, active / 5)
    return round(100 * (0.40 * volume + 0.30 * frequency + 0.20 * 0.9 + 0.10 * 0.95), 0)


def _record(astronaut_id: int, metric: str, value: float, when: datetime, **extra) -> None:
    measurements.record(astronaut_id, metric, value, source=SOURCE, created_at=when, live=False, commit=False,
                        **extra)


def _task(astronaut_id: int, code: str, when: datetime) -> None:
    db.session.add(DailyTask(astronaut_id=astronaut_id, date=when.date(), task_code=code, done=True, done_at=when))


def _seed_day(astronaut: Astronaut, profile: dict, model: PhysiologyModel, seed: int, days_ago: int,
              now: datetime, total_days: int) -> None:
    """Write one day of readings, sessions and tasks."""
    sleep_debt = profile["story"] == "sleep_debt"
    day = (now - timedelta(days=days_ago)).date()
    if days_ago == 0:  # today's entries sit just before "now", whatever the hour
        wake, morning = now - timedelta(hours=2, minutes=20), now - timedelta(hours=2)
    else:
        wake, morning = datetime.combine(day, time(7, 5)), datetime.combine(day, time(8, 10))
    midday, afternoon = datetime.combine(day, time(13, 30)), datetime.combine(day, time(17, 0))
    evening, night = datetime.combine(day, time(20, 30)), datetime.combine(day, time(21, 0))
    index = total_days - days_ago

    # Sleep
    hours = profile["sleep_base"] + _wobble(seed, index, 1, 0.5)
    if sleep_debt and days_ago in SLEEP_DEBT:
        hours = SLEEP_DEBT[days_ago]
    if profile["story"] == "steady" and days_ago == 12:
        hours = 6.4
    hours = round(hours, 1)
    db.session.add(SleepLog(astronaut_id=astronaut.id, date=wake.date(), hours=hours,
                            quality_1_5=4 if hours >= 7 else 2, source=SOURCE, created_at=wake))
    _record(astronaut.id, "sleep_hours", hours, wake)
    _task(astronaut.id, "sleep_log", wake)

    # Morning heart check (resting)
    heart_rate = round(profile["hr_base"] + 3 * smooth_noise(seed, index, 3, 11))
    if sleep_debt and days_ago in HR_CLIMB:
        heart_rate = HR_CLIMB[days_ago]
    fasting = model.sample(wake, hr_live=heart_rate, hr_expected=profile["hr_base"])
    spo2 = round(98 + _wobble(seed, index, 2, 1))
    temperature = round(36.6 + _wobble(seed, index, 3, 0.25), 1)
    session = CardioSession(
        astronaut_id=astronaut.id, started_at=morning - timedelta(seconds=90), ended_at=morning,
        avg_hr=heart_rate, avg_sys=fasting["systolic"], avg_dia=fasting["diastolic"], avg_temp=temperature,
        avg_glucose=fasting["glucose"], glucose_context="fasting", avg_spo2=spo2, avg_resp=fasting["respiration"],
        rest_verified=True, summary="Morning heart check", created_at=morning)
    db.session.add(session)
    db.session.flush()
    common = {"session_type": "cardio", "session_id": session.id}
    _record(astronaut.id, "heart_rate", heart_rate, morning, context="resting", **common)
    _record(astronaut.id, "spo2", spo2, morning, **common)
    _record(astronaut.id, "temperature_c", temperature, morning, **common)
    _record(astronaut.id, "blood_pressure", fasting["systolic"], morning, value2=fasting["diastolic"],
            context="resting", **common)
    _record(astronaut.id, "glucose", fasting["glucose"], morning, context="fasting", **common)
    _record(astronaut.id, "respiration", fasting["respiration"], morning, context="resting", **common)
    session.overall_status = Measurement.query.filter_by(session_id=session.id, session_type="cardio") \
        .order_by(Measurement.status.is_(None)).first().status
    _task(astronaut.id, "cardio", morning)
    if days_ago == 0:
        water = 1100
    else:
        _seed_rest_of_day(astronaut, profile, model, seed, days_ago, total_days, heart_rate, midday, afternoon,
                          evening, night)
        water = int(2300 + _wobble(seed, index, 4, 350))
        _task(astronaut.id, "hydration", evening)
    db.session.add(IntakeLog(astronaut_id=astronaut.id, date=wake.date(), water_ml=water, created_at=wake))


def _seed_rest_of_day(astronaut: Astronaut, profile: dict, model: PhysiologyModel, seed: int, days_ago: int,
                      total_days: int, heart_rate: int, midday: datetime, afternoon: datetime, evening: datetime,
                      night: datetime) -> None:
    index = total_days - days_ago
    # Midday and evening readings
    for when in (midday, evening):
        sample = model.sample(when, hr_live=heart_rate, hr_expected=profile["hr_base"])
        systolic, diastolic = sample["systolic"], sample["diastolic"]
        if profile["story"] == "sleep_debt" and days_ago == BP_EVENT_DAYS_AGO and when is evening:
            systolic, diastolic = 186, 118  # the one "Get help now" event; it settles by the next morning
        _record(astronaut.id, "blood_pressure", systolic, when, value2=diastolic, context="resting")
        _record(astronaut.id, "glucose", sample["glucose"], when, context=sample["glucose_context"])
        _record(astronaut.id, "respiration", sample["respiration"], when, context="resting")
    _record(astronaut.id, "heart_rate", heart_rate + 3, evening, context="resting")

    # Exercise
    if _exercised(profile, seed, days_ago):
        workout = ExerciseSession(astronaut_id=astronaut.id, started_at=afternoon,
                                  ended_at=afternoon + timedelta(minutes=45), environment=astronaut.mission.environment,
                                  summary="Running and push-ups", created_at=afternoon)
        workout.sets = [
            ExerciseSet(exercise_type="run", duration_s=1500, cadence_spm=round(158 + _wobble(seed, index, 5, 6)),
                        form_score=None, created_at=afternoon),
            ExerciseSet(exercise_type="pushup", reps=int(22 + _wobble(seed, index, 6, 4)), duration_s=600,
                        form_score=round(82 + _wobble(seed, index, 7, 6)), created_at=afternoon),
        ]
        db.session.add(workout)
        _task(astronaut.id, "exercise", afternoon + timedelta(minutes=45))
    loading = _loading_index(profile, seed, days_ago, total_days)
    _record(astronaut.id, "loading_index", loading, afternoon + timedelta(minutes=50))

    # Evening voice check-in
    mood = round(profile["mood_base"] + _wobble(seed, index, 8, 5))
    if profile["story"] == "sleep_debt" and days_ago in MOOD_DIP:
        mood = MOOD_DIP[days_ago]
    themes = '["fatigue", "homesickness"]' if mood < 70 else "[]"
    db.session.add(MentalCheckin(
        astronaut_id=astronaut.id, started_at=night, duration_s=180, mode="voice", status="done",
        mood_category="Good" if mood >= 70 else "Okay" if mood >= 55 else "Low", confidence=0.8,
        themes_json=themes, wellbeing_score=mood, summary="Evening voice check-in", created_at=night))
    _record(astronaut.id, "wellbeing", mood, night + timedelta(minutes=4))
    _task(astronaut.id, "mental", night + timedelta(minutes=4))


def seed_astronaut(astronaut: Astronaut, profile: dict, config: Config, now: datetime) -> int:
    """Seed one astronaut. Returns the number of measurement rows written."""
    seed = stable_seed(astronaut.astro_id, config.mission_name)
    model = PhysiologyModel(seed, config.meal_times)
    health = HealthProfile.query.filter_by(astronaut_id=astronaut.id).first()
    for field in ("age", "sex", "height_cm", "weight_kg"):
        if getattr(health, field) is None:
            setattr(health, field, profile[field])
    for days_ago in range(config.seed_days - 1, -1, -1):
        _seed_day(astronaut, profile, model, seed, days_ago, now, config.seed_days)
        db.session.flush()
        end_of_day = now if days_ago == 0 else datetime.combine((now - timedelta(days=days_ago)).date(), time(23, 59))
        store_readiness(astronaut.id, end_of_day.date(), as_of=end_of_day)
    astronaut.streak = gamification.streak_for(astronaut.id, now.date())
    astronaut.xp = sum(load_indicators()["tasks"][task.task_code]["xp"]
                       for task in DailyTask.query.filter_by(astronaut_id=astronaut.id, done=True))
    astronaut.level = gamification.level_for(astronaut.xp)
    gamification.award_badges(astronaut, now)
    db.session.commit()
    return Measurement.query.filter_by(astronaut_id=astronaut.id).count()


def reset_health_data() -> None:
    """Delete every health record (crew accounts and settings are kept)."""
    for model in (ExerciseSet, ExerciseSession, CardioSession, MentalCheckin, ChatMessage, Measurement, SleepLog,
                  IntakeLog, ReadinessDaily, DailyTask, Notification, AuditLog):
        db.session.query(model).delete()
    db.session.commit()


def seed_demo_data(config: Config, *, reset: bool = False, now: datetime | None = None) -> dict[str, int]:
    """Seed every astronaut who has no readings yet. Must run inside an app context."""
    now = now or utcnow()
    if reset:
        reset_health_data()
    written: dict[str, int] = {}
    crew = Astronaut.query.filter_by(is_surgeon=False).order_by(Astronaut.id).all()
    for position, astronaut in enumerate(crew):
        if Measurement.query.filter_by(astronaut_id=astronaut.id).first():
            continue
        profile = PROFILES[position] if position < len(PROFILES) else dict(PROFILES[2], story="steady")
        written[astronaut.astro_id] = seed_astronaut(astronaut, profile, config, now)
        log.info("Seeded %d readings of demo history for %s", written[astronaut.astro_id], astronaut.astro_id)
    return written
