"""Builds what the browser sees: the Today summary and chart history.

Nothing returned from this module carries a ``source`` field or any other hint of
where a number came from (Section 0 rule 3). A metric is its name, value, unit,
status word and age, nothing else.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from statistics import median

import yaml

from config import BASE_DIR, Config

from ..extensions import db
from ..models import Astronaut, DailyTask, IntakeLog, Measurement, Mission, ReadinessDaily, SleepLog, utcnow
from . import readiness as readiness_service
from . import thresholds
from .readiness import MetricState, Readiness

LOOKBACK_DAYS = thresholds.BASELINE_WINDOW_DAYS + thresholds.BASELINE_EXCLUDE_DAYS
SPARK_POINTS = 7
MAX_CHART_POINTS = 500
READINESS_CAPTION = "Wellness estimate · not a fitness-for-duty decision"
RANGES = {"7d": 7, "30d": 30}


@lru_cache(maxsize=1)
def load_environments() -> dict:
    return yaml.safe_load((BASE_DIR / "config" / "environments.yaml").read_text(encoding="utf-8"))


@dataclass
class MetricView:
    """Everything known about one metric at a point in time."""

    key: str
    latest: Measurement | None = None
    status: str | None = None
    direction: str | None = None
    baseline: thresholds.Baseline | None = None
    baseline_days: int = 0
    notable: bool = False
    spark: tuple[float, ...] = ()
    age_s: float | None = None


# ── formatting ────────────────────────────────────────────

def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds") + "Z"


def ago(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)} h ago"
    return f"{int(seconds // 86400)} days ago"


def duration_text(seconds: float) -> str:
    """'12 min 40 s', '1.3 s' or '2 s'."""
    if seconds < 60:
        return f"{seconds:g} s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest} s" if rest else f"{minutes} min"


def hours_text(hours: float) -> str:
    whole, minutes = divmod(int(round(hours * 60)), 60)
    return f"{whole} h {minutes:02d} min"


def number_text(metric: str, value: float, value2: float | None = None) -> str:
    if metric == "blood_pressure":
        return f"{value:.0f}/{value2:.0f}"
    if metric == "sleep_hours":
        return hours_text(value)
    if metric == "hydration_ml":
        return f"{value / 1000:.1f}"
    decimals = readiness_service.load_indicators()["metrics"][metric]["decimals"]
    return f"{value:.{decimals}f}"


def unit_text(metric: str) -> str:
    unit = readiness_service.load_indicators()["metrics"][metric]["unit"]
    return "" if metric == "sleep_hours" else unit


def usual_text(view: "MetricView") -> str:
    """A person's usual value as text (systolic only for blood pressure)."""
    return number_text(view.key, view.baseline.median, 0).split("/")[0]


def status_json(status: str | None, direction: str | None = None) -> dict | None:
    if status is None:
        return None
    described = thresholds.describe(status, direction)
    return {"key": described["key"], "label": described["label"], "verdict": described["verdict"],
            "icon": described["icon"]}


# ── reading the data ──────────────────────────────────────

def _baseline_context(metric: str) -> str | None:
    if metric == "glucose":
        return "fasting"
    return thresholds.REST_CONTEXT if thresholds.requires_rest(metric) else None


def _daily_medians(rows: list[Measurement], metric: str) -> dict[date, float]:
    """One value per day; measured rows win over generated ones when 7 days of them exist."""
    wanted = _baseline_context(metric)
    rows = [row for row in rows if wanted is None or row.context == wanted]
    measured = [row for row in rows if row.source != "simulated"]
    if len({row.created_at.date() for row in measured}) >= thresholds.BASELINE_MIN_DAYS:
        rows = measured
    by_day: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        by_day[row.created_at.date()].append(row.value)
    return {day: median(values) for day, values in by_day.items()}


