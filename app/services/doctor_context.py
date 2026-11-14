"""The ONE path that builds what Dr. NOVA knows (voice bridge and text chat alike).

Minimum necessary data (Appendix C): callsign, role, age, mission, latest readings with
status words, sources and ages, 14-day trends, baselines, recent sessions, alerts and
readiness. No full name, no email, no IDs, no other astronaut's data, no transcripts.
The ``source`` of each reading is for Dr. NOVA's reasoning only and never reaches a page.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from config import Config

from ..models import Astronaut, CardioSession, ExerciseSession, HealthProfile, MentalCheckin, Measurement, utcnow
from . import thresholds
from .mission import mission_day
from .readiness import load_indicators
from .summary import build_summary, iso, load_environments, metric_views, usual_text

SOURCE_WORDS = {
    "sensor": "measured by the wearable sensor",
    "derived": "estimated from the wearable's temperature probe",
    "manual": "entered by hand",
    "simulated": "generated for demonstration (no sensor for it is attached)",
    "cv": "counted by the camera from exercise movements",
    "nlp": "estimated from the voice check-in's words",
    "voice": "logged by voice",
}
METRIC_ORDER = ("heart_rate", "blood_pressure", "spo2", "temperature_c", "glucose", "respiration", "sleep_hours",
                "wellbeing", "loading_index")


def _value(row: Measurement) -> object:
    if row.metric == "blood_pressure":
        return {"sys": round(row.value), "dia": round(row.value2)}
    decimals = load_indicators()["metrics"][row.metric]["decimals"]
    return round(row.value, decimals) if decimals else round(row.value)


def _trend(astronaut_id: int, metric: str, now: datetime, baseline: float | None) -> dict | None:
    rows = (Measurement.query.filter(Measurement.astronaut_id == astronaut_id, Measurement.metric == metric,
                                     Measurement.status.isnot(None),
                                     Measurement.created_at >= now - timedelta(days=14))
            .order_by(Measurement.created_at).all())
    if len(rows) < 3:
        return None
    first = sum(r.value for r in rows[: len(rows) // 3]) / max(1, len(rows) // 3)
    last = sum(r.value for r in rows[-(len(rows) // 3):]) / max(1, len(rows) // 3)
    change = (last - first) / first * 100 if first else 0
    out = {"direction": "up" if change > 3 else "down" if change < -3 else "steady",
           "avg": round(sum(r.value for r in rows) / len(rows), 1)}
    if baseline:
        out["change_vs_baseline_pct"] = round((rows[-1].value - baseline) / baseline * 100)
    return out


def build(astronaut_id: int, config: Config, now: datetime | None = None, live: dict | None = None) -> dict:
    """The astronaut context for Dr. NOVA (Appendix C)."""
    from ..extensions import db

    now = now or utcnow()
    astronaut = db.session.get(Astronaut, astronaut_id)
    profile = HealthProfile.query.filter_by(astronaut_id=astronaut_id).first()
    mission = astronaut.mission
    environment = load_environments().get(mission.environment, {})
    delay = mission.comms_delay_s if mission.comms_delay_s is not None \
        else environment.get("comms_delay_one_way_s", 0)
    views = metric_views(astronaut_id, now)
    indicators = load_indicators()["metrics"]
    latest, trends = [], {}
    for metric in METRIC_ORDER:
        view = views.get(metric)
        if view is None or view.latest is None:
            continue
        row = view.latest
        verdict = thresholds.classify_measurement(metric, row.value, row.value2, row.context)
        item = {
            "metric": metric, "value": _value(row), "unit": indicators[metric]["unit"],
            "status_word": thresholds.STATUS_META[view.status]["label"] if view.status else None,
            "source": row.source, "at": iso(row.created_at),
            "data_age_h": round((now - row.created_at).total_seconds() / 3600, 1),
        }
        if verdict and verdict.get("direction") and view.status in ("CAUTION", "CRITICAL"):
            item["direction"] = verdict["direction"]
        if not row.confirmed:
            item["note"] = "unconfirmed: re-measure to confirm"
        if view.baseline:
            usual = usual_text(view)
            item["baseline"] = usual
            if view.notable:
                delta = row.value - view.baseline.median
                item["vs_baseline"] = f"{delta:+.0f} {indicators[metric]['unit']}".strip()
        latest.append(item)
        trend = _trend(astronaut_id, metric, now, view.baseline.median if view.baseline else None)
        if trend:
            trends[metric] = trend

    cardio = (CardioSession.query.filter(CardioSession.astronaut_id == astronaut_id,
                                         CardioSession.ended_at.isnot(None))
              .order_by(CardioSession.ended_at.desc()).first())
    exercise = (ExerciseSession.query.filter(ExerciseSession.astronaut_id == astronaut_id,
                                             ExerciseSession.ended_at.isnot(None))
                .order_by(ExerciseSession.started_at.desc()).first())
    mental = (MentalCheckin.query.filter(MentalCheckin.astronaut_id == astronaut_id, MentalCheckin.status == "done")
              .order_by(MentalCheckin.started_at.desc()).first())
    sessions = {}
    if cardio:
        sessions["cardio"] = (f"{_ago_words(now, cardio.ended_at)}: avg HR {cardio.avg_hr or '–'}, "
                              f"BP {round(cardio.avg_sys) if cardio.avg_sys else '–'}/"
                              f"{round(cardio.avg_dia) if cardio.avg_dia else '–'}, SpO2 {cardio.avg_spo2 or '–'}")
    if exercise:
        sessions["exercise"] = f"last session {_ago_words(now, exercise.started_at)}: {exercise.summary or 'workout'}"
    if mental:
        themes = json.loads(mental.themes_json or "[]")
        sessions["mental"] = f"mood {mental.mood_category}" + (f"; themes: {', '.join(themes)}" if themes else "")

    summary = build_summary(astronaut, config, now)
    readiness = summary["readiness"]
    context = {
        "generated_at": iso(now),
        "profile": {"callsign": astronaut.callsign, "role": astronaut.role,
                    "age": profile.age if profile else None},
        "mission": {"name": mission.name, "day": mission_day(config, mission), "environment": mission.environment,
                    "gravity_g": environment.get("gravity_g"), "comms_delay_one_way_s": delay},
        "units": {"temperature": "C", "glucose": "mg/dL"},
        "latest": latest,
        "trends_14d": trends,
        "recent_sessions": sessions,
        "active_alerts": [alert["text"] for alert in summary["alerts"]],
        "readiness": {"score": readiness["score"],
                      "status_word": readiness["status"]["label"] if readiness["status"] else None},
        "streak_days": astronaut.streak,
    }
    if live is not None:
        context["wearable"] = {"state": live.get("state"), "finger": bool(live.get("finger")),
                               "live_hr": live.get("hr"), "live_spo2": live.get("spo2")}
    return context


def _ago_words(now: datetime, then: datetime) -> str:
    days = (now.date() - then.date()).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def to_prompt_text(context: dict) -> str:
    """The context as a compact block for the text-chat and fallback LLM prompts."""
    return "ASTRONAUT CONTEXT:\n" + json.dumps(context, indent=1)


def source_sentence(item: dict) -> str:
    """A truthful answer to "how was this measured?" for one reading."""
    return SOURCE_WORDS.get(item.get("source"), "recorded by AstroVital")
