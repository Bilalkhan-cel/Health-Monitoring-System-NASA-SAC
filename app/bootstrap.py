"""Start-up work that ``run.py`` performs before serving requests.

Phase 0 covers the database file and the uploads sweep. Later phases add the
crew and wearable upserts, the first-run seed, the raw-frame purge and the
generated-data catch-up here, so start-up stays in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import get_config
from .extensions import db

log = logging.getLogger(__name__)

KEEP_FILES = {".gitkeep"}


@dataclass(frozen=True)
class BootReport:
    """What start-up found, for the boot checklist."""

    db_ready: bool
    crew_loaded: int | None = None
    wearable_last_seen_s: float | None = None
    sensor_mode: str | None = None
    uploads_swept: int = 0


def ensure_database(app: Flask) -> bool:
    """Create the database (and any missing tables) and prove it answers."""
    try:
        with app.app_context():
            db.create_all()
            db.session.execute(text("SELECT 1"))
            db.session.commit()
        return True
    except SQLAlchemyError:
        log.exception("Database could not be opened")
        return False


def sweep_uploads(app: Flask) -> int:
    """Delete temporary audio left behind by an earlier run."""
    uploads = get_config(app).uploads_dir
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


def run(app: Flask) -> BootReport:
    """Run every start-up step and report the outcome."""
    db_ready = ensure_database(app)
    swept = sweep_uploads(app)
    return BootReport(db_ready=db_ready, uploads_swept=swept)
