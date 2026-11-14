"""/login and /logout."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, redirect, render_template, request, url_for

from ..extensions import limiter
from .services import current_crew, find_crew, home_endpoint, log_in, log_out, normalise_id

bp = Blueprint("auth", __name__)

NOT_ON_CREW = "That ID isn't on this mission's crew list."


def _submitted_id() -> str:
    return "id:" + normalise_id(request.form.get("astro_id"))[:32]


def _safe_next(target: str | None) -> str | None:
    """Only follow relative, same-site redirects."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target.rstrip("?") or None


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute", methods=["POST"])
@limiter.limit("5/minute", methods=["POST"], key_func=_submitted_id)
def login():
    crew = current_crew()
    if request.method == "GET":
        if crew is not None:
            return redirect(url_for(home_endpoint(crew)))
        return render_template("login.html", error=None, astro_id="", next=_safe_next(request.args.get("next")))

    astro_id = normalise_id(request.form.get("astro_id"))
    target = _safe_next(request.form.get("next"))
    crew = find_crew(astro_id)
    if crew is None:
        # 200 with the message on the page: a 401 would only add a console error in the browser.
        return render_template("login.html", error=NOT_ON_CREW, astro_id=astro_id, next=target), 200
    log_in(crew)
    if crew.is_surgeon or target is None:
        return redirect(url_for(home_endpoint(crew)))
    return redirect(target)


@bp.post("/logout")
def logout():
    log_out()
    return redirect(url_for("landing.index"))
