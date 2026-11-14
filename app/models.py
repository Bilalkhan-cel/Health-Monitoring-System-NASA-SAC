"""SQLAlchemy models (Section 17 of PROMPT.md).

All timestamps are naive UTC. "Dates" use the UTC calendar date as the mission clock.
``Measurement.source`` and ``SleepLog.source`` are internal data-handling metadata:
they are never serialised to the browser.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .extensions import db

SOURCES = ("sensor", "derived", "manual", "simulated", "cv", "nlp", "voice")
CONTEXTS = ("resting", "active", "unspecified", "fasting", "post_meal", "random")
METRICS = ("heart_rate", "blood_pressure", "glucose", "temperature_c", "spo2", "respiration",
           "sleep_hours", "wellbeing", "loading_index", "hydration_ml")
TASK_CODES = ("cardio", "exercise", "mental", "sleep_log", "hydration")


def utcnow() -> datetime:
    """Current time as a naive UTC datetime (what every column stores)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utctoday() -> date:
    """Today's date on the mission clock (UTC)."""
    return utcnow().date()


class Mission(db.Model):
    """The single mission. Environment and sensor mode live here only."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    start_date = db.Column(db.Date, nullable=False)
    environment = db.Column(db.String(40), nullable=False)
    comms_delay_s = db.Column(db.Float)
    sensor_mode = db.Column(db.String(10), nullable=False, default="device")
    day_override = db.Column(db.Integer)  # Demo panel "jump the mission day"; NULL = the calendar day
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Astronaut(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astro_id = db.Column(db.String(32), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(80), nullable=False)
    callsign = db.Column(db.String(40), nullable=False)
    is_surgeon = db.Column(db.Boolean, nullable=False, default=False)
    mission_id = db.Column(db.Integer, db.ForeignKey("mission.id"), nullable=False)
    xp = db.Column(db.Integer, nullable=False, default=0)
    level = db.Column(db.Integer, nullable=False, default=1)
    streak = db.Column(db.Integer, nullable=False, default=0)
    last_active_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    mission = db.relationship("Mission")

    @property
    def first_name(self) -> str:
        """Given name without a title such as 'Cmdr.' or 'Dr.'."""
        parts = [part for part in self.name.split() if not part.endswith(".")]
        return parts[0] if parts else self.callsign

    @property
    def initials(self) -> str:
        parts = [part for part in self.name.split() if not part.endswith(".")]
        return "".join(part[0] for part in parts[:2]).upper() or self.callsign[:2].upper()


class UserSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, unique=True)
    temp_unit = db.Column(db.String(1), nullable=False, default="C")
    glucose_unit = db.Column(db.String(8), nullable=False, default="mg/dL")
    reminder_times_json = db.Column(db.Text, nullable=False, default="{}")
    voice_cues = db.Column(db.Boolean, nullable=False, default=True)
    reduced_motion = db.Column(db.Boolean, nullable=False, default=False)
    store_transcripts = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class HealthProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, unique=True)
    age = db.Column(db.Integer)
    sex = db.Column(db.String(12))
    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    baseline_json = db.Column(db.Text, nullable=False, default="{}")  # computed cache only
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(40), nullable=False, unique=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    label = db.Column(db.String(80))
    fw_version = db.Column(db.String(20))
    temp_site = db.Column(db.String(10), nullable=False, default="axilla")
    temp_offset_c = db.Column(db.Float, nullable=False, default=0.6)
    last_seen_at = db.Column(db.DateTime)
    last_boot_id = db.Column(db.String(16))
    last_seq = db.Column(db.Integer)
    last_ip = db.Column(db.String(45))
    last_rssi = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Measurement(db.Model):
    """One long table that powers every chart."""

    __table_args__ = (db.Index("ix_measurement_lookup", "astronaut_id", "metric", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    metric = db.Column(db.String(24), nullable=False)
    value = db.Column(db.Float, nullable=False)
    value2 = db.Column(db.Float)
    unit = db.Column(db.String(12), nullable=False)
    status = db.Column(db.String(10))  # NULL = not classified (no rest context, or informational)
    threshold_version = db.Column(db.Integer)
    source = db.Column(db.String(10), nullable=False)
    context = db.Column(db.String(12))
    confirmed = db.Column(db.Boolean, nullable=False, default=True)
    session_type = db.Column(db.String(16))
    session_id = db.Column(db.Integer)
    device_pk = db.Column(db.Integer, db.ForeignKey("device.id"))
    quality = db.Column(db.Float)
    n_samples = db.Column(db.Integer)
    window_s = db.Column(db.Integer)
    raw_value = db.Column(db.Float)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class CardioSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime)
    avg_hr = db.Column(db.Float)
    avg_sys = db.Column(db.Float)
    avg_dia = db.Column(db.Float)
    avg_temp = db.Column(db.Float)
    avg_glucose = db.Column(db.Float)
    glucose_context = db.Column(db.String(12))
    avg_spo2 = db.Column(db.Float)
    avg_resp = db.Column(db.Float)
    hrv_rmssd = db.Column(db.Float)  # always NULL: not supported by the hardware
    symptom_flags_json = db.Column(db.Text, nullable=False, default="[]")
    input_modes_json = db.Column(db.Text, nullable=False, default="{}")
    valid_pct_json = db.Column(db.Text, nullable=False, default="{}")
    rest_verified = db.Column(db.Boolean)
    overall_status = db.Column(db.String(10))
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ExerciseSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime)
    environment = db.Column(db.String(40))
    loading_index = db.Column(db.Float)
    overall_status = db.Column(db.String(10))
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sets = db.relationship("ExerciseSet", backref="session", cascade="all, delete-orphan")


class ExerciseSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("exercise_session.id"), nullable=False, index=True)
    exercise_type = db.Column(db.String(12), nullable=False)  # run | pushup | pullup | squat | device_log
    reps = db.Column(db.Integer)
    duration_s = db.Column(db.Float)
    cadence_spm = db.Column(db.Float)
    form_score = db.Column(db.Float)
    effort_1_10 = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class MentalCheckin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    duration_s = db.Column(db.Float)
    mode = db.Column(db.String(8), nullable=False, default="voice")
    status = db.Column(db.String(12), nullable=False, default="recording")
    transcript = db.Column(db.Text)
    mood_category = db.Column(db.String(12))
    confidence = db.Column(db.Float)
    sentiment_json = db.Column(db.Text)
    emotion_json = db.Column(db.Text)
    themes_json = db.Column(db.Text)
    self_mood_1_10 = db.Column(db.Integer)
    self_sleep_1_5 = db.Column(db.Integer)
    wellbeing_score = db.Column(db.Float)
    safety_flag = db.Column(db.Boolean, nullable=False, default=False)
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AudioChunk(db.Model):
    __table_args__ = (db.UniqueConstraint("checkin_id", "seq"),)

    id = db.Column(db.Integer, primary_key=True)
    checkin_id = db.Column(db.Integer, db.ForeignKey("mental_checkin.id"), nullable=False)
    seq = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(12), nullable=False, default="received")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class SleepLog(db.Model):
    __table_args__ = (db.UniqueConstraint("astronaut_id", "date"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    hours = db.Column(db.Float, nullable=False)
    quality_1_5 = db.Column(db.Integer)
    source = db.Column(db.String(10), nullable=False, default="manual")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class IntakeLog(db.Model):
    __table_args__ = (db.UniqueConstraint("astronaut_id", "date"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    water_ml = db.Column(db.Integer, nullable=False, default=0)
    meals_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ReadinessDaily(db.Model):
    __table_args__ = (db.UniqueConstraint("astronaut_id", "date"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    score = db.Column(db.Float)  # NULL = not enough data that day
    breakdown_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DoctorSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_heartbeat_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False, index=True)
    doctor_session_id = db.Column(db.Integer, db.ForeignKey("doctor_session.id"))
    role = db.Column(db.String(12), nullable=False)
    content = db.Column(db.Text, nullable=False)
    engine = db.Column(db.String(16))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Notification(db.Model):
    __table_args__ = (db.Index("ix_notification_feed", "astronaut_id", "is_read", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    type = db.Column(db.String(24), nullable=False)
    severity = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    action_url = db.Column(db.String(200))
    dedupe_key = db.Column(db.String(120), index=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Badge(db.Model):
    __table_args__ = (db.UniqueConstraint("astronaut_id", "code"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    awarded_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DailyTask(db.Model):
    __table_args__ = (db.UniqueConstraint("astronaut_id", "date", "task_code"),)

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    task_code = db.Column(db.String(16), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    done_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    target_astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"))
    meta_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)


class SensorSample(db.Model):
    """Raw 1 Hz wearable frames, purged after RAW_RETENTION_DAYS."""

    __table_args__ = (
        db.UniqueConstraint("device_pk", "boot_id", "seq"),
        db.Index("ix_sensor_sample_lookup", "astronaut_id", "ts"),
    )

    id = db.Column(db.Integer, primary_key=True)
    astronaut_id = db.Column(db.Integer, db.ForeignKey("astronaut.id"), nullable=False)
    device_pk = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False)
    boot_id = db.Column(db.String(16), nullable=False)
    seq = db.Column(db.Integer, nullable=False)
    ts = db.Column(db.DateTime, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    buffered = db.Column(db.Boolean, nullable=False, default=False)
    finger = db.Column(db.Boolean, nullable=False, default=False)
    hr = db.Column(db.Float)
    spo2 = db.Column(db.Float)
    temp_raw_c = db.Column(db.Float)
    temp_c = db.Column(db.Float)
    temp_state = db.Column(db.String(10))
    pi = db.Column(db.Float)
    quality = db.Column(db.Float)
    flags_json = db.Column(db.Text)


class DeviceEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_pk = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False, index=True)
    ts = db.Column(db.DateTime, nullable=False, default=utcnow)
    kind = db.Column(db.String(16), nullable=False)
    detail_json = db.Column(db.Text)
