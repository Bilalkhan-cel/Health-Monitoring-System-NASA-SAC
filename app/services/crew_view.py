"""Mission Control data (Section 16). The flight surgeon sees status colours, flags and
physiological metrics only: no readiness numbers on the grid, no transcripts and no
mental-health detail beyond a status colour.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..extensions import db
from ..models import Astronaut, CardioSession, ExerciseSession, Measurement, MentalCheckin
from . import thresholds
from .readiness import load_indicators
from .summary import ago, metric_views, number_text, readiness_from, unit_text

PHYSIOLOGICAL = ("heart_rate", "blood_pressure", "spo2", "temperature_c", "glucose", "respiration", "loading_index")
FLAG_WINDOW = timedelta(days=7)
DETAIL_DAYS = 14


def _with_unit(metric: str, value: float, value2: float | None) -> str:
    unit = unit_text(metric)
    text = number_text(metric, value, value2)
    return f"{text}{unit}" if unit.startswith("/") else f"{text} {unit}".strip()


def _status(status: str | None) -> dict | None:
    meta = thresholds.STATUS_META.get(status)
    return {"key": meta["key"], "label": meta["label"], "icon": meta["icon"]} if meta else None


def _last_checkin(astronaut_id: int) -> datetime | None:
    candidates = [
        db.session.query(db.func.max(CardioSession.ended_at)).filter_by(astronaut_id=astronaut_id).scalar(),
        db.session.query(db.func.max(ExerciseSession.ended_at)).filter_by(astronaut_id=astronaut_id).scalar(),
        db.session.query(db.func.max(MentalCheckin.started_at)).filter(
            MentalCheckin.astronaut_id == astronaut_id,
            MentalCheckin.status.in_(("done", "safety_flag"))).scalar(),
    ]
    found = [moment for moment in candidates if moment is not None]
    return max(found) if found else None


def crew_grid(now: datetime) -> list[dict]:
    spec = load_indicators()
    out = []
    for astronaut in Astronaut.query.filter_by(is_surgeon=False).order_by(Astronaut.astro_id):
        result = readiness_from(metric_views(astronaut.id, now))
        follow_up = MentalCheckin.query.filter(MentalCheckin.astronaut_id == astronaut.id,
                                               MentalCheckin.safety_flag.is_(True),
                                               MentalCheckin.started_at >= now - FLAG_WINDOW).first() is not None
        last = _last_checkin(astronaut.id)
        systems = []
        for system, system_spec in spec["systems"].items():
            scored = result.systems.get(system)
            systems.append({"id": system, "label": system_spec["label"],
                            "status": _status(scored.status if scored else None)})
        out.append({
            "astro_id": astronaut.astro_id, "name": astronaut.name, "role": astronaut.role,
            "callsign": astronaut.callsign, "initials": astronaut.initials,
            "status": _status(result.status), "systems": systems,
            "flags": ["Follow-up requested"] if follow_up else [],
            "last_checkin": f"{ago((now - last).total_seconds())}" if last else "No check-ins yet",
        })
    return out


def crew_detail(astronaut: Astronaut, now: datetime) -> dict:
    """Physiological metrics only, read-only."""
    spec = load_indicators()["metrics"]
    views = metric_views(astronaut.id, now)
    latest = []
    for key in PHYSIOLOGICAL:
        view = views.get(key)
        row = view.latest if view else None
        latest.append({"label": spec[key]["short"],
                       "value": _with_unit(key, row.value, row.value2) if row else "—",
                       "updated": ago(view.age_s) if row else "No reading yet",
                       "status": _status(view.status if view else None)})
    since = now - timedelta(days=DETAIL_DAYS)
    flagged = (Measurement.query.filter(Measurement.astronaut_id == astronaut.id,
                                        Measurement.metric.in_(PHYSIOLOGICAL), Measurement.created_at >= since,
                                        Measurement.status.in_(("CAUTION", "CRITICAL")))
               .order_by(Measurement.created_at.desc()).limit(40).all())
    seen, flags = set(), []
    for row in flagged:
        key = (row.metric, row.created_at.date(), row.status)
        if key in seen:
            continue
        seen.add(key)
        flags.append({"when": row.created_at.strftime("%d %b %H:%M"), "label": spec[row.metric]["short"],
                      "value": _with_unit(row.metric, row.value, row.value2),
                      "status": _status(row.status)})
    sessions = []
    for row in (CardioSession.query.filter(CardioSession.astronaut_id == astronaut.id,
                                           CardioSession.started_at >= since, CardioSession.ended_at.isnot(None))
                .order_by(CardioSession.started_at.desc()).limit(20)):
        sessions.append({"when": row.started_at, "kind": "Heart check", "status": _status(row.overall_status),
                         "text": f"Heart rate {row.avg_hr:.0f}" if row.avg_hr is not None else "Saved"})
    for row in (ExerciseSession.query.filter(ExerciseSession.astronaut_id == astronaut.id,
                                             ExerciseSession.started_at >= since,
                                             ExerciseSession.ended_at.isnot(None))
                .order_by(ExerciseSession.started_at.desc()).limit(20)):
        sessions.append({"when": row.started_at, "kind": "Exercise", "status": _status(row.overall_status),
                         "text": f"Exercise load {row.loading_index:.0f}" if row.loading_index is not None
                         else "Saved"})
    sessions.sort(key=lambda item: item["when"], reverse=True)
    for item in sessions:
        item["when"] = item["when"].strftime("%d %b %H:%M")
    mind = readiness_from(views).systems.get("mind")
    return {"astro_id": astronaut.astro_id, "name": astronaut.name, "role": astronaut.role,
            "callsign": astronaut.callsign, "latest": latest, "flags": flags[:15], "sessions": sessions[:20],
            "mind_status": _status(mind.status if mind else None), "days": DETAIL_DAYS}
