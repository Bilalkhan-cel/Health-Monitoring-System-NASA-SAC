"""/doctor page, text chat, voice proxy and the OpenHome bridge API."""

from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, render_template, request, session

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import csrf, db, limiter, sock
from ..models import Astronaut, utcnow
from ..services import openhome_service, rules_engine, whisper_service
from ..services.live import get_runtime
from ..services.summary import build_summary
from . import services

bp = Blueprint("doctor", __name__)
PROMPTS = {"summary": "How am I doing today?"}


def _config():
    return current_app.extensions["astrovital_config"]


@bp.get("/doctor")
@login_required
def index():
    crew = current_crew()
    config = _config()
    payload = build_summary(crew, config)
    metrics = {item["key"]: item for item in payload["metrics"]}
    sees = [metrics[key] for key in ("heart_rate", "blood_pressure", "sleep_hours", "wellbeing", "loading_index")]
    turns = [{"role": row.role, "content": row.content, "engine": row.engine}
             for row in services.history(crew.id, _since())]
    return render_template("doctor.html", sees=sees, turns=turns, mission=payload["mission"],
                           mode=openhome_service.mode(config), ask=PROMPTS.get(request.args.get("ask", "")),
                           callsign=crew.callsign)


@bp.post("/doctor/chat")
@login_required
def chat():
    message = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not message:
        return jsonify(ok=False, error="empty", message="Type a question first."), 400
    if len(message) > 2000:
        return jsonify(ok=False, error="too_long", message="Please keep it under 2000 characters."), 400
    answer = services.reply(current_crew(), message, _config(), get_runtime(), since=_since())
    return jsonify(ok=True, reply=answer.text, engine=answer.engine)


@bp.post("/doctor/new")
@login_required
def new_consultation():
    """Start a fresh conversation view. Earlier messages stay stored; they are just not shown."""
    session["consult_since"] = utcnow().isoformat()
    return jsonify(ok=True)


def _since():
    from datetime import datetime

    value = session.get("consult_since")
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


@bp.post("/doctor/session")
@login_required
def session_start():
    session = services.open_session(current_crew().id)
    return jsonify(ok=True, session_id=session.id, expires_at=session.expires_at.isoformat() + "Z",
                   mode=openhome_service.mode(_config()))


@bp.post("/doctor/session/end")
@login_required
def session_end():
    services.end_session(current_crew().id)
    return jsonify(ok=True)


# ── OpenHome bridge (token, tunnel-reachable, single active session) ──

def _bridge_guard():
    if not services.bridge_token_ok(_config(), request.headers.get("X-AstroVital-Token", "")):
        services.audit("bridge_bad_token", None, {"path": request.path})
        return None, (jsonify(ok=False, error="bad_token"), 401)
    session, error = services.bridge_session()
    if error:
        services.audit(f"bridge_{error}", None, {"path": request.path})
        return None, (jsonify(ok=False, error=error), 409 if error == "ambiguous_session" else 404)
    return session, None


@bp.get("/api/openhome/context")
@csrf.exempt
@limiter.limit("30/minute")
def bridge_context():
    session, error = _bridge_guard()
    if error:
        return error
    context = services.context_for(session.astronaut_id, _config(), get_runtime())
    services.audit("bridge_context", session.astronaut_id)
    return jsonify(context)


@bp.post("/api/openhome/log")
@csrf.exempt
@limiter.limit("30/minute")
def bridge_log():
    session, error = _bridge_guard()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = services.voice_log(db.session.get(Astronaut, session.astronaut_id), str(data.get("metric")),
                                     float(data.get("value")))
    except (TypeError, ValueError) as problem:
        return jsonify(ok=False, error="bad_log", message=str(problem)), 400
    services.audit("bridge_log", session.astronaut_id, {"metric": data.get("metric")})
    return jsonify(ok=True, message=message)


@bp.get("/api/openhome/health")
@login_required
def bridge_health():
    return jsonify(status=openhome_service.health(_config()), mode=openhome_service.mode(_config()))


# ── voice proxy ──────────────────────────────────────────

def origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    config = _config()
    host = (urlsplit(origin).hostname or "").lower()
    public = (urlsplit(config.public_base_url).hostname or "").lower()
    return host in config.trusted_hosts or (bool(public) and host == public)


@sock.route("/ws/doctor/voice")
def voice(ws):
    """Relay the browser's microphone to OpenHome (or the mock) and stream captions/audio back."""
    crew = current_crew()
    config = _config()
    if crew is None or crew.is_surgeon or not origin_allowed(request.headers.get("Origin")):
        ws.close(1008, "not allowed")
        return
    app = current_app._get_current_object()
    runtime = get_runtime()
    crew_id = crew.id
    send_lock = threading.Lock()

    def to_browser(frame: dict) -> None:
        try:
            with send_lock:
                ws.send(json.dumps(frame))
        except Exception:  # noqa: BLE001 (browser went away)
            pass

    def answer(text: str) -> str:
        with app.app_context():
            context = services.context_for(crew_id, config, runtime)
            return rules_engine.answer(text, context, voice=True)

    def transcribe(pcm: bytes) -> str | None:
        import tempfile
        import wave
        from pathlib import Path

        model_dir = config.whisper_model_path / config.whisper_model_size
        if not whisper_service.available(model_dir):
            return None
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "turn.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(pcm)
            return whisper_service.transcribe(path, model_dir, config.whisper_compute_type)

    services.touch_session(crew_id)
    db.session.commit()
    mode = openhome_service.mode(config)
    to_browser({"type": "state", "data": {"mode": mode, "state": "connecting"}})
    if mode == "live":
        upstream = openhome_service.OpenHomeUpstream(config, to_browser)
        if not upstream.wait_open(8):
            to_browser({"type": "state", "data": {"mode": mode, "state": "offline"}})
            upstream.close()
            ws.close()
            return
        upstream.send({"type": "transcribed", "data": "Doctor Nova, check my health"})
    else:
        greeting = f"Dr. Nova here, {crew.callsign}. I have your latest data. What would you like to check?"
        upstream = openhome_service.MockUpstream(to_browser, answer, greeting, transcribe)
    to_browser({"type": "state", "data": {"mode": mode, "state": "live"}})
    last_beat = time.monotonic()
    try:
        while not upstream.closed.is_set():
            raw = ws.receive(timeout=30)
            if raw is None:
                continue
            try:
                frame = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if frame.get("type") not in ("audio", "text", "transcribed", "ping", "ack"):
                continue
            if time.monotonic() - last_beat > 10:
                last_beat = time.monotonic()
                with app.app_context():
                    services.touch_session(crew_id)
                    from ..extensions import db as _db

                    _db.session.commit()
            upstream.send(frame)
    except Exception:  # noqa: BLE001 (browser closed the socket)
        pass
    finally:
        upstream.close()
