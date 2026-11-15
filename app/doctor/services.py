"""Text chat, session binding and the OpenHome bridge for Dr. NOVA.

Engine chain for text chat: OpenHome → fallback LLM → offline rules. The safety screen
runs on every incoming message before any engine is called.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta

from config import Config

from ..extensions import db
from ..models import Astronaut, AuditLog, ChatMessage, DoctorSession, IntakeLog, Notification, SleepLog, utcnow
from ..services import doctor_context, gamification, llm_fallback, measurements, nlp_service, openhome_service
from ..services import rules_engine
from ..services.openhome_service import EngineReply

SESSION_MINUTES = 20
HEARTBEAT_FRESH_S = 45
HISTORY_TURNS = 30


def with_context(message: str, context: dict) -> str:
    """The astronaut's question with their current data attached, for the OpenHome agent."""
    data = json.dumps(context, separators=(",", ":"), default=str)
    return ("[AstroVital data for this astronaut. Use it to answer and quote the real numbers. "
            f"Do not read this block aloud.]\n{data}\n\nAstronaut: {message}")


def context_for(astronaut_id: int, config: Config, runtime=None) -> dict:
    live = None
    if runtime is not None:
        live = runtime.live.snapshot(astronaut_id, utcnow(), linked=True)
    return doctor_context.build(astronaut_id, config, live=live)


def history(astronaut_id: int, since: datetime | None = None) -> list[ChatMessage]:
    query = ChatMessage.query.filter_by(astronaut_id=astronaut_id)
    if since is not None:
        query = query.filter(ChatMessage.created_at >= since)
    rows = query.order_by(ChatMessage.id.desc()).limit(HISTORY_TURNS).all()
    return list(reversed(rows))


def _crisis(astronaut_id: int, now: datetime) -> EngineReply:
    db.session.add(Notification(
        astronaut_id=astronaut_id, type="critical", severity="alert", title="Please reach out now",
        message=nlp_service.support_message(), action_url="/doctor",
        dedupe_key=f"safety-chat:{now.date().isoformat()}:{now.hour}", created_at=now))
    db.session.add(AuditLog(actor="system", action="safety_followup", target_astronaut_id=astronaut_id,
                            meta_json=json.dumps({"from": "doctor_chat"})))
    return EngineReply(nlp_service.support_message(), "OFFLINE RULES")


def reply(astronaut: Astronaut, message: str, config: Config, runtime=None, now: datetime | None = None,
          since: datetime | None = None) -> EngineReply:
    """Answer one text message and store both turns."""
    now = now or utcnow()
    db.session.add(ChatMessage(astronaut_id=astronaut.id, role="user", content=message, created_at=now))
    if nlp_service.safety_screen(message):
        answer = _crisis(astronaut.id, now)
    else:
        context = context_for(astronaut.id, config, runtime)
        answer = None
        if openhome_service.mode(config) == "live":
            touch_session(astronaut.id, now)  # the Ability fetches context through the bridge
            db.session.commit()
            # The data rides along with the question, so Dr. NOVA can answer even when the
            # OpenHome Ability is not triggered or cannot reach the tunnel.
            audio = bytearray()
            text = openhome_service.text_call(config, with_context(message, context), audio=audio)
            if text:
                answer = EngineReply(text, "OPENHOME", bytes(audio) or None)
        if answer is None:
            past = [{"role": row.role, "content": row.content} for row in history(astronaut.id, since)]
            text = llm_fallback.chat(config, message, doctor_context.to_prompt_text(context), past)
            if text:
                answer = EngineReply(text, "FALLBACK LLM")
        if answer is None:
            answer = EngineReply(rules_engine.answer(message, context), "OFFLINE RULES")
    db.session.add(ChatMessage(astronaut_id=astronaut.id, role="assistant", content=answer.text, engine=answer.engine,
                               created_at=utcnow()))
    db.session.commit()
    return answer


# ── sessions (fail closed) ───────────────────────────────

