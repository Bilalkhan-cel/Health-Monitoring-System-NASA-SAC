"""/dashboard ("Today"), /api/summary, /api/history, /api/bodypart, daily tasks and logs.

Every route is scoped to the logged-in astronaut. No response carries a ``source`` field.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import IntakeLog, SleepLog, utcnow
from ..services import gamification, measurements, summary
from ..services.readiness import load_indicators

bp = Blueprint("dashboard", __name__)

TASK_ENDPOINTS = {"cardio": "cardio.index", "exercise": "musculoskeletal.index", "mental": "mental.index"}
SYSTEM_ENDPOINTS = {"heart": "cardio.index", "bones": "musculoskeletal.index", "mind": "mental.index"}
SYSTEMS = ("heart", "mind", "bones")


def _config():
    return current_app.extensions["astrovital_config"]


def task_links() -> dict[str, str]:
    return {code: url_for(endpoint) for code, endpoint in TASK_ENDPOINTS.items()
            if endpoint in current_app.view_functions}


def catch_up_generated() -> None:
    """Keep the generated attributes current (rate-limited inside SimRecorder)."""
    runtime = current_app.extensions.get("live")
    if runtime is not None:
        crew = current_crew()
        hr_live = runtime.live.snapshot(crew.id, utcnow(), linked=True)["hr"]
        runtime.sim.catch_up(crew, utcnow(), hr_live=hr_live)


def current_summary() -> dict:
    catch_up_generated()
    payload = summary.build_summary(current_crew(), _config(), task_links=task_links())
    for system, endpoint in SYSTEM_ENDPOINTS.items():
        if endpoint in current_app.view_functions:
            payload["systems"][system]["start_url"] = url_for(endpoint)
    return payload


@bp.get("/dashboard")
@login_required
def index():
    return render_template("dashboard.html", summary=current_summary())


@bp.get("/api/summary")
@login_required
def api_summary():
    return jsonify(current_summary())


@bp.get("/api/alerts")
@login_required
def api_alerts():
    """Open critical alerts for the alert bar on every page."""
    payload = summary.build_summary(current_crew(), _config())
    return jsonify(alerts=payload["alerts"], protocol=payload["protocol"])


@bp.get("/api/history")
@login_required
def api_history():
    metric = request.args.get("metric", "readiness")
    range_key = request.args.get("range", "30d")
    if range_key not in ("7d", "30d", "mission"):
        return jsonify(ok=False, error="bad_range"), 400
    catch_up_generated()
    try:
        return jsonify(summary.build_history(current_crew(), _config(), metric, range_key))
    except KeyError:
        return jsonify(ok=False, error="unknown_metric"), 400


@bp.get("/api/bodypart/<system>")
@login_required
def api_bodypart(system: str):
    if system not in SYSTEMS:
        abort(404)
    payload = current_summary()
    part = dict(payload["systems"][system])
    by_key = {item["key"]: item for item in payload["metrics"]}
    part["rows"] = [by_key[key] for key in part["metrics"] if key in by_key]
    part["mission"] = payload["mission"]
    return jsonify(part)


@bp.get("/api/gamification")
@login_required
def api_gamification():
    return jsonify(gamification.summary_for(current_crew()))


def _number(name: str, lo: float, hi: float) -> float:
    try:
        value = float((request.get_json(silent=True) or {}).get(name))
    except (TypeError, ValueError):
        abort(400, description=f"{name} must be a number")
    if not lo <= value <= hi:
        abort(400, description=f"{name} must be between {lo:g} and {hi:g}")
    return value


@bp.post("/api/tasks/<code>/done")
@login_required
def task_done(code: str):
    """Hydration (add a glass) and the sleep log. Other tasks finish inside their module."""
    crew, now = current_crew(), utcnow()
    tasks = load_indicators()
    if code == "hydration":
        ml = int(_number("ml", 50, 2000)) if (request.get_json(silent=True) or {}).get("ml") else tasks["glass_ml"]
        intake = IntakeLog.query.filter_by(astronaut_id=crew.id, date=now.date()).first()
        if intake is None:
            intake = IntakeLog(astronaut_id=crew.id, date=now.date(), water_ml=0)
            db.session.add(intake)
        intake.water_ml += ml
        outcome = gamification.complete_task(crew, "hydration", now) \
            if intake.water_ml >= tasks["hydration_goal_ml"] else None
        db.session.commit()
        return jsonify(ok=True, water_ml=intake.water_ml, xp_gained=outcome.xp_gained if outcome else 0)
    if code == "sleep_log":
        hours = round(_number("hours", 0, 16), 2)
        quality = (request.get_json(silent=True) or {}).get("quality")
        quality = int(quality) if str(quality).isdigit() and 1 <= int(quality) <= 5 else None
        log = SleepLog.query.filter_by(astronaut_id=crew.id, date=now.date()).first()
        if log is None:
            log = SleepLog(astronaut_id=crew.id, date=now.date(), hours=hours)
            db.session.add(log)
        log.hours, log.quality_1_5, log.source = hours, quality, "manual"
        result = measurements.record(crew.id, "sleep_hours", hours, source="manual", created_at=now, commit=False)
        outcome = gamification.complete_task(crew, "sleep_log", now)
        db.session.commit()
        return jsonify(ok=True, status=result.status, xp_gained=outcome.xp_gained)
    if code in tasks["tasks"]:
        return jsonify(ok=False, error="finish_in_module",
                       message="This task is ticked when you finish the check."), 400
    abort(404)
