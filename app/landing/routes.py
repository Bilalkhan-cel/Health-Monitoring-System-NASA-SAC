"""Landing page and ``/healthz``."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory

from config import VERSION

bp = Blueprint("landing", __name__)


@bp.get("/")
def index():
    """Cinematic landing: Earth and the ISS in WebGL, with a still poster as fallback."""
    return render_template("landing.html")


@bp.get("/healthz")
def healthz():
    """Liveness probe. Public, and deliberately free of any health or crew data."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return jsonify(ok=True, server="astrovital", version=VERSION, server_time=now.isoformat().replace("+00:00", "Z"))


@bp.get("/favicon.ico")
def favicon():
    """Browsers ask for /favicon.ico regardless of the <link>; answer with the SVG mark."""
    return send_from_directory(Path(current_app.static_folder) / "img", "favicon.svg", mimetype="image/svg+xml",
                               max_age=86400)