def open_session(astronaut_id: int, now: datetime | None = None) -> DoctorSession:
    now = now or utcnow()
    for old in DoctorSession.query.filter_by(astronaut_id=astronaut_id, active=True):
        old.active = False
    session = DoctorSession(astronaut_id=astronaut_id, active=True, started_at=now, last_heartbeat_at=now,
                            expires_at=now + timedelta(minutes=SESSION_MINUTES))
    db.session.add(session)
    db.session.commit()
    return session


def touch_session(astronaut_id: int, now: datetime | None = None) -> DoctorSession:
    now = now or utcnow()
    session = (DoctorSession.query.filter_by(astronaut_id=astronaut_id, active=True)
               .order_by(DoctorSession.id.desc()).first())
    if session is None or session.expires_at < now:
        return open_session(astronaut_id, now)
    session.last_heartbeat_at = now
    return session


def end_session(astronaut_id: int) -> None:
    for session in DoctorSession.query.filter_by(astronaut_id=astronaut_id, active=True):
        session.active = False
    db.session.commit()


def bridge_session(now: datetime | None = None) -> tuple[DoctorSession | None, str | None]:
    """The single live session the OpenHome Ability may read. (session, error)."""
    now = now or utcnow()
    fresh = [s for s in DoctorSession.query.filter_by(active=True).all()
             if (now - s.last_heartbeat_at).total_seconds() <= HEARTBEAT_FRESH_S and s.expires_at >= now]
    if not fresh:
        return None, "no_active_session"
    if len({s.astronaut_id for s in fresh}) > 1:
        return None, "ambiguous_session"
    return fresh[-1], None


def bridge_token_ok(config: Config, supplied: str) -> bool:
    expected = config.openhome_bridge_token
    return bool(expected) and hmac.compare_digest((supplied or "").encode(), expected.encode())


def audit(action: str, astronaut_id: int | None, meta: dict | None = None) -> None:
    db.session.add(AuditLog(actor="openhome-bridge", action=action, target_astronaut_id=astronaut_id,
                            meta_json=json.dumps(meta or {})))
    db.session.commit()


def voice_log(astronaut: Astronaut, metric: str, value: float, now: datetime | None = None) -> str:
    """Voice logging from the Ability: sleep hours, mood 1-10, water in mL."""
    now = now or utcnow()
    if metric == "sleep_hours":
        if not 0 < value <= 16:
            raise ValueError("Sleep must be between 0 and 16 hours.")
        log = SleepLog.query.filter_by(astronaut_id=astronaut.id, date=now.date()).first()
        if log is None:
            log = SleepLog(astronaut_id=astronaut.id, date=now.date(), hours=value)
            db.session.add(log)
        log.hours, log.source = value, "voice"
        measurements.record(astronaut.id, "sleep_hours", value, source="voice", created_at=now, commit=False)
        gamification.complete_task(astronaut, "sleep_log", now)
        message = f"Logged {value:g} hours of sleep."
    elif metric == "mood":
        if not 1 <= value <= 10:
            raise ValueError("Mood must be 1 to 10.")
        score = (value - 1) / 9 * 100
        measurements.record(astronaut.id, "wellbeing", score, source="voice", created_at=now, commit=False)
        message = f"Logged your mood as {value:g} out of 10."
    elif metric == "water_ml":
        if not 10 <= value <= 3000:
            raise ValueError("Water must be 10 to 3000 mL.")
        intake = IntakeLog.query.filter_by(astronaut_id=astronaut.id, date=now.date()).first()
        if intake is None:
            intake = IntakeLog(astronaut_id=astronaut.id, date=now.date(), water_ml=0)
            db.session.add(intake)
        intake.water_ml += int(value)
        from ..services.readiness import load_indicators

        if intake.water_ml >= load_indicators()["hydration_goal_ml"]:
            gamification.complete_task(astronaut, "hydration", now)
        message = f"Logged {int(value)} millilitres of water."
    else:
        raise ValueError("Unknown log type.")
    db.session.commit()
    return message
