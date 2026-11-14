"""Start-up work that ``run.py`` performs before serving requests.

1. create or upgrade the database (Flask-Migrate),
2. upsert the mission, the crew from .env and the wearable's Device row,
3. seed 30 days of demo history on first run,
4. sweep leftover uploads.

Later phases hook the raw-frame purge and the generated-data catch-up in here too,
so start-up stays in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from flask import Flask
from flask_migrate import upgrade
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from config import BASE_DIR, Config

from . import get_config
from .extensions import db
from .models import Astronaut, Device, HealthProfile, Measurement, Mission, UserSettings, utcnow

log = logging.getLogger(__name__)

KEEP_FILES = {".gitkeep"}
MIGRATIONS_DIR = BASE_DIR / "migrations"


@dataclass(frozen=True)
class BootReport:
    """What start-up found, for the boot checklist."""

    db_ready: bool
    crew_loaded: int | None = None
    wearable_last_seen_s: float | None = None
    sensor_mode: str | None = None
    uploads_swept: int = 0
    seeded: int = 0


def ensure_database(app: Flask) -> bool:
    """Bring the schema up to date and prove the database answers."""
    try:
        with app.app_context():
            if MIGRATIONS_DIR.exists():
                upgrade(directory=str(MIGRATIONS_DIR))
            else:  # pragma: no cover - only when the migrations folder was deleted
                db.create_all()
            db.session.execute(text("SELECT 1"))
            db.session.commit()
        return True
    except (SQLAlchemyError, OSError):
        log.exception("Database could not be opened")
        return False


def upsert_mission(config: Config) -> Mission:
    """The mission row. Environment and sensor mode are only set on first creation."""
    mission = Mission.query.filter_by(name=config.mission_name).first()
    if mission is None:
        mission = Mission(name=config.mission_name, start_date=config.mission_start_date,
                          environment=config.default_environment, sensor_mode=config.sensor_mode)
        db.session.add(mission)
    else:
        mission.start_date = config.mission_start_date
    db.session.flush()
    return mission


def upsert_crew(config: Config, mission: Mission) -> int:
    """Create or update every crew member listed in .env. Returns how many astronauts are active."""
    for member in (*config.astronauts, *config.surgeons):
        crew = Astronaut.query.filter_by(astro_id=member.astro_id).first()
        if crew is None:
            crew = Astronaut(astro_id=member.astro_id, mission_id=mission.id)
            db.session.add(crew)
        crew.name, crew.role, crew.callsign = member.name, member.role, member.callsign
        crew.is_surgeon, crew.mission_id = member.is_surgeon, mission.id
        db.session.flush()
        if not member.is_surgeon:
            if UserSettings.query.filter_by(astronaut_id=crew.id).first() is None:
                db.session.add(UserSettings(astronaut_id=crew.id, store_transcripts=config.store_transcripts))
            if HealthProfile.query.filter_by(astronaut_id=crew.id).first() is None:
                db.session.add(HealthProfile(astronaut_id=crew.id))
    return len(config.astronauts)


def upsert_device(config: Config) -> Device | None:
    """The wearable's Device row. The wearer chosen in Settings is kept across restarts."""
    if not config.device_enabled:
        return None
    device = Device.query.filter_by(device_id=config.device_id).first()
    if device is None:
        wearer = Astronaut.query.filter_by(astro_id=config.device_wearer_id, is_surgeon=False).first() \
            or Astronaut.query.filter_by(is_surgeon=False).order_by(Astronaut.id).first()
        if wearer is None:
            return None
        device = Device(device_id=config.device_id, astronaut_id=wearer.id, label="Wrist wearable",
                        temp_site=config.temp_site, temp_offset_c=config.temp_offset_c)
        db.session.add(device)
    return device


def sweep_uploads(app: Flask) -> int:
    """Delete temporary audio left behind by an earlier run."""
    uploads: Path = get_config(app).uploads_dir
    uploads.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in uploads.iterdir():
        if path.is_file() and path.name not in KEEP_FILES:
            try:
                path.unlink()
                removed += 1
            except OSError:
                log.warning("Could not delete leftover upload %s", path.name)
    if removed:
        log.info("Removed %d leftover upload(s)", removed)
    return removed


def prepare_data(app: Flask, *, seed: bool | None = None) -> tuple[int, int, Mission]:
    """Upsert mission, crew and device; seed demo history when the database is empty."""
    config = get_config(app)
    from .seed import seed_demo_data

    mission = upsert_mission(config)
    crew = upsert_crew(config, mission)
    upsert_device(config)
    db.session.commit()
    seeded = 0
    should_seed = config.seed_on_first_run if seed is None else seed
    if should_seed and db.session.query(Measurement.id).first() is None:
        seeded = sum(seed_demo_data(config).values())
    return crew, seeded, mission


def _hooks(app: Flask) -> list:
    return app.extensions.setdefault("astrovital_boot_hooks", [])


def register_hook(app: Flask, hook) -> None:
    """Later phases add start-up steps (purge, catch-up) here."""
    _hooks(app).append(hook)


def run(app: Flask) -> BootReport:
    """Run every start-up step and report the outcome."""
    if not ensure_database(app):
        return BootReport(db_ready=False)
    with app.app_context():
        crew, seeded, mission = prepare_data(app)
        report = {"crew_loaded": crew, "sensor_mode": mission.sensor_mode, "seeded": seeded}
        device = Device.query.filter_by(device_id=get_config(app).device_id).first()
        if device is not None and device.last_seen_at is not None:
            report["wearable_last_seen_s"] = (utcnow() - device.last_seen_at).total_seconds()
        for hook in _hooks(app):
            hook(app)
    swept = sweep_uploads(app)
    return BootReport(db_ready=True, uploads_swept=swept, **report)


def schema_tables() -> set[str]:
    return set(inspect(db.engine).get_table_names())
