"""/notifications and /api/notifications/poll (Section 15)."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import utcnow
from ..services import notifications

bp = Blueprint("notifications", __name__)

TYPE_ICONS = {"reminder": "timer", "attention": "triangle-alert", "critical": "octagon-alert",
              "saved": "circle-check", "doctor": "stethoscope", "badge": "award"}
SEVERITY_LABELS = {"good": "Good", "okay": "Okay", "watch": "Needs attention", "alert": "Get help now"}


@bp.get("/notifications")
@login_required
def index():
    crew = current_crew()
    notifications.queue_due_reminders(crew, utcnow())
    db.session.commit()
    show = request.args.get("show", "all")
    rows = notifications.feed(crew.id, unread_only=show == "unread")
    return render_template("notifications.html", items=[notifications.as_json(row) for row in rows], show=show,
                           unread=notifications.unread_count(crew.id), icons=TYPE_ICONS,
                           severity_labels=SEVERITY_LABELS)


@bp.get("/api/notifications/poll")
@login_required
def poll():
    try:
        since = max(0, int(request.args.get("since", "0")))
    except ValueError:
        since = 0
    return jsonify(notifications.poll(current_crew(), utcnow(), since))


@bp.post("/notifications/<int:notification_id>/read")
@login_required
def read(notification_id: int):
    crew = current_crew()
    if not notifications.mark_read(crew.id, notification_id):
        return jsonify(ok=False, error="not_found"), 404
    return jsonify(ok=True, unread=notifications.unread_count(crew.id))


@bp.post("/notifications/read-all")
@login_required
def read_all():
    crew = current_crew()
    count = notifications.mark_all_read(crew.id)
    return jsonify(ok=True, marked=count, unread=0)