def metric_view(astronaut_id: int, metric: str, as_of: datetime) -> MetricView:
    """Latest classified value of a metric with its baseline comparison."""
    since = as_of - timedelta(days=LOOKBACK_DAYS + 1)
    query = Measurement.query.filter(
        Measurement.astronaut_id == astronaut_id, Measurement.metric == metric,
        Measurement.status.isnot(None), Measurement.created_at <= as_of)
    rows = query.filter(Measurement.created_at >= since).order_by(Measurement.created_at).all()
    latest = rows[-1] if rows else query.order_by(Measurement.created_at.desc()).first()
    view = MetricView(metric, latest)
    if latest is None:
        return view

    verdict = thresholds.classify_measurement(metric, latest.value, latest.value2, latest.context)
    view.status, view.direction = latest.status, verdict["direction"] if verdict else None
    view.age_s = max(0.0, (as_of - latest.created_at).total_seconds())
    view.spark = tuple(row.value for row in rows[-SPARK_POINTS:]) or (latest.value,)

    params = thresholds.baseline_params(metric, latest.context)
    daily = _daily_medians(rows, metric)
    view.baseline, view.baseline_days = thresholds.compute_baseline(daily, as_of.date())
    comparable = _baseline_context(metric) in (None, latest.context)
    if view.baseline and params and comparable:
        view.notable = thresholds.is_notable(latest.value, view.baseline, params)
        recent = [daily[day] for day in sorted(daily) if day > view.baseline.end]
        if thresholds.should_escalate(recent, view.baseline, params):
            escalated = thresholds.apply_baseline(view.status, True)
            if escalated != view.status:
                view.status = escalated
                view.direction = "high" if latest.value > view.baseline.median else "low"
    return view


def metric_views(astronaut_id: int, as_of: datetime) -> dict[str, MetricView]:
    metrics = readiness_service.load_indicators()["metrics"]
    return {metric: metric_view(astronaut_id, metric, as_of) for metric in metrics if metric != "hydration_ml"}


def readiness_from(views: dict[str, MetricView]) -> Readiness:
    states = {key: MetricState(view.status, view.age_s / 3600) for key, view in views.items()
              if view.latest is not None and view.age_s is not None}
    return readiness_service.compute(states)


def store_readiness(astronaut_id: int, day: date, as_of: datetime | None = None) -> Readiness:
    """Compute readiness as of a moment and upsert that day's ``ReadinessDaily`` row."""
    as_of = as_of or utcnow()
    result = readiness_from(metric_views(astronaut_id, as_of))
    row = ReadinessDaily.query.filter_by(astronaut_id=astronaut_id, date=day).first()
    if row is None:
        row = ReadinessDaily(astronaut_id=astronaut_id, date=day)
        db.session.add(row)
    row.score = result.score
    row.breakdown_json = json.dumps(result.breakdown())
    return result


# ── sentences ─────────────────────────────────────────────

def _phrase(view: MetricView, short: str) -> str:
    """'heart rate is higher than your usual' / 'sleep is a bit low'."""
    name = short.lower()
    if view.notable and view.baseline:
        side = "higher" if view.latest.value > view.baseline.median else "lower"
        return f"{name} is {side} than your usual"
    if view.direction:
        return f"{name} is {'very' if view.status == 'CRITICAL' else 'a bit'} {view.direction}"
    return f"{name} needs attention"


def readiness_sentence(result: Readiness, views: dict[str, MetricView]) -> str:
    """One plain sentence about the day, naming what needs attention (heart first)."""
    metrics = readiness_service.load_indicators()["metrics"]
    if result.score is None:
        return "Not enough data yet. Do today's checks to see your score."
    order = list(metrics)
    flagged = sorted((key for key, status in result.fresh_metrics.items() if status in ("CAUTION", "CRITICAL")),
                     key=lambda key: (-thresholds.rank(result.fresh_metrics[key]), order.index(key)))
    phrases = [f"your {_phrase(views[key], metrics[key]['short'])}" for key in flagged]
    if result.status == "CRITICAL":
        return f"Get help now: {phrases[0]}. Tell your crew medical officer."
    if not flagged:
        return "All good. Keep it up." if result.status == "NOMINAL" else "Everything is inside normal limits."
    if len(flagged) == 1:
        return f"Mostly good. One thing needs attention: {phrases[0]}."
    if len(flagged) == 2:
        return f"Two things need attention: {phrases[0]}, and {phrases[1]}."
    return f"{len(flagged)} things need attention, starting with {phrases[0]}."


