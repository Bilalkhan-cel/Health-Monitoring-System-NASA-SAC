"""/cardio: the guided heart check."""

from __future__ import annotations

import time

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import CardioSession, utcnow
from ..services import measurements, summary, units
from ..services.live import get_runtime
from ..services.stream_hub import format_sse
from . import services

bp = Blueprint("cardio", __name__)


def _config():
    return current_app.extensions["astrovital_config"]


def _run_or_404():
    run = services.runs(get_runtime()).get(current_crew().id)
    if run is None:
        return None, (jsonify(ok=False, error="no_session",
                              message="No heart check is running. Start a new one."), 404)
    return run, None


@bp.get("/cardio")
@login_required
def index():
    crew = current_crew()
    config = _config()
    payload = summary.build_summary(crew, config)
    metrics = {item["key"]: item for item in payload["metrics"]}
    latest = [metrics[key] for key in ("heart_rate", "blood_pressure", "spo2", "glucose", "respiration",
                                       "temperature_c") if key in metrics]
    last = (CardioSession.query.filter(CardioSession.astronaut_id == crew.id, CardioSession.ended_at.isnot(None))
            .order_by(CardioSession.ended_at.desc()).first())
    view = summary.metric_view(crew.id, "heart_rate", utcnow())
    usual = round(view.baseline.median) if view.baseline else None
    return render_template("cardio.html", latest=latest, usual=usual, system=payload["systems"]["heart"],
                           mission=payload["mission"], last=last, demo=config.demo_mode,
                           rest_seconds=services.REST_SECONDS, session_seconds=config.cardio_session_seconds,
                           symptoms=services.SYMPTOMS, alerts=payload["alerts"])


@bp.post("/cardio/start")
@login_required
def start():
    data = request.get_json(silent=True) or {}
    context = data.get("glucose_context", "random")
    if context not in services.GLUCOSE_CONTEXTS:
        return jsonify(ok=False, error="bad_context", message="Choose when you last ate."), 400
    symptoms = [s for s in data.get("symptoms", []) if s in services.SYMPTOMS]
    runtime = get_runtime()
    run = services.start(runtime, current_crew(), glucose_context=context, symptoms=symptoms, config=_config())
    wearable = services.wearable_state(runtime, current_crew().id, utcnow())
    return jsonify(ok=True, session_id=run.session_id, rest_seconds=services.REST_SECONDS,
                   can_skip=_config().demo_mode, wearable=wearable)


@bp.post("/cardio/measure")
@login_required
def measure():
    run, error = _run_or_404()
    if error:
        return error
    skipped = bool((request.get_json(silent=True) or {}).get("skip_rest"))
    if skipped and not _config().demo_mode:
        return jsonify(ok=False, error="rest_required", message="The 5-minute rest is required."), 400
    elapsed = (utcnow() - run.rest_started).total_seconds()
    if not skipped and elapsed < services.REST_SECONDS - 3:
        return jsonify(ok=False, error="rest_not_done", message="Keep resting until the countdown ends."), 400
    modes = (request.get_json(silent=True) or {}).get("modes") or {}
    run.modes.update({k: v for k, v in modes.items() if k in services.MANUAL_METRICS and v in ("wearable", "ble",
                                                                                                "manual")})
    services.begin_measuring(get_runtime(), run, skipped=skipped)
    wearable = services.wearable_state(get_runtime(), current_crew().id, utcnow())
    return jsonify(ok=True, duration_s=run.duration_s, rest_verified=run.rest_verified, wearable=wearable)


@bp.post("/cardio/pause")
@login_required
def pause():
    run, error = _run_or_404()
    if error:
        return error
    paused = bool((request.get_json(silent=True) or {}).get("paused"))
    now = utcnow()
    if paused and run.paused_at is None:
        run.paused_at = now
    elif not paused and run.paused_at is not None:
        run.paused_s += (now - run.paused_at).total_seconds()
        run.paused_at = None
    return jsonify(ok=True, paused=run.paused_at is not None)


@bp.post("/cardio/reading")
@login_required
def reading():
    run, error = _run_or_404()
    if error:
        return error
    try:
        payload = _stored_units(request.get_json(silent=True) or {})
        reply = services.add_reading(get_runtime(), run, current_crew(), payload, utcnow())
    except (ValueError, TypeError, measurements.InvalidReading) as problem:
        db.session.rollback()
        return jsonify(ok=False, error="bad_reading", message=str(problem)), 400
    return jsonify(reply)


def _stored_units(payload: dict) -> dict:
    """Typed temperature and blood sugar arrive in the astronaut's display units."""
    metric = payload.get("metric")
    if metric in ("temperature_c", "glucose"):
        try:
            payload = {**payload, "value": round(units.to_stored(metric, float(payload.get("value"))), 2)}
        except (TypeError, ValueError):
            pass  # add_reading reports the bad value
    return payload


@bp.post("/cardio/end")
@login_required
def end():
    run, error = _run_or_404()
    if error:
        return error
    if run.phase != "measure":
        services.runs(get_runtime()).pop(current_crew().id)
        return jsonify(ok=True, cancelled=True)
    results = services.finish(get_runtime(), run, current_crew(), _config())
    return jsonify(ok=True, results=results)


@bp.get("/cardio/stream")
@login_required
def stream():
    """Session-scoped SSE: one `reading` event per second. Reads only in-memory state."""
    run, error = _run_or_404()
    if error:
        return error
    runtime = get_runtime()
    crew = current_crew()
    config = _config()
    model = services.model_for(crew, config)
    session_id = run.session_id
    astronaut = type("Crew", (), {"id": crew.id, "astro_id": crew.astro_id})()

    def generate():
        finger_lost_at = None
        while True:
            current = services.runs(runtime).get(astronaut.id)
            if current is None or current.session_id != session_id:
                yield format_sse("ended", {"session_id": session_id})
                return
            now = utcnow()
            payload = services.live_reading(runtime, current, astronaut, config, now, model)
            # Lifting the finger pauses the countdown, for at most 60 s.
            if payload["waiting_for_finger"] and current.paused_at is None:
                current.paused_at, finger_lost_at = now, now
            elif finger_lost_at and (not payload["waiting_for_finger"] or
                                     (now - finger_lost_at).total_seconds() > services.MAX_PAUSE_S):
                current.paused_s += (now - current.paused_at).total_seconds()
                current.paused_at, finger_lost_at = None, None
                if payload["waiting_for_finger"]:
                    current.modes["heart_rate"] = "timeout"
            snap = runtime.live.entry(astronaut.id)
            if snap.ppg and payload["finger"]:
                payload["ppg"] = snap.ppg
            yield format_sse("reading", payload)
            if current.phase == "measure" and payload["remaining_s"] == 0:
                yield format_sse("complete", {"session_id": session_id})
                return
            time.sleep(1)

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
