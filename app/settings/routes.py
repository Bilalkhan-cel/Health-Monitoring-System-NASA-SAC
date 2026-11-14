"""Settings routes. Phase 1 ships the environment picker; the full page arrives in Phase 10."""

from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, request

from config import ENVIRONMENTS

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import AuditLog, Device

bp = Blueprint("settings", __name__)


@bp.post("/settings/environment")
@login_required
def environment():
    """Change the mission environment.

    # SECURITY NOTE: any crew member may change the mission-wide environment. This is a
    # demo convenience; a real system would restrict it to the commander or Mission Control.
    """
    data = request.get_json(silent=True) or request.form
    choice = (data.get("environment") or "").strip()
    if choice not in ENVIRONMENTS:
        return jsonify(ok=False, error="unknown_environment"), 400
    crew = current_crew()
    mission = crew.mission
    previous = mission.environment
    mission.environment = choice
    mission.comms_delay_s = None  # a scenario override ends when the environment changes by hand
    db.session.add(AuditLog(actor=crew.astro_id, action="environment_change", target_astronaut_id=crew.id,
                            meta_json=json.dumps({"from": previous, "to": choice})))
    db.session.commit()
    return jsonify(ok=True, environment=choice)


@bp.post("/settings/sensor-mode")
@login_required
def sensor_mode():
    """Switch between the real wearable and demo data. The ONLY way the mode ever changes.

    Available only with DEMO_MODE=true, always by a person, always audited.
    """
    config = current_app.extensions["astrovital_config"]
    if not config.demo_mode:
        return jsonify(ok=False, error="demo_mode_off"), 404
    data = request.get_json(silent=True) or request.form
    mode = (data.get("mode") or "").strip()
    if mode not in ("device", "demo"):
        return jsonify(ok=False, error="unknown_mode"), 400
    crew = current_crew()
    mission = crew.mission
    previous = mission.sensor_mode
    if previous != mode:
        mission.sensor_mode = mode
        db.session.add(AuditLog(actor=crew.astro_id, action="sensor_mode_change", target_astronaut_id=crew.id,
                                meta_json=json.dumps({"from": previous, "to": mode})))
        runtime = current_app.extensions["live"]
        for device in Device.query.all():
            runtime.live.reset(device.astronaut_id)
            runtime.aggregator.flush(device.id)
        db.session.commit()
    return jsonify(ok=True, mode=mode)