def system_headline(system: str, status: str | None, worst_view: MetricView | None, short: str) -> str:
    if status is None or worst_view is None:
        return "No recent readings yet. Do today's check to see how this is doing."
    if status == "NOMINAL":
        return {"heart": "Your heart numbers look good.", "mind": "Your mood and sleep look good.",
                "bones": "Your bones and muscles are getting the load they need."}[system]
    if status == "STABLE":
        return "Everything here is inside normal limits."
    shown = f"{number_text(worst_view.key, worst_view.latest.value, worst_view.latest.value2)} " \
            f"{unit_text(worst_view.key)}".strip()
    sentence = f"Your {short.lower()} is {shown}."
    if worst_view.notable and worst_view.baseline:
        sentence += f" Your usual is {usual_text(worst_view)}."
    if status == "CRITICAL":
        sentence += " Tell your crew medical officer now."
    return sentence


# ── summary ───────────────────────────────────────────────

def mission_json(mission: Mission, config: Config, now: datetime) -> dict:
    environment = load_environments().get(mission.environment, {})
    delay = mission.comms_delay_s if mission.comms_delay_s is not None else environment.get("comms_delay_one_way_s", 0)
    return {
        "name": mission.name, "day": config.mission_day, "environment": mission.environment,
        "gravity_g": environment.get("gravity_g"), "comms_delay_s": delay, "comms_delay_text": duration_text(delay),
        "date_text": f"{now:%A}, {now.day} {now:%B}",
    }


def _metric_json(view: MetricView, spec: dict, system: str) -> dict:
    latest = view.latest
    item = {
        "key": view.key, "label": spec["label"], "short": spec["short"], "system": system, "info": spec["info"],
        "value": None, "unit": unit_text(view.key), "status": None, "age_s": None, "updated": "No reading yet",
        "spark": [], "usual": None, "note": None,
    }
    if latest is None:
        return item
    item.update(
        value=number_text(view.key, latest.value, latest.value2), status=status_json(view.status, view.direction),
        age_s=round(view.age_s), updated=f"Updated {ago(view.age_s)}", spark=[round(v, 1) for v in view.spark],
    )
    if view.baseline:
        usual = usual_text(view)
        if view.notable:
            delta = latest.value - view.baseline.median
            amount = hours_text(abs(delta)) if view.key == "sleep_hours" else f"{abs(delta):.{spec['decimals']}f}"
            item["usual"] = f"{amount} {'above' if delta > 0 else 'below'} your usual ({usual})"
        else:
            item["usual"] = f"Close to your usual ({usual})"
    elif thresholds.baseline_params(view.key, latest.context):
        item["usual"] = f"Your usual: building ({view.baseline_days}/{thresholds.BASELINE_MIN_DAYS} days)"
    if not latest.confirmed:
        item["note"] = "Re-measure to confirm."
    return item


def _tasks_json(astronaut: Astronaut, today: date, water_ml: int, task_links: dict[str, str]) -> dict:
    spec = readiness_service.load_indicators()
    done = {task.task_code: task for task in DailyTask.query.filter_by(astronaut_id=astronaut.id, date=today)
            if task.done}
    sleep = SleepLog.query.filter_by(astronaut_id=astronaut.id, date=today).first()
    goal = spec["hydration_goal_ml"]
    items = []
    for code, task in spec["tasks"].items():
        item = {"code": code, "label": task["label"], "state": "due", "detail": task["hint"], "action": None,
                "url": task_links.get(code)}
        if code == "hydration":
            item["detail"] = f"{water_ml / 1000:.1f} of {goal / 1000:.1f} litres"
            item["action"] = "water"
        elif code == "sleep_log":
            item["action"] = "sleep"
        if code in done:
            item["state"] = "done"
            item["action"] = "water" if code == "hydration" else None
            if code == "sleep_log" and sleep:
                item["detail"] = hours_text(sleep.hours)
            elif code != "hydration":
                item["detail"] = f"Done at {done[code].done_at:%H:%M}"
        elif code not in ("hydration", "sleep_log") and item["url"] is None:
            item["state"] = "later"
            item["detail"] = "Not available in this build"
        items.append(item)
    return {"done": sum(item["state"] == "done" for item in items), "total": len(items),
            "streak": astronaut.streak, "items": items}


