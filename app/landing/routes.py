"""Landing page and ``/healthz``."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template

from config import VERSION

bp = Blueprint("landing", __name__)


@bp.get("/")
def index():
    """Landing page. The cinematic 3D version replaces this in a later phase."""
    return render_template("landing.html")


@bp.get("/healthz")
def healthz():
    """Liveness probe. Public, and deliberately free of any health or crew data."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return jsonify(ok=True, server="astrovital", version=VERSION, server_time=now.isoformat().replace("+00:00", "Z"))
