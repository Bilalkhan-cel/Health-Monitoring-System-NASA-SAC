"""/settings (Section 16): preferences, reminders, the Wearable panel, privacy, About and the Demo panel."""

from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify, render_template, request

from config import ENVIRONMENTS, TEMP_SITES

from ..auth.decorators import login_required
from ..auth.services import current_crew
from ..extensions import db
from ..models import AuditLog, Device, utcnow
from ..services import demo_controls, gamification, notifications, privacy, units
from ..services.live import get_runtime
from ..services.sensors.device_gateway import DEMO_DEVICE_ID
from ..services.mission import mission_day
from ..services.readiness import load_indicators

bp = Blueprint("settings", __name__)

ABOUT_TEXT = ("Heart rate, SpO₂ and temperature come from the connected wearable when it is present. Blood "
              "pressure, glucose, respiration and the ECG-style trace are generated for demonstration because no "
              "sensor for them is attached. This is a prototype, not a medical device.")
FORCE_METRICS = {"blood_pressure": "Blood pressure", "glucose": "Blood sugar", "respiration": "Breathing rate",
                 "heart_rate": "Heart rate", "spo2": "Oxygen", "temperature_c": "Temperature"}
TEMP_SITE_LABELS = {"axilla": "Under the arm (recommended)", "skin": "On the skin"}
CALIBRATION_LIMIT_C = 2.0


def _config():
    return current_app.extensions["astrovital_config"]


def _payload() -> dict:
    return request.get_json(silent=True) or request.form.to_dict()


def _audit(crew, action: str, meta: dict) -> None:
    db.session.add(AuditLog(actor=crew.astro_id, action=action, target_astronaut_id=crew.id,
                            meta_json=json.dumps(meta)))


def _real_devices():
    """Physical wearables only: the in-process demo wearable is never shown as a device."""
    return Device.query.filter(Device.device_id != DEMO_DEVICE_ID)


def _device_for(crew) -> Device | None:
    """The wearable this astronaut wears, else the configured one (for the wearer switch)."""
    mine = _real_devices().filter_by(astronaut_id=crew.id).order_by(Device.last_seen_at.desc()).first()
    if mine is not None:
        return mine
    configured = _real_devices().filter_by(device_id=_config().device_id).first()
    return configured or _real_devices().order_by(Device.last_seen_at.desc()).first()


def wearable_panel(crew) -> dict:
    """Real device state only (10A): nothing here is invented when no wearable exists."""
    device = _device_for(crew)
    if device is None:
        return {"exists": False}
    now = utcnow()
    snapshot = get_runtime().live.snapshot(device.astronaut_id, now, linked=True)
    age = (now - device.last_seen_at).total_seconds() if device.last_seen_at else None
    online = bool(snapshot["device"]["online"])
    return {
        "exists": True, "device_id": device.device_id, "label": device.label or "Wearable",
        "online": online, "last_seen_age_s": round(age) if age is not None else None,
        "fw": device.fw_version or snapshot["device"].get("fw"), "rssi": device.last_rssi,
        "wearing": device.astronaut_id == crew.id, "wearer": device.astronaut_id,
        "temp_site": device.temp_site, "temp_offset_c": round(device.temp_offset_c, 2),
        "temp_state": snapshot["temp"]["state"] if device.astronaut_id == crew.id else "missing",
        "temp_value_c": snapshot["temp"]["value_c"] if device.astronaut_id == crew.id else None,
    }


@bp.get("/settings")
@login_required
def index():
    crew, config = current_crew(), _config()
    row = notifications.settings_for(crew.id)
    db.session.commit()
    tasks = load_indicators()["tasks"]
    reminders = [{"code": code, "label": tasks[code]["label"], "time": at}
                 for code, at in notifications.reminder_times(row).items() if code in tasks]
    mission = crew.mission
    return render_template(
        "settings.html", prefs=row, reminders=reminders, wearable=wearable_panel(crew),
        game=gamification.summary_for(crew), about=ABOUT_TEXT, environments=ENVIRONMENTS, mission=mission,
        day=mission_day(config, mission), day_jumped=mission.day_override is not None,
        sensor_mode=mission.sensor_mode, scenarios=demo_controls.SCENARIOS.values(), force_metrics=FORCE_METRICS,
        wearable_metrics=demo_controls.WEARABLE, temp_sites=TEMP_SITE_LABELS)