def build_summary(astronaut: Astronaut, config: Config, now: datetime | None = None,
                  task_links: dict[str, str] | None = None) -> dict:
    """The full Today payload for one astronaut."""
    now = now or utcnow()
    from . import recommendations  # local import: recommendations reads load_environments from here

    spec = readiness_service.load_indicators()
    views = metric_views(astronaut.id, now)
    result = readiness_from(views)
    mission = mission_json(astronaut.mission, config, now)

    intake = IntakeLog.query.filter_by(astronaut_id=astronaut.id, date=now.date()).first()
    water_ml = intake.water_ml if intake else 0

    metrics, systems, alerts = [], {}, []
    for system, system_spec in spec["systems"].items():
        keys = [key for key in system_spec["metrics"] if key in views]
        for key in keys:
            metrics.append(_metric_json(views[key], spec["metrics"][key], system))
        scored = result.systems.get(system)
        ranked = sorted((views[k] for k in keys if views[k].status),
                        key=lambda v: (-thresholds.rank(v.status), keys.index(v.key)))
        worst_view = ranked[0] if ranked else None
        status = scored.status if scored else None
        systems[system] = {
            "id": system, "label": system_spec["label"], "title": system_spec["title"], "icon": system_spec["icon"],
            "score": scored.score if scored else None, "status": status_json(status),
            "headline": system_headline(system, status, worst_view,
                                        spec["metrics"][worst_view.key]["short"] if worst_view else ""),
            "do": spec["metrics"][worst_view.key]["info"]["do"]
            if worst_view and status in ("CAUTION", "CRITICAL") else None,
            "steps": recommendations.steps(system, status, mission["environment"], mission["comms_delay_text"]),
            "metrics": [view.key for view in ranked[:3]],
        }
        for view in ranked:
            fresh_h = spec["metrics"][view.key]["fresh_h"]
            if view.status == "CRITICAL" and view.latest.confirmed and view.age_s <= fresh_h * 3600:
                shown = f"{number_text(view.key, view.latest.value, view.latest.value2)} {unit_text(view.key)}".strip()
                alerts.append({
                    "metric": view.key, "system": system,
                    "text": f"Your {spec['metrics'][view.key]['short'].lower()} is very "
                            f"{view.direction or 'far from normal'} ({shown}). Tell your crew medical officer now. "
                            f"Messages to Earth take {mission['comms_delay_text']}.",
                })

    metrics.append({
        "key": "hydration_ml", "label": spec["metrics"]["hydration_ml"]["label"], "short": "Water", "system": "heart",
        "info": spec["metrics"]["hydration_ml"]["info"], "value": f"{water_ml / 1000:.1f}", "unit": "L",
        "status": None, "age_s": None, "updated": f"Goal {spec['hydration_goal_ml'] / 1000:.1f} L", "spark": [],
        "usual": None, "note": None,
    })

    hour = now.hour
    return {
        "protocol": recommendations.protocol(mission["environment"], mission["comms_delay_text"]),
        "generated_at": iso(now),
        "greeting": "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening",
        "astronaut": {"first_name": astronaut.first_name, "name": astronaut.name, "callsign": astronaut.callsign,
                      "initials": astronaut.initials, "role": astronaut.role},
        "mission": mission,
        "readiness": {"score": result.score, "status": status_json(result.status),
                      "sentence": readiness_sentence(result, views), "caption": READINESS_CAPTION},
        "systems": systems,
        "metrics": metrics,
        "alerts": alerts,
        "tasks": _tasks_json(astronaut, now.date(), water_ml, task_links or {}),
        "hydration": {"ml": water_ml, "goal_ml": spec["hydration_goal_ml"], "glass_ml": spec["glass_ml"]},
    }


# ── history ───────────────────────────────────────────────

