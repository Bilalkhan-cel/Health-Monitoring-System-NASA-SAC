"""/mission-control (Section 16): flight surgeon only, every view written to the audit log."""

from __future__ import annotations

import json

from flask import Blueprint, abort, render_template

from ..auth.decorators import surgeon_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import Astronaut, AuditLog, utcnow
from ..services import crew_view

bp = Blueprint("mission_control", __name__)


def _audit(action: str, target: Astronaut | None = None) -> None:
    surgeon = current_crew()
    db.session.add(AuditLog(actor=surgeon.astro_id, action=action, target_astronaut_id=target.id if target else None,
                            meta_json=json.dumps({"view": action})))
    db.session.commit()


@bp.get("/mission-control")
@surgeon_required
def index():
    grid = crew_view.crew_grid(utcnow())
    _audit("mission_control_view")
    return render_template("mission_control.html", crew_grid=grid)


@bp.get("/mission-control/crew/<astro_id>")
@surgeon_required
def crew(astro_id: str):
    astronaut = Astronaut.query.filter_by(astro_id=astro_id, is_surgeon=False).first()
    if astronaut is None:
        abort(404)
    detail = crew_view.crew_detail(astronaut, utcnow())
    _audit("mission_control_crew_view", astronaut)
    return render_template("mission_control_crew.html", detail=detail)
