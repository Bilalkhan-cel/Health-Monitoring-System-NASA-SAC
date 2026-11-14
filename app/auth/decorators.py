"""Route guards. Every app route uses ``login_required``; Mission Control uses ``surgeon_required``."""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import current_app, jsonify, redirect, request, url_for

from .services import current_crew


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.is_json or \
        request.accept_mimetypes.best == "application/json"


def _deny(status: int):
    if _wants_json():
        return jsonify(ok=False, error="login_required" if status == 401 else "forbidden"), status
    if status == 401:
        return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
    return redirect(url_for("auth.login"))


def login_required(view: Callable) -> Callable:
    """Astronaut pages: anonymous users go to /login, surgeons go to Mission Control."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        crew = current_crew()
        if crew is None:
            return _deny(401)
        if crew.is_surgeon:
            if _wants_json() or "mission_control.index" not in current_app.view_functions:
                return jsonify(ok=False, error="astronaut_only"), 403
            return redirect(url_for("mission_control.index"))
        return view(*args, **kwargs)

    return wrapper


def any_crew_required(view: Callable) -> Callable:
    """Pages open to astronauts and flight surgeons alike (logout, settings basics)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_crew() is None:
            return _deny(401)
        return view(*args, **kwargs)

    return wrapper


def surgeon_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        crew = current_crew()
        if crew is None:
            return _deny(401)
        if not crew.is_surgeon:
            if _wants_json():
                return jsonify(ok=False, error="forbidden"), 403
            return redirect(url_for("dashboard.index"))
        return view(*args, **kwargs)

    return wrapper