def _bucket(points: list[dict], limit: int = MAX_CHART_POINTS) -> list[dict]:
    """Reduce a series to at most ``limit`` points (median per bucket)."""
    if len(points) <= limit:
        return points
    size = -(-len(points) // limit)
    reduced = []
    for start in range(0, len(points), size):
        chunk = points[start:start + size]
        middle = dict(chunk[len(chunk) // 2])
        middle["v"] = round(median(point["v"] for point in chunk), 2)
        reduced.append(middle)
    return reduced


def build_history(astronaut: Astronaut, config: Config, metric: str, range_key: str,
                  now: datetime | None = None) -> dict:
    """Chart series for ``readiness`` or one metric over 7 d, 30 d or the whole mission."""
    now = now or utcnow()
    spec = readiness_service.load_indicators()["metrics"]
    days = RANGES.get(range_key) or max(7, config.mission_day)
    start_day = now.date() - timedelta(days=days - 1)
    key_of = {name: meta["key"] for name, meta in thresholds.STATUS_META.items()}
    points, tiles, events = [], [], []

    if metric == "readiness":
        label, unit, reference = "Readiness", "/100", [80, 50]
        rows = (ReadinessDaily.query.filter(ReadinessDaily.astronaut_id == astronaut.id,
                                            ReadinessDaily.date >= start_day, ReadinessDaily.date <= now.date())
                .order_by(ReadinessDaily.date).all())
        for row in rows:
            breakdown = json.loads(row.breakdown_json or "{}")
            status = breakdown.get("status")
            tiles.append({"date": row.date.isoformat(), "status": key_of.get(status)})
            if row.score is None:
                continue
            points.append({"t": row.date.isoformat(), "v": row.score, "status": key_of.get(status)})
            if status == "CRITICAL" and breakdown.get("worst_metric") in spec:
                name = spec[breakdown["worst_metric"]]["short"].lower()
                events.append({"t": row.date.isoformat(), "v": row.score, "status": "alert",
                               "label": f"{row.date:%b} {row.date.day} · {name}"})
    elif metric in spec and metric != "hydration_ml":
        label, unit = spec[metric]["short"], unit_text(metric) or "h"
        table = thresholds.load_rules()[thresholds.table_name(metric if metric != "blood_pressure" else "systolic",
                                                              "fasting" if metric == "glucose" else None)]
        reference = [bound for bound in table["nominal"][0] if bound is not None]
        rows = (Measurement.query.filter(Measurement.astronaut_id == astronaut.id, Measurement.metric == metric,
                                         Measurement.created_at >= datetime.combine(start_day, datetime.min.time()),
                                         Measurement.created_at <= now)
                .order_by(Measurement.created_at).all())
        worst_by_day: dict[date, str | None] = {}
        for row in rows:
            point = {"t": iso(row.created_at), "v": round(row.value, 2), "status": key_of.get(row.status)}
            if row.value2 is not None:
                point["v2"] = round(row.value2, 2)
            points.append(point)
            day = row.created_at.date()
            worst_by_day[day] = thresholds.worst([worst_by_day.get(day), row.status])
            if row.status == "CRITICAL":
                shown = number_text(metric, row.value, row.value2)
                events.append({"t": point["t"], "v": point["v"], "status": "alert",
                               "label": f"{row.created_at:%b} {row.created_at.day} · {shown}"})
        tiles = [{"date": (start_day + timedelta(days=i)).isoformat(),
                  "status": key_of.get(worst_by_day.get(start_day + timedelta(days=i)))} for i in range(days)]
        points = _bucket(points)
    else:
        raise KeyError(metric)

    values = [point["v"] for point in points]
    if values:
        text = (f"{label} over the last {days} days: lowest {min(values):g}, highest {max(values):g}, "
                f"latest {values[-1]:g}. {len(events)} day(s) needed urgent attention.")
    else:
        text = f"No {label.lower()} data for this period yet."
    return {"metric": metric, "label": label, "unit": unit, "range": range_key, "points": points, "tiles": tiles,
            "events": events[:12], "reference": reference, "summary": text}
