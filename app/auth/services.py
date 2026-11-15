"""Login, logout and the current crew member.

# SECURITY NOTE: login by Astro ID alone is a prototype shortcut. A real crew system
# needs multi-factor authentication (badge, biometric or hardware key). The host guard
# keeps the login page off the public tunnel.
"""

from __future__ import annotations

import re

from flask import current_app, g, session

from ..extensions import db
from ..models import Astronaut, AuditLog, utcnow

SESSION_KEY = "crew_id"
ID_PATTERN = re.compile(r"^[A-Z0-9-]{3,32}$")


def normalise_id(raw: str | None) -> str:
    return (raw or "").strip().upper()


def registered_ids() -> set[str]:
    """IDs Mission Control registered in .env. Anything else cannot log in."""
    config = current_app.extensions["astrovital_config"]
    return {member.astro_id for member in (*config.astronauts, *config.surgeons)}


def find_crew(astro_id: str) -> Astronaut | None:
    """Return the crew member for a submitted ID, or ``None``."""
    astro_id = normalise_id(astro_id)
    if not ID_PATTERN.match(astro_id) or astro_id not in registered_ids():
        return None
    return Astronaut.query.filter_by(astro_id=astro_id).first()


def log_in(crew: Astronaut) -> None:
    session.clear()
    session[SESSION_KEY] = crew.id
    crew.last_active_at = utcnow()
    db.session.add(AuditLog(actor=crew.astro_id, action="login", target_astronaut_id=crew.id))
    db.session.commit()


def log_out() -> None:
    crew = current_crew()
    if crew is not None:
        db.session.add(AuditLog(actor=crew.astro_id, action="logout", target_astronaut_id=crew.id))
        db.session.commit()
    session.clear()


def load_current_crew() -> None:
    """``before_request`` hook: put the logged-in crew member on ``g``."""
    g.crew = None
    crew_id = session.get(SESSION_KEY)
    if crew_id is None:
        return
    crew = db.session.get(Astronaut, crew_id)
    if crew is None or crew.astro_id not in registered_ids():
        session.clear()  # removed from .env since the last visit
        return
    g.crew = crew


def current_crew() -> Astronaut | None:
    return getattr(g, "crew", None)


def home_endpoint(crew: Astronaut) -> str:
    """Where a crew member lands after logging in."""
    return "mission_control.index" if crew.is_surgeon and "mission_control.index" in current_app.view_functions \
        else "dashboard.index"
