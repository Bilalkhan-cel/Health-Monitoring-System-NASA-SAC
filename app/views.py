"""Template helpers shared by every page: navigation, the mission chip and icons."""

from __future__ import annotations

from flask import Flask, current_app, request, url_for

from config import ENVIRONMENTS, VERSION, Config

from .auth.services import current_crew
from .services.mission import mission_day
from .services.units import current_units

# (endpoint, label, icon). An item is shown only when its page exists, so nothing is dead.
NAV = (
    ("dashboard.index", "Today", "layout-grid"),
    ("cardio.index", "Heart", "heart"),
    ("musculoskeletal.index", "Body", "bone"),
    ("mental.index", "Mind", "mic"),
    ("doctor.index", "Dr. NOVA", "stethoscope"),
    ("history.index", "History", "history"),
)
SURGEON_NAV = (("mission_control.index", "Crew", "users"),)


def has_endpoint(name: str) -> bool:
    return name in current_app.view_functions


def nav_items() -> list[dict]:
    crew = current_crew()
    source = SURGEON_NAV if crew is not None and crew.is_surgeon else NAV
    active = request.endpoint or ""
    items = []
    for endpoint, label, icon in source:
        if not has_endpoint(endpoint):
            continue
        section = endpoint.split(".")[0]
        items.append({"url": url_for(endpoint), "label": label, "icon": icon,
                      "active": active.split(".")[0] == section})
    return items


def mission_chip(config: Config) -> dict | None:
    crew = current_crew()
    if crew is None:
        return None
    from .services.summary import load_environments, duration_text

    mission = crew.mission
    environment = load_environments().get(mission.environment, {})
    delay = mission.comms_delay_s if mission.comms_delay_s is not None \
        else environment.get("comms_delay_one_way_s", 0)
    return {"day": mission_day(config, mission), "environment": mission.environment, "options": ENVIRONMENTS,
            "gravity_g": environment.get("gravity_g"), "comms_delay_text": duration_text(delay)}


def reduce_motion() -> bool:
    """Settings → Reduce motion, for the logged-in astronaut (the OS setting is honoured in CSS)."""
    crew = current_crew()
    if crew is None:
        return False
    from .models import UserSettings

    row = UserSettings.query.filter_by(astronaut_id=crew.id).first()
    return bool(row and row.reduced_motion)


def register_template_helpers(app: Flask, config: Config) -> None:
    @app.context_processor
    def inject_globals() -> dict[str, object]:
        return {
            "app_version": VERSION,
            "mission_name": config.mission_name,
            "crew": current_crew(),
            "has_endpoint": has_endpoint,
            "nav_items": nav_items,
            "mission_chip": lambda: mission_chip(config),
            "demo_mode": config.demo_mode,
            "display_units": current_units,
            "reduce_motion": reduce_motion,
        }