@bp.post("/settings")
@login_required
def save():
    """Units, reminder times, voice cues, reduced motion and transcript storage."""
    crew, data = current_crew(), _payload()
    row = notifications.settings_for(crew.id)
    if "temp_unit" in data:
        if data["temp_unit"] not in ("C", "F"):
            return jsonify(ok=False, error="bad_unit", message="Pick °C or °F."), 400
        row.temp_unit = data["temp_unit"]
    if "glucose_unit" in data:
        if data["glucose_unit"] not in ("mg/dL", "mmol/L"):
            return jsonify(ok=False, error="bad_unit", message="Pick mg/dL or mmol/L."), 400
        row.glucose_unit = data["glucose_unit"]
    for key in ("voice_cues", "reduced_motion", "store_transcripts"):
        if key in data:
            value = data[key]
            setattr(row, key, value is True or str(value).lower() in ("1", "true", "on", "yes"))
    if "reminders" in data:
        incoming = data["reminders"]
        if isinstance(incoming, str):
            try:
                incoming = json.loads(incoming)
            except ValueError:
                incoming = None
        if not isinstance(incoming, dict):
            return jsonify(ok=False, error="bad_reminders", message="Reminder times could not be read."), 400
        saved = {}
        for code in notifications.DEFAULT_REMINDERS:
            value = str(incoming.get(code, notifications.DEFAULT_REMINDERS[code]) or "").strip()
            if value and notifications.parse_time(value) is None:
                return jsonify(ok=False, error="bad_time", message="Use a time like 08:30, or leave it empty."), 400
            saved[code] = value
        row.reminder_times_json = json.dumps(saved)
    db.session.commit()
    units.forget()
    return jsonify(ok=True, settings={"temp_unit": row.temp_unit, "glucose_unit": row.glucose_unit,
                                      "voice_cues": row.voice_cues, "reduced_motion": row.reduced_motion,
                                      "store_transcripts": row.store_transcripts})


@bp.post("/settings/environment")
@login_required
def environment():
    """Change the mission environment.

    # SECURITY NOTE: any crew member may change the mission-wide environment. This is a
    # demo convenience; a real system would restrict it to the commander or Mission Control.
    """
    data = _payload()
    choice = (data.get("environment") or "").strip()
    if choice not in ENVIRONMENTS:
        return jsonify(ok=False, error="unknown_environment"), 400
    crew = current_crew()
    mission = crew.mission
    previous = mission.environment
    mission.environment = choice
    mission.comms_delay_s = None  # a scenario override ends when the environment changes by hand
    _audit(crew, "environment_change", {"from": previous, "to": choice})
    db.session.commit()
    return jsonify(ok=True, environment=choice)


