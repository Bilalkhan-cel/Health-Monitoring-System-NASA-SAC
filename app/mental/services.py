"""Daily voice (or text) check-in: chunks → background Whisper → safety screen → analysis.

Privacy by default: audio files are deleted as soon as they are transcribed; with
``STORE_TRANSCRIPTS=false`` the transcript is discarded once the analysis is done and
only scores and the summary are kept.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask

from config import Config

from ..extensions import db
from ..models import AudioChunk, Astronaut, MentalCheckin, Measurement, Notification, UserSettings, utcnow
from ..services import gamification, measurements, nlp_service, whisper_service
from ..services.stream_hub import queue_event

log = logging.getLogger(__name__)

MAX_CHUNK_BYTES = 2 * 1024 * 1024
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_transcripts: dict[int, dict[int, str]] = {}   # checkin_id -> seq -> text (memory only until finish)
_transcripts_lock = threading.Lock()


def executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="astrovital-whisper")
        return _executor


def stores_transcripts(astronaut_id: int, config: Config) -> bool:
    settings = UserSettings.query.filter_by(astronaut_id=astronaut_id).first()
    return settings.store_transcripts if settings else config.store_transcripts


def start(astronaut: Astronaut, mode: str, now: datetime | None = None) -> MentalCheckin:
    checkin = MentalCheckin(astronaut_id=astronaut.id, started_at=now or utcnow(), mode=mode, status="recording")
    db.session.add(checkin)
    db.session.commit()
    return checkin


def owned(checkin_id: int, astronaut_id: int) -> MentalCheckin | None:
    checkin = db.session.get(MentalCheckin, checkin_id)
    return checkin if checkin is not None and checkin.astronaut_id == astronaut_id else None


def text_so_far(checkin_id: int) -> str:
    with _transcripts_lock:
        parts = _transcripts.get(checkin_id, {})
        return " ".join(parts[key] for key in sorted(parts))


def _safety_event(app: Flask, checkin: MentalCheckin, now: datetime) -> None:
    """Flag the check-in, raise a critical notification, and record wellbeing as Get help now."""
    if checkin.safety_flag:
        return
    checkin.safety_flag = True
    checkin.status = "safety_flag"
    db.session.add(Notification(
        astronaut_id=checkin.astronaut_id, type="critical", severity="alert", title="Please reach out now",
        message=nlp_service.support_message(), action_url="/doctor", dedupe_key=f"safety:{checkin.id}",
        created_at=now))
    measurements.record(checkin.astronaut_id, "wellbeing", 0, source="nlp", created_at=now, symptom=True,
                        session_type="mental", session_id=checkin.id, commit=False, notify=False)
    queue_event(db.session, checkin.astronaut_id, "alert", {"kind": "safety"})


def save_chunk(app: Flask, checkin: MentalCheckin, seq: int, data: bytes, config: Config) -> tuple[bool, str]:
    """Store one WAV chunk and transcribe it in the background. Idempotent on (checkin, seq)."""
    if AudioChunk.query.filter_by(checkin_id=checkin.id, seq=seq).first():
        return False, "duplicate"
    if not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
        raise ValueError("Chunks must be WAV audio.")
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    path = config.uploads_dir / f"checkin-{checkin.id}-{seq:04d}.wav"
    path.write_bytes(data)
    chunk = AudioChunk(checkin_id=checkin.id, seq=seq, status="received")
    db.session.add(chunk)
    db.session.commit()
    executor().submit(_transcribe_job, app, chunk.id, checkin.id, seq, path)
    return True, "received"


def _transcribe_job(app: Flask, chunk_id: int, checkin_id: int, seq: int, path: Path) -> None:
    config = app.extensions["astrovital_config"]
    with app.app_context():
        chunk = db.session.get(AudioChunk, chunk_id)
        chunk.status = "transcribing"
        db.session.commit()
        try:
            text = whisper_service.transcribe(path, config.whisper_model_path / config.whisper_model_size,
                                              config.whisper_compute_type)
            chunk.status = "done" if text is not None else "failed"
            if text:
                with _transcripts_lock:
                    _transcripts.setdefault(checkin_id, {})[seq] = text
                if nlp_service.safety_screen(text):
                    _safety_event(app, db.session.get(MentalCheckin, checkin_id), utcnow())
        except Exception:  # noqa: BLE001 (a failed chunk is reported, never crashes the worker)
            log.exception("Transcription failed for check-in %s chunk %s", checkin_id, seq)
            chunk.status = "failed"
        finally:
            path.unlink(missing_ok=True)  # audio is deleted once it has been read
            db.session.commit()
            db.session.remove()


def status(checkin: MentalCheckin) -> dict:
    chunks = AudioChunk.query.filter_by(checkin_id=checkin.id).all()
    pending = sum(chunk.status in ("received", "transcribing") for chunk in chunks)
    return {"id": checkin.id, "status": checkin.status, "chunks": len(chunks), "pending": pending,
            "failed": sum(chunk.status == "failed" for chunk in chunks), "preview": text_so_far(checkin.id)[-400:],
            "safety": checkin.safety_flag}


def finish(app: Flask, checkin: MentalCheckin, *, text: str | None, self_mood: int | None, self_sleep: int | None,
           duration_s: float | None, config: Config, now: datetime | None = None) -> dict:
    """Analyse the transcript (or typed text) and save the result."""
    now = now or utcnow()
    full = (text or "").strip() if text is not None else text_so_far(checkin.id)
    checkin.duration_s = duration_s
    checkin.self_mood_1_10, checkin.self_sleep_1_5 = self_mood, self_sleep
    astronaut = db.session.get(Astronaut, checkin.astronaut_id)
    analysis = nlp_service.analyse(full, config.nlp_sentiment_path, config.nlp_emotion_path)
    if analysis.safety or checkin.safety_flag:
        _safety_event(app, checkin, now)
        checkin.summary = "Safety follow-up requested."
        checkin.transcript = None
        gamification.complete_task(astronaut, "mental", now)
        db.session.commit()
        _forget(checkin.id)
        return {"safety": True, "message": nlp_service.support_message(), "checkin_id": checkin.id}
    min_seconds = config.mental_session_min_seconds
    if checkin.mode == "voice" and (duration_s or 0) < min_seconds and self_mood is None:
        checkin.status = "failed"
        db.session.commit()
        _forget(checkin.id)
        return {"safety": False, "too_short": True, "checkin_id": checkin.id,
                "message": f"Talk for at least {min_seconds} seconds, or add a mood rating, for a result."}
    score = nlp_service.wellbeing_score(analysis, self_mood)
    category, internal = nlp_service.mood_category(score)
    checkin.wellbeing_score = score
    checkin.mood_category = category
    checkin.confidence = analysis.confidence
    checkin.sentiment_json = json.dumps({"pos": analysis.pos_ratio, "neg": analysis.neg_ratio,
                                         "timeline": analysis.segments})
    checkin.emotion_json = json.dumps(analysis.emotions)
    checkin.themes_json = json.dumps(analysis.themes)
    checkin.summary = nlp_service.summary_text(analysis, score, category)
    checkin.transcript = full if stores_transcripts(checkin.astronaut_id, config) and full else None
    checkin.status = "done"
    result = measurements.record(checkin.astronaut_id, "wellbeing", score, source="nlp", created_at=now,
                                 session_type="mental", session_id=checkin.id, commit=False)
    outcome = gamification.complete_task(astronaut, "mental", now)
    _persistent_low(checkin.astronaut_id, now)
    db.session.commit()
    _forget(checkin.id)
    return {
        "safety": False, "checkin_id": checkin.id, "score": score, "category": category,
        "status": result.status, "internal": internal, "confidence": analysis.confidence,
        "emotions": analysis.emotions, "timeline": analysis.segments, "themes": analysis.themes,
        "summary": checkin.summary, "suggestions": nlp_service.suggestions(analysis, category),
        "transcript": checkin.transcript, "engine": analysis.engine, "xp": outcome.xp_gained,
        "trend": trend(checkin.astronaut_id, now),
    }


def _forget(checkin_id: int) -> None:
    with _transcripts_lock:
        _transcripts.pop(checkin_id, None)


def _persistent_low(astronaut_id: int, now: datetime) -> None:
    """Needs attention for 3+ days → a supportive notification suggesting Dr. NOVA."""
    since = now - timedelta(days=3)
    rows = (Measurement.query.filter(Measurement.astronaut_id == astronaut_id, Measurement.metric == "wellbeing",
                                     Measurement.created_at >= since).all())
    days = {row.created_at.date() for row in rows if row.status in ("CAUTION", "CRITICAL")}
    if len(days) >= 3:
        key = f"mood_low:{now.date().isoformat()}"
        if not Notification.query.filter_by(astronaut_id=astronaut_id, dedupe_key=key).first():
            db.session.add(Notification(
                astronaut_id=astronaut_id, type="attention", severity="watch", title="A few hard days in a row",
                message="Your check-ins have been low for three days. That is common on long missions. Talking "
                        "to Dr. NOVA or a crewmate can help.", action_url="/doctor", dedupe_key=key,
                created_at=now))


def trend(astronaut_id: int, now: datetime) -> list[dict]:
    since = now - timedelta(days=14)
    rows = (Measurement.query.filter(Measurement.astronaut_id == astronaut_id, Measurement.metric == "wellbeing",
                                     Measurement.created_at >= since).order_by(Measurement.created_at).all())
    key_of = {"NOMINAL": "good", "STABLE": "okay", "CAUTION": "watch", "CRITICAL": "alert"}
    return [{"t": row.created_at.isoformat(timespec="minutes") + "Z", "v": row.value, "status": key_of.get(row.status)}
            for row in rows]


def delete_transcript(checkin: MentalCheckin) -> None:
    checkin.transcript = None
    db.session.commit()
    _forget(checkin.id)
