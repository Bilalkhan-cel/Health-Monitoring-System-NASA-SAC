"""Settings → "Delete my mental-health data" (Section 16).

Removes every voice check-in (and its chunk records), the Dr. NOVA conversation history,
the derived wellbeing readings and the wellbeing notifications, then recomputes readiness
for each affected day so no score still leans on the deleted data.

Dr. NOVA chats are deleted as a whole: a conversation about sleep or stress is
mental-health content, and splitting it reliably is not possible (DECISIONS D59).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time

from ..extensions import db
from ..models import AudioChunk, AuditLog, ChatMessage, Measurement, MentalCheckin, Notification, utcnow
from .summary import store_readiness

MENTAL_NOTIFICATION_KEYS = ("wellbeing", "safety", "safety-chat", "mood_low")


@dataclass(frozen=True)
class DeletionReport:
    checkins: int
    chat_messages: int
    wellbeing_readings: int
    days_rescored: int

    def as_json(self) -> dict:
        return {"checkins": self.checkins, "chat_messages": self.chat_messages,
                "wellbeing_readings": self.wellbeing_readings, "days_rescored": self.days_rescored}


def delete_mental_data(astronaut_id: int, actor: str, now: datetime | None = None) -> DeletionReport:
    now = now or utcnow()
    days: set[date] = set()
    checkin_ids = [row.id for row in db.session.query(MentalCheckin.id).filter_by(astronaut_id=astronaut_id)]
    for (started,) in db.session.query(MentalCheckin.started_at).filter_by(astronaut_id=astronaut_id):
        days.add(started.date())
    if checkin_ids:
        AudioChunk.query.filter(AudioChunk.checkin_id.in_(checkin_ids)).delete(synchronize_session=False)
    checkins = MentalCheckin.query.filter_by(astronaut_id=astronaut_id).delete(synchronize_session=False)
    chats = ChatMessage.query.filter_by(astronaut_id=astronaut_id).delete(synchronize_session=False)
    for (created,) in db.session.query(Measurement.created_at).filter_by(astronaut_id=astronaut_id,
                                                                          metric="wellbeing"):
        days.add(created.date())
    readings = (Measurement.query.filter_by(astronaut_id=astronaut_id, metric="wellbeing")
                .delete(synchronize_session=False))
    keys = db.or_(*(Notification.dedupe_key.like(f"{prefix}:%") for prefix in MENTAL_NOTIFICATION_KEYS))
    Notification.query.filter(Notification.astronaut_id == astronaut_id, keys).delete(synchronize_session=False)
    db.session.flush()
    for day in sorted(days):
        end_of_day = datetime.combine(day, time.max)
        store_readiness(astronaut_id, day, as_of=min(now, end_of_day))
    store_readiness(astronaut_id, now.date(), as_of=now)
    report = DeletionReport(checkins, chats, readings, len(days | {now.date()}))
    db.session.add(AuditLog(actor=actor, action="delete_mental_data", target_astronaut_id=astronaut_id,
                            meta_json=json.dumps(report.as_json())))
    db.session.commit()
    return report
