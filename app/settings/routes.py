"""Settings routes. Phase 1 ships the environment picker; the full page arrives in Phase 10."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from config import ENVIRONMENTS

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import AuditLog

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
