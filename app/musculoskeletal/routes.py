"""/musculoskeletal ("Body"): camera exercise tracking and the device log."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..models import ExerciseSession, utcnow
from ..services import loading_index as li
from ..services.live import get_runtime
from . import services

bp = Blueprint("musculoskeletal", __name__)


def _config():
    return current_app.extensions["astrovital_config"]


def _bad(message: str, status: int = 400):
    return jsonify(ok=False, error="bad_request", message=message), status


@bp.get("/musculoskeletal")
@login_required
def index():
    crew = current_crew()
    environment = crew.mission.environment
    allowed = services.allowed_exercises(environment)
    history = (ExerciseSession.query.filter(ExerciseSession.astronaut_id == crew.id,
                                            ExerciseSession.ended_at.isnot(None))
               .order_by(ExerciseSession.started_at.desc()).limit(5).all())
    breakdown = li.compute(li.trailing_sets(crew.id, utcnow()), environment)
    from ..services.summary import load_environments

    return render_template("musculoskeletal.html", environment=environment, allowed=allowed,
                           env=load_environments().get(environment, {}), plan=services.plan_for(environment),
                           names=services.NAMES, devices=services.DEVICES, history=history, breakdown=breakdown,
                           current=services.latest_loading(crew.id), backend=_config().pose_backend,
                           since=li.days_since_exercise(crew.id, utcnow()))


@bp.post("/musculoskeletal/start")
@login_required
def start():
    exercise = (request.get_json(silent=True) or {}).get("exercise")
    run = services.start(get_runtime(), current_crew())
    if exercise and exercise != "device_log":
        try:
            services.begin_set(run, exercise)
        except ValueError as error:
            return _bad(str(error))
    return jsonify(ok=True, session_id=run.session_id, exercise=exercise)


@bp.post("/musculoskeletal/keypoints")
@login_required
def keypoints():
    run = services.runs(get_runtime()).get(current_crew().id)
    if run is None:
        return _bad("Start a session first.", 404)
    frames = (request.get_json(silent=True) or {}).get("frames")
    if not isinstance(frames, list):
        return _bad("frames must be a list")
    try:
        reply = services.feed(run, frames)
    except ValueError as error:
        return _bad(str(error))
    reply["preview"] = services.preview(current_crew().id, run, utcnow())
    return jsonify(ok=True, **reply)


@bp.post("/musculoskeletal/frame")
@login_required
def frame():
    """Server-side pose (optional ViTPose backend). The default MediaPipe path never sends frames."""
    if _config().pose_backend != "hf_vitpose":
        return jsonify(ok=False, error="fast_mode", message="Frames stay in the browser in fast mode."), 409
    return jsonify(ok=False, error="model_missing",
                   message="Run python scripts/download_models.py --with-vitpose to enable server pose."), 503


@bp.post("/musculoskeletal/set")
@login_required
def next_set():
    run = services.runs(get_runtime()).get(current_crew().id)
    if run is None:
        return _bad("Start a session first.", 404)
    data = request.get_json(silent=True) or {}
    if data.get("exercise_type") == "device_log":
        try:
            item = services.log_device(run, data.get("device", ""), float(data.get("minutes", 0)),
                                       int(data.get("effort", 0)))
        except (TypeError, ValueError) as error:
            return _bad(str(error))
        return jsonify(ok=True, set=item, sets=len(run.finished_sets))
    closed = services.close_set(run)
    if data.get("next"):
        try:
            services.begin_set(run, data["next"])
        except ValueError as error:
            return _bad(str(error))
    return jsonify(ok=True, set=closed, sets=len(run.finished_sets),
                   preview=services.preview(current_crew().id, run, utcnow()))


@bp.post("/musculoskeletal/end")
@login_required
def end():
    try:
        results = services.finish(get_runtime(), current_crew())
    except LookupError as error:
        return _bad(str(error), 404)
    return jsonify(ok=True, results=results)