@bp.post("/settings/device")
@login_required
def device():
    """Wearer switch, temperature site and calibration (10A.6). The device token is never shown."""
    crew, data = current_crew(), _payload()
    target = _device_for(crew)
    if target is None:
        return jsonify(ok=False, error="no_device", message="No wearable has connected yet."), 404
    runtime = get_runtime()
    changes: dict = {}
    if "wearing" in data:
        wearing = data["wearing"] is True or str(data["wearing"]).lower() in ("1", "true", "on", "yes")
        if wearing and target.astronaut_id != crew.id:
            runtime.live.reset(target.astronaut_id)
            runtime.aggregator.flush(target.id)
            changes["wearer"] = {"from": target.astronaut_id, "to": crew.id}
            target.astronaut_id = crew.id
            demo = Device.query.filter_by(device_id=DEMO_DEVICE_ID).first()
            if demo is not None:  # the demo wearable follows the real one (bootstrap.upsert_demo_device)
                runtime.aggregator.flush(demo.id)
                demo.astronaut_id = crew.id
            runtime.live.reset(crew.id)
        elif not wearing and target.astronaut_id == crew.id:
            return jsonify(ok=False, error="hand_over",
                           message="To hand the wearable over, the other astronaut switches “I'm wearing it” on."), 400
    if target.astronaut_id != crew.id and ("temp_site" in data or "reference_c" in data):
        return jsonify(ok=False, error="not_wearer", message="Only the person wearing it can change this."), 403
    if "temp_site" in data:
        if data["temp_site"] not in TEMP_SITES:
            return jsonify(ok=False, error="bad_site", message="Pick a probe position from the list."), 400
        changes["temp_site"] = {"from": target.temp_site, "to": data["temp_site"]}
        target.temp_site = data["temp_site"]
    if "reference_c" in data:
        try:
            reference = units.to_stored("temperature_c", float(data["reference_c"]))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="bad_reference", message="Type the thermometer reading as a number."), 400
        snapshot = runtime.live.snapshot(crew.id, utcnow(), linked=True)
        if snapshot["temp"]["state"] != "settled" or snapshot["temp"]["value_c"] is None:
            return jsonify(ok=False, error="not_settled",
                           message="Wait until the probe has settled under your arm, then try again."), 409
        raw = snapshot["temp"]["value_c"] - target.temp_offset_c
        offset = round(reference - raw, 2)
        if abs(offset) > CALIBRATION_LIMIT_C:
            return jsonify(ok=False, error="offset_too_large",
                           message="That is more than 2 °C away from the probe. Check the probe and the "
                                   "thermometer, then try again."), 400
        changes["temp_offset_c"] = {"from": target.temp_offset_c, "to": offset}
        target.temp_offset_c = offset
    if changes:
        _audit(crew, "device_settings", {"device": target.device_id, **changes})
    db.session.commit()
    return jsonify(ok=True, wearable=wearable_panel(crew))


@bp.post("/settings/privacy/delete-mental")
@login_required
def delete_mental():
    crew, data = current_crew(), _payload()
    if str(data.get("confirm", "")).strip().upper() != "DELETE":
        return jsonify(ok=False, error="confirm", message="Type DELETE to confirm."), 400
    report = privacy.delete_mental_data(crew.id, crew.astro_id)
    return jsonify(ok=True, deleted=report.as_json())


@bp.post("/settings/sensor-mode")
@login_required
def sensor_mode():
    """Switch between the real wearable and demo data. The ONLY way the mode ever changes.

    Available only with DEMO_MODE=true, always by a person, always audited.
    """
    config = _config()
    if not config.demo_mode:
        return jsonify(ok=False, error="demo_mode_off"), 404
    data = _payload()
    mode = (data.get("mode") or "").strip()
    if mode not in ("device", "demo"):
        return jsonify(ok=False, error="unknown_mode"), 400
    crew = current_crew()
    mission = crew.mission
    previous = mission.sensor_mode
    if previous != mode:
        mission.sensor_mode = mode
        _audit(crew, "sensor_mode_change", {"from": previous, "to": mode})
        runtime = get_runtime()
        for item in Device.query.all():
            runtime.live.reset(item.astronaut_id)
            runtime.aggregator.flush(item.id)
        db.session.commit()
    return jsonify(ok=True, mode=mode)


@bp.post("/settings/demo/<action>")
@login_required
def demo(action: str):
    """Demo panel: ``force``, ``day`` or a Judge Mode scenario code. DEMO_MODE only, always audited."""
    if not _config().demo_mode:
        return jsonify(ok=False, error="demo_mode_off"), 404
    crew, data, now = current_crew(), _payload(), utcnow()
    try:
        if action == "force":
            status = demo_controls.force_status(crew, str(data.get("metric", "")), str(data.get("status", "")), now)
            return jsonify(ok=True, status=status)
        if action == "day":
            raw = data.get("day")
            day = None if raw in (None, "", "reset") else int(raw)
            demo_controls.jump_day(crew, day)
            return jsonify(ok=True, day=mission_day(_config(), crew.mission))
        if action in demo_controls.SCENARIOS:
            scenario = demo_controls.run_scenario(crew, action, now)
            return jsonify(ok=True, scenario=scenario.code, title=scenario.title)
    except (ValueError, TypeError) as problem:
        db.session.rollback()
        message = str(problem) if isinstance(problem, demo_controls.DemoError) else "That value could not be used."
        return jsonify(ok=False, error="demo_refused", message=message), 400
    return jsonify(ok=False, error="unknown_action"), 404
