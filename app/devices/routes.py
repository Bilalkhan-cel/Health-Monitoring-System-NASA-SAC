"""/api/device/ingest, /api/device/ping (wearable) and /api/live, /api/stream (browser).

# SECURITY NOTE: the wearable talks plain HTTP on the local network with a shared token.
# Anyone on the same Wi-Fi could read the token. Production needs TLS with a pinned
# certificate and a per-device key. The host guard keeps these routes off any tunnel.
"""

from __future__ import annotations

import hmac
import json
from datetime import timedelta

from flask import Blueprint, Response, current_app, jsonify, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import csrf, db, limiter
from ..models import Astronaut, Device, DeviceEvent, utcnow
from ..services.live import get_runtime
from ..services.sensors.device_gateway import DatabaseBusy, ingest as ingest_batch
from ..services.sensors.frames import MAX_BODY_BYTES, BadPayload
from ..services.stream_hub import TooManyStreams, stream
from ..services.thresholds import load_rules

bp = Blueprint("devices", __name__)
TOKEN_EVENT_EVERY = timedelta(minutes=1)


def _config():
    return current_app.extensions["astrovital_config"]


def _device_key() -> str:
    return "device:" + (request.headers.get("X-Device-Id") or "unknown")[:40]


def _device_limit() -> str:
    return _config().device_rate_limit


def _token_ok() -> bool:
    expected = _config().device_token
    supplied = request.headers.get("X-Device-Token", "")
    return bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())


def _reject_token(device_id: str) -> tuple:
    runtime = get_runtime()
    device = Device.query.filter_by(device_id=device_id).first()
    now = utcnow()
    last = runtime.token_rejections.get(device_id)
    if device is not None and (last is None or now - last > TOKEN_EVENT_EVERY):
        runtime.token_rejections[device_id] = now
        db.session.add(DeviceEvent(device_pk=device.id, ts=now, kind="token_rejected"))
        db.session.commit()
    return jsonify(ok=False, error="bad_token"), 401


def _find_device(device_id: str) -> Device | None:
    device = Device.query.filter_by(device_id=device_id).first()
    config = _config()
    if device is None and config.device_auto_register and device_id:
        wearer = Astronaut.query.filter_by(astro_id=config.device_wearer_id, is_surgeon=False).first()
        if wearer is not None:
            device = Device(device_id=device_id, astronaut_id=wearer.id, label="Auto-registered wearable",
                            temp_site=config.temp_site, temp_offset_c=config.temp_offset_c)
            db.session.add(device)
            db.session.commit()
    return device


@bp.post("/api/device/ingest")
@csrf.exempt
@limiter.limit(_device_limit, key_func=_device_key)
def ingest():
    if not _config().device_enabled:
        return jsonify(ok=False, error="disabled"), 404
    device_id = request.headers.get("X-Device-Id", "")
    if not _token_ok():
        return _reject_token(device_id)
    if (request.content_length or 0) > MAX_BODY_BYTES:
        return jsonify(ok=False, error="too_large"), 413
    raw = request.get_data(cache=False)
    if len(raw) > MAX_BODY_BYTES:
        return jsonify(ok=False, error="too_large"), 413
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return jsonify(ok=False, error="bad_payload", path="$"), 400
    if not isinstance(payload, dict) or payload.get("device_id") != device_id:
        return jsonify(ok=False, error="bad_payload", path="device_id"), 400
    device = _find_device(device_id)
    if device is None:
        return jsonify(ok=False, error="unknown_device"), 401
    now = utcnow()
    try:
        result = ingest_batch(get_runtime(), device, payload, now, request.remote_addr)
    except BadPayload as error:
        db.session.rollback()
        return jsonify(ok=False, error="bad_payload", path=error.path), 400
    except DatabaseBusy:
        response = jsonify(ok=False, error="busy")
        response.status_code = 503
        response.headers["Retry-After"] = "2"
        return response
    return jsonify(result.as_json(now))


@bp.get("/api/device/ping")
@csrf.exempt
@limiter.limit(_device_limit, key_func=_device_key)
def ping():
    if not _config().device_enabled:
        return jsonify(ok=False, error="disabled"), 404
    if not _token_ok():
        return _reject_token(request.headers.get("X-Device-Id", ""))
    now = utcnow()
    return jsonify(ok=True, server="astrovital", server_time=now.isoformat(timespec="seconds") + "Z",
                   cfg={"rev": 1, "send_interval_ms": 1000})


def live_snapshot(astronaut_id: int) -> dict:
    linked = Device.query.filter_by(astronaut_id=astronaut_id).first() is not None
    consecutive = load_rules()["alert_confirm"]["heart_rate"]["wearable"]["consecutive_frames"]
    return get_runtime().live.snapshot(astronaut_id, utcnow(), linked=linked, consecutive=consecutive)


@bp.get("/api/live")
@login_required
def live():
    return jsonify(live_snapshot(current_crew().id))


@bp.get("/api/stream")
@login_required
def events():
    runtime = get_runtime()
    crew = current_crew()
    try:
        subscription = runtime.hub.subscribe(runtime.hub.topic_for(crew.id))
    except TooManyStreams:
        return jsonify(ok=False, error="too_many_streams"), 429
    first = [("snapshot", live_snapshot(crew.id))]
    response = Response(stream(runtime.hub, subscription, first), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
