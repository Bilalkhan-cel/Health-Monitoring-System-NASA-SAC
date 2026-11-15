"""Health history (Section 14): timeline, calendar heatmap, day detail and CSV export.

Records are read-only here: nothing is ever overwritten. Mental-health entries carry their
status and score only; transcripts never appear in history or exports. No row carries a
source column.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..models import (Astronaut, CardioSession, ExerciseSession, Measurement, MentalCheckin, ReadinessDaily,
                      SleepLog)
from . import thresholds
from .readiness import load_indicators
from .summary import number_text

SYSTEMS = ("all", "cardio", "bones", "mental", "sleep")
KINDS = ("all", "heart_check", "exercise", "checkin", "sleep")
STATUS_KEYS = ("good", "okay", "watch", "alert")
MAX_RANGE_DAYS = 400
KIND_SYSTEM = {"heart_check": "cardio", "exercise": "bones", "checkin": "mental", "sleep": "sleep"}
KIND_TITLE = {"heart_check": "Heart check", "exercise": "Exercise session", "checkin": "Voice check-in",
              "sleep": "Sleep log"}
EXERCISE_NAMES = {"run": "running", "pushup": "push-ups", "pullup": "pull-ups", "squat": "squats",
                  "device_log": "device workout"}
CSV_COLUMNS = ("date", "time_utc", "metric", "value", "value2", "unit", "status")


@dataclass(frozen=True)
class Filters:
    system: str = "all"
    kind: str = "all"
    status: str = "all"
    start: date | None = None
    end: date | None = None

    @classmethod
    def parse(cls, args, today: date) -> "Filters":
        """Read filters from a query string, falling back to safe defaults for anything odd."""
        system = args.get("system", "all")
        kind = args.get("kind", "all")
        status = args.get("status", "all")
        end = _parse_day(args.get("to")) or today
        start = _parse_day(args.get("from")) or end - timedelta(days=29)
        if start > end:
            start, end = end, start
        start = max(start, end - timedelta(days=MAX_RANGE_DAYS - 1))
        return cls(system=system if system in SYSTEMS else "all", kind=kind if kind in KINDS else "all",
                   status=status if status in STATUS_KEYS else "all", start=start, end=end)

    def as_query(self) -> dict[str, str]:
        return {"system": self.system, "kind": self.kind, "status": self.status,
                "from": self.start.isoformat(), "to": self.end.isoformat()}


def _parse_day(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _key(status: str | None) -> str | None:
    return thresholds.STATUS_META[status]["key"] if status in thresholds.STATUS_META else None


def _span(filters: Filters) -> tuple[datetime, datetime]:
    return (datetime.combine(filters.start, datetime.min.time()),
            datetime.combine(filters.end + timedelta(days=1), datetime.min.time()))


def _entries(astronaut_id: int, filters: Filters) -> list[dict]:
    """Every assessment in the range as a plain dict, newest first."""
    lo, hi = _span(filters)
    out: list[dict] = []
    for row in CardioSession.query.filter(CardioSession.astronaut_id == astronaut_id,
                                          CardioSession.started_at >= lo, CardioSession.started_at < hi,
                                          CardioSession.ended_at.isnot(None)):
        parts = []
        if row.avg_hr is not None:
            parts.append(f"heart rate {row.avg_hr:.0f}")
        if row.avg_sys is not None and row.avg_dia is not None:
            parts.append(f"blood pressure {row.avg_sys:.0f}/{row.avg_dia:.0f}")
        if row.avg_spo2 is not None:
            parts.append(f"oxygen {row.avg_spo2:.0f} %")
        out.append({"kind": "heart_check", "at": row.started_at, "status": row.overall_status,
                    "text": row.summary or (", ".join(parts).capitalize() or "Heart check saved.")})
    for row in ExerciseSession.query.filter(ExerciseSession.astronaut_id == astronaut_id,
                                            ExerciseSession.started_at >= lo, ExerciseSession.started_at < hi,
                                            ExerciseSession.ended_at.isnot(None)):
        moves = []
        for item in row.sets:
            name = EXERCISE_NAMES.get(item.exercise_type, item.exercise_type)
            moves.append(f"{item.reps} {name}" if item.reps else name)
        text = row.summary or ("Did " + ", ".join(moves) + "." if moves else "Exercise session saved.")
        if row.loading_index is not None:
            text += f" Exercise load {row.loading_index:.0f}."
        out.append({"kind": "exercise", "at": row.started_at, "status": row.overall_status, "text": text})
    for row in MentalCheckin.query.filter(MentalCheckin.astronaut_id == astronaut_id,
                                          MentalCheckin.started_at >= lo, MentalCheckin.started_at < hi,
                                          MentalCheckin.status.in_(("done", "safety_flag"))):
        status = "CAUTION" if row.wellbeing_score is not None and row.wellbeing_score < 55 else (
            "STABLE" if row.wellbeing_score is not None and row.wellbeing_score < 70 else "NOMINAL")
        if row.safety_flag:
            status = "CRITICAL"
        score = f"Wellbeing {row.wellbeing_score:.0f}." if row.wellbeing_score is not None else "Check-in saved."
        out.append({"kind": "checkin", "at": row.started_at, "status": status, "text": score})
    for row in SleepLog.query.filter(SleepLog.astronaut_id == astronaut_id, SleepLog.date >= filters.start,
                                     SleepLog.date <= filters.end):
        status = thresholds.classify("sleep_hours", row.hours)["status"]
        out.append({"kind": "sleep", "at": datetime.combine(row.date, datetime.min.time()), "status": status,
                    "text": f"Slept {row.hours:g} hours."})
    keep = []
    for entry in out:
        entry["system"] = KIND_SYSTEM[entry["kind"]]
        entry["status_key"] = _key(entry["status"])
        if filters.system != "all" and entry["system"] != filters.system:
            continue
        if filters.kind != "all" and entry["kind"] != filters.kind:
            continue
        if filters.status != "all" and entry["status_key"] != filters.status:
            continue
        keep.append(entry)
    keep.sort(key=lambda entry: entry["at"], reverse=True)
    return keep


def _entry_json(entry: dict) -> dict:
    meta = thresholds.STATUS_META.get(entry["status"])
    return {"kind": entry["kind"], "title": KIND_TITLE[entry["kind"]], "system": entry["system"],
            "at": entry["at"].isoformat() + "Z", "time": entry["at"].strftime("%H:%M") if entry["kind"] != "sleep"
            else None, "text": entry["text"],
            "status": {"key": meta["key"], "label": meta["label"], "icon": meta["icon"]} if meta else None}


def timeline(astronaut: Astronaut, filters: Filters) -> list[dict]:
    """Cards per day: each day lists its assessments and the worst status of the day."""
    days: dict[date, list[dict]] = {}
    for entry in _entries(astronaut.id, filters):
        days.setdefault(entry["at"].date(), []).append(entry)
    out = []
    for day, entries in sorted(days.items(), reverse=True):
        worst = thresholds.worst([entry["status"] for entry in entries])
        out.append({"date": day.isoformat(), "label": f"{day:%a} {day.day} {day:%b}",
                    "status_key": _key(worst), "entries": [_entry_json(entry) for entry in entries]})
    return out


def heatmap(astronaut: Astronaut, filters: Filters) -> list[dict]:
    """Readiness per day for the calendar (Mon-first weeks). Missing days have no score."""
    rows = {row.date: row for row in ReadinessDaily.query.filter(
        ReadinessDaily.astronaut_id == astronaut.id, ReadinessDaily.date >= filters.start,
        ReadinessDaily.date <= filters.end)}
    out = []
    day = filters.start
    while day <= filters.end:
        row = rows.get(day)
        status = json.loads(row.breakdown_json or "{}").get("status") if row else None
        out.append({"date": day.isoformat(), "weekday": day.weekday(), "day": day.day,
                    "score": round(row.score) if row and row.score is not None else None,
                    "status_key": _key(status) if row and row.score is not None else None})
        day += timedelta(days=1)
    return out


def day_detail(astronaut: Astronaut, day: date) -> dict:
    """Everything recorded on one day: assessments plus every reading, oldest first."""
    filters = Filters(start=day, end=day)
    lo, hi = _span(filters)
    spec = load_indicators()["metrics"]
    readings = []
    for row in (Measurement.query.filter(Measurement.astronaut_id == astronaut.id, Measurement.created_at >= lo,
                                         Measurement.created_at < hi)
                .order_by(Measurement.created_at)):
        if row.metric not in spec:
            continue
        meta = thresholds.STATUS_META.get(row.status)
        readings.append({"time": row.created_at.strftime("%H:%M"), "metric": spec[row.metric]["short"],
                         "value": number_text(row.metric, row.value, row.value2),
                         "status": {"key": meta["key"], "label": meta["label"], "icon": meta["icon"]} if meta
                         else None})
    readiness = ReadinessDaily.query.filter_by(astronaut_id=astronaut.id, date=day).first()
    return {"date": day.isoformat(), "label": f"{day:%A} {day.day} {day:%B}",
            "readiness": round(readiness.score) if readiness and readiness.score is not None else None,
            "entries": [_entry_json(entry) for entry in reversed(_entries(astronaut.id, filters))],
            "readings": readings[-300:], "readings_total": len(readings)}


def csv_text(astronaut: Astronaut, filters: Filters) -> str:
    """Every reading in the range. Columns: date, time, metric, value(s), unit, status."""
    lo, hi = _span(filters)
    spec = load_indicators()["metrics"]
    wanted = None
    if filters.system != "all":
        wanted = set(load_indicators()["systems"].get(
            {"cardio": "heart", "bones": "bones", "mental": "mind", "sleep": "mind"}[filters.system], {})
            .get("metrics", []))
        if filters.system == "sleep":
            wanted = {"sleep_hours"}
        elif filters.system == "mental":
            wanted = {"wellbeing"}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    query = (Measurement.query.filter(Measurement.astronaut_id == astronaut.id, Measurement.created_at >= lo,
                                      Measurement.created_at < hi)
             .order_by(Measurement.created_at))
    for row in query.yield_per(2000):
        if row.metric not in spec or (wanted is not None and row.metric not in wanted):
            continue
        status = _key(row.status)
        if filters.status != "all" and status != filters.status:
            continue
        label = thresholds.STATUS_META[row.status]["label"] if row.status in thresholds.STATUS_META else ""
        writer.writerow((row.created_at.date().isoformat(), row.created_at.strftime("%H:%M:%S"),
                         spec[row.metric]["short"], f"{row.value:g}",
                         f"{row.value2:g}" if row.value2 is not None else "", row.unit, label))
    return buffer.getvalue()
