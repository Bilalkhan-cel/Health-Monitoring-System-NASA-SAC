"""/mental: the daily check-in."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import MentalCheckin
from ..services import nlp_service, whisper_service
from . import services

bp = Blueprint("mental", __name__)


def _config():
    return current_app.extensions["astrovital_config"]


def _bad(message: str, status: int = 400):
    return jsonify(ok=False, error="bad_request", message=message), status


def _rating(data, key: str, hi: int) -> int | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= hi else None


@bp.get("/mental")
@login_required
def index():
    config = _config()
    crew = current_crew()
    last = (MentalCheckin.query.filter(MentalCheckin.astronaut_id == crew.id, MentalCheckin.status == "done")
            .order_by(MentalCheckin.started_at.desc()).first())
    voice_ready = whisper_service.available(config.whisper_model_path / config.whisper_model_size)
    return render_template("mental.html", target_min=config.mental_session_target_min,
                           min_seconds=config.mental_session_min_seconds, max_min=config.mental_session_max_min,
                           last=last, voice_ready=voice_ready,
                           models_ready=nlp_service.models_available(config.nlp_sentiment_path,
                                                                     config.nlp_emotion_path),
                           prompts=nlp_service.mental_config()["prompts"],
                           store=services.stores_transcripts(crew.id, config))


@bp.post("/mental/start")
@login_required
def start():
    mode = (request.get_json(silent=True) or {}).get("mode", "voice")
    if mode not in ("voice", "text"):
        return _bad("mode must be voice or text")
    checkin = services.start(current_crew(), mode)
    return jsonify(ok=True, checkin_id=checkin.id)


@bp.post("/mental/chunk")
@login_required
def chunk():
    config = _config()
    checkin = services.owned(request.form.get("checkin_id", type=int) or 0, current_crew().id)
    if checkin is None:
        return _bad("Unknown check-in.", 404)
    if checkin.status not in ("recording", "processing"):
        return _bad("This check-in is finished.", 409)
    seq = request.form.get("seq", type=int)
    upload = request.files.get("audio")
    if seq is None or seq < 0 or upload is None:
        return _bad("checkin_id, seq and audio are required")
    data = upload.read(services.MAX_CHUNK_BYTES + 1)
    if len(data) > services.MAX_CHUNK_BYTES:
        return jsonify(ok=False, error="too_large", message="Audio chunks must be 2 MB or less."), 413
    try:
        stored, state = services.save_chunk(current_app._get_current_object(), checkin, seq, data, config)
    except ValueError as error:
        return _bad(str(error))
    return jsonify(ok=True, stored=stored, state=state)


@bp.get("/mental/status/<int:checkin_id>")
@login_required
def status(checkin_id: int):
    checkin = services.owned(checkin_id, current_crew().id)
    if checkin is None:
        return _bad("Unknown check-in.", 404)
    return jsonify(ok=True, **services.status(checkin))


@bp.post("/mental/text")
@login_required
def text():
    """Typed check-in: analysed at once (the safety screen runs first)."""
    data = request.get_json(silent=True) or {}
    body = (data.get("text") or "").strip()
    if len(body) < 3 and _rating(data, "self_mood", 10) is None:
        return _bad("Write a few words or choose a mood rating.")
    if len(body) > 8000:
        return _bad("Please keep it under 8000 characters.")
    checkin = services.start(current_crew(), "text")
    results = services.finish(current_app._get_current_object(), checkin, text=body,
                              self_mood=_rating(data, "self_mood", 10), self_sleep=_rating(data, "self_sleep", 5),
                              duration_s=None, config=_config())
    return jsonify(ok=True, results=results)


@bp.post("/mental/finish")
@login_required
def finish():
    data = request.get_json(silent=True) or {}
    checkin = services.owned(int(data.get("checkin_id") or 0), current_crew().id)
    if checkin is None:
        return _bad("Unknown check-in.", 404)
    if checkin.status in ("done", "failed"):
        return _bad("This check-in is already finished.", 409)
    pending = services.status(checkin)["pending"]
    if pending and not data.get("force"):
        checkin.status = "processing"
        db.session.commit()
        return jsonify(ok=True, processing=True, pending=pending), 202
    duration = data.get("duration_s")
    results = services.finish(current_app._get_current_object(), checkin, text=None,
                              self_mood=_rating(data, "self_mood", 10), self_sleep=_rating(data, "self_sleep", 5),
                              duration_s=float(duration) if isinstance(duration, (int, float)) else None,
                              config=_config())
    return jsonify(ok=True, results=results)


@bp.delete("/mental/<int:checkin_id>/transcript")
@login_required
def delete_transcript(checkin_id: int):
    checkin = services.owned(checkin_id, current_crew().id)
    if checkin is None:
        return _bad("Unknown check-in.", 404)
    services.delete_transcript(checkin)
    return jsonify(ok=True)
