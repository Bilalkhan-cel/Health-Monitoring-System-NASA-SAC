"""Notifications feed and daily reminders (Sections 9.6 and 15).

The client polls ``/api/notifications/poll`` every 30 s. Each poll turns any reminder that
is due (its time has passed today and the task is still open) into one notification,
deduplicated per task and day, and returns everything newer than what the client has seen.
"""

from __future__ import annotations

import json
from datetime import datetime, time

from ..extensions import db
from ..models import Astronaut, DailyTask, Notification, UserSettings
from .readiness import load_indicators

DEFAULT_REMINDERS = {"sleep_log": "07:30", "cardio": "08:00", "exercise": "10:00", "hydration": "14:00",
                     "mental": "19:00"}
REMINDER_TEXT = {
    "cardio": ("Time for your heart check", "About 7 minutes. Rest a finger on the wearable or type your numbers.",
               "/cardio"),
    "exercise": ("Time to exercise", "About 20 minutes. Your bones need the load.", "/musculoskeletal"),
    "mental": ("How are you feeling?", "A 3-minute voice check-in.", "/mental"),
    "sleep_log": ("Log last night's sleep", "Takes 10 seconds.", "/dashboard"),
    "hydration": ("Drink some water", "You're not at today's water goal yet.", "/dashboard"),
}
TYPES = ("reminder", "attention", "critical", "saved", "doctor", "badge")
FEED_LIMIT = 100


def settings_for(astronaut_id: int) -> UserSettings:
    """The astronaut's settings row, created with defaults on first use (not committed)."""
    row = UserSettings.query.filter_by(astronaut_id=astronaut_id).first()
    if row is None:
        row = UserSettings(astronaut_id=astronaut_id)
        db.session.add(row)
        db.session.flush()
    return row


def reminder_times(settings: UserSettings) -> dict[str, str]:
    """Saved times merged over the defaults. An empty string switches a reminder off."""
    try:
        saved = json.loads(settings.reminder_times_json or "{}")
    except ValueError:
        saved = {}
    out = dict(DEFAULT_REMINDERS)
    for code, value in saved.items():
        if code in out and (value == "" or parse_time(value) is not None):
            out[code] = value
    return out


def parse_time(text: str) -> time | None:
    try:
        hour, minute = (int(part) for part in str(text).split(":"))
        return time(hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None
    except (TypeError, ValueError):
        return None


def queue_due_reminders(astronaut: Astronaut, now: datetime) -> int:
    """Create a notification for each reminder that is due and still open. Does not commit."""
    settings = settings_for(astronaut.id)
    tasks = load_indicators()["tasks"]
    done = {task.task_code for task in DailyTask.query.filter_by(astronaut_id=astronaut.id, date=now.date(),
                                                                  done=True)}
    created = 0
    for code, at in reminder_times(settings).items():
        moment = parse_time(at) if at else None
        if moment is None or code not in tasks or code in done or now.time() < moment:
            continue
        key = f"reminder:{code}:{now.date().isoformat()}"
        if db.session.query(Notification.id).filter_by(astronaut_id=astronaut.id, dedupe_key=key).first():
            continue
        title, message, url = REMINDER_TEXT[code]
        db.session.add(Notification(astronaut_id=astronaut.id, type="reminder", severity="okay", title=title,
                                    message=message, action_url=url, dedupe_key=key,
                                    created_at=datetime.combine(now.date(), moment)))
        created += 1
    return created


def as_json(row: Notification) -> dict:
    return {"id": row.id, "type": row.type, "severity": row.severity, "title": row.title, "message": row.message,
            "url": row.action_url, "read": row.is_read, "at": row.created_at.isoformat() + "Z"}


def feed(astronaut_id: int, *, unread_only: bool = False, limit: int = FEED_LIMIT) -> list[Notification]:
    query = Notification.query.filter_by(astronaut_id=astronaut_id)
    if unread_only:
        query = query.filter_by(is_read=False)
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()


def unread_count(astronaut_id: int) -> int:
    return Notification.query.filter_by(astronaut_id=astronaut_id, is_read=False).count()


def poll(astronaut: Astronaut, now: datetime, since_id: int) -> dict:
    """New notifications since ``since_id`` (reminders made due first) plus the unread count."""
    queue_due_reminders(astronaut, now)
    db.session.commit()
    rows = (Notification.query.filter(Notification.astronaut_id == astronaut.id, Notification.id > since_id)
            .order_by(Notification.id).limit(20).all())
    latest = db.session.query(db.func.max(Notification.id)).filter_by(astronaut_id=astronaut.id).scalar() or 0
    return {"items": [as_json(row) for row in rows], "unread": unread_count(astronaut.id), "latest_id": latest}


def mark_read(astronaut_id: int, notification_id: int) -> bool:
    row = Notification.query.filter_by(id=notification_id, astronaut_id=astronaut_id).first()
    if row is None:
        return False
    row.is_read = True
    db.session.commit()
    return True


def mark_all_read(astronaut_id: int) -> int:
    count = (Notification.query.filter_by(astronaut_id=astronaut_id, is_read=False)
             .update({"is_read": True}, synchronize_session=False))
    db.session.commit()
    return count
