"""Phase 10: history, exports, notifications + reminders, settings, privacy delete, Demo panel, Mission Control."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import timedelta

import pytest

from app.extensions import db
from app.models import (AuditLog, ChatMessage, DailyTask, Device, Measurement, MentalCheckin, Mission, Notification,
                        ReadinessDaily, UserSettings, utcnow)
from conftest import build_app, crew_id, login, make_values

FORBIDDEN_LABELS = re.compile(r"\b(SENSOR|DERIVED|SIMULATED|SIM)\b|\"source\"")


@pytest.fixture
def seeded(tmp_path):
    return build_app(make_values(tmp_path / "instance"), seed=True)


@pytest.fixture
def crew_client(seeded):
    client = seeded.test_client()
    login(client)
    return client


# ── history ───────────────────────────────────────────────

def test_history_page_shows_timeline_heatmap_and_exports(crew_client):
    page = crew_client.get("/history").get_data(as_text=True)
    assert "Readiness by day" in page and "Timeline" in page
    assert page.count('class="heat__day') == 30
    assert "/history/report.pdf" in page and "/history/export.csv" in page
    assert not FORBIDDEN_LABELS.search(page)


def test_history_filters_narrow_the_timeline(crew_client):
    everything = crew_client.get("/history").get_data(as_text=True)
    heart_only = crew_client.get("/history?system=cardio&kind=all").get_data(as_text=True)
    assert "Voice check-in" in everything and "Voice check-in" not in heart_only
    assert "Heart check" in heart_only
    odd = crew_client.get("/history?system=nope&from=garbage&to=2026-13-40")
    assert odd.status_code == 200


def test_day_detail_lists_readings_without_source(crew_client):
    page = crew_client.get("/history").get_data(as_text=True)
    day = re.findall(r'data-day="([0-9-]+)"', page)[-2]
    detail = crew_client.get(f"/history/day/{day}").get_json()
    assert detail["date"] == day and detail["readings"]
    assert not FORBIDDEN_LABELS.search(json.dumps(detail))
    assert crew_client.get("/history/day/not-a-date").status_code == 404


def test_csv_export_has_no_source_column_and_respects_filters(crew_client):
    response = crew_client.get("/history/export.csv")
    assert response.mimetype == "text/csv" and "attachment" in response.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0] == ["date", "time_utc", "metric", "value", "value2", "unit", "status"]
    assert len(rows) > 50
    assert not FORBIDDEN_LABELS.search(response.get_data(as_text=True))
    sleep = list(csv.reader(io.StringIO(crew_client.get("/history/export.csv?system=sleep").get_data(as_text=True))))
    assert {row[2] for row in sleep[1:]} == {"Sleep"}


def test_downlink_report_is_a_pdf_without_transcripts(seeded, crew_client):
    with seeded.app_context():
        checkin = MentalCheckin.query.filter_by(astronaut_id=crew_id(seeded, "AST-1001")).first()
        checkin.transcript = "secret words about my family"
        db.session.commit()
    response = crew_client.get("/history/report.pdf")
    assert response.status_code == 200 and response.data[:5] == b"%PDF-"
    assert b"secret words" not in response.data
    assert "downlink-report-AST-1001" in response.headers["Content-Disposition"]


def test_history_is_scoped_to_the_logged_in_astronaut(seeded):
    with seeded.app_context():
        other = crew_id(seeded, "AST-1002")
        Measurement.query.filter_by(astronaut_id=other).update({"value": 199}, synchronize_session=False)
        db.session.commit()
    client = seeded.test_client()
    login(client, "AST-1001")
    assert ",199," not in client.get("/history/export.csv").get_data(as_text=True)


# ── notifications ─────────────────────────────────────────

def test_poll_turns_due_reminders_into_one_notification_each(seeded, crew_client):
    crew_client.post("/settings", json={"reminders": {"cardio": "00:00", "exercise": "", "mental": "",
                                                      "sleep_log": "", "hydration": ""}})
    first = crew_client.get("/api/notifications/poll?since=0").get_json()
    reminders = [item for item in first["items"] if item["type"] == "reminder"]
    with seeded.app_context():
        done = {row.task_code for row in DailyTask.query.filter_by(astronaut_id=crew_id(seeded, "AST-1001"),
                                                                     date=utcnow().date(), done=True)}
    assert len(reminders) == (0 if "cardio" in done else 1)
    again = crew_client.get(f"/api/notifications/poll?since={first['latest_id']}").get_json()
    assert not [item for item in again["items"] if item["type"] == "reminder"], "deduplicated per task and day"
    assert again["unread"] == first["unread"]


def test_mark_read_and_read_all(seeded, crew_client):
    with seeded.app_context():
        me = crew_id(seeded, "AST-1001")
        for index in range(3):
            db.session.add(Notification(astronaut_id=me, type="saved", severity="good", title=f"Saved {index}",
                                        message="ok"))
        db.session.commit()
        first = Notification.query.filter_by(astronaut_id=me, is_read=False).first().id
    assert crew_client.post(f"/notifications/{first}/read").get_json()["ok"] is True
    page = crew_client.get("/notifications").get_data(as_text=True)
    assert "Mark all read" in page
    assert crew_client.post("/notifications/read-all").get_json()["unread"] == 0
    assert crew_client.get("/api/notifications/poll").get_json()["unread"] == 0


def test_cannot_read_another_astronauts_notification(seeded, crew_client):
    with seeded.app_context():
        other = crew_id(seeded, "AST-1002")
        row = Notification(astronaut_id=other, type="saved", severity="good", title="theirs", message="x")
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    assert crew_client.post(f"/notifications/{row_id}/read").status_code == 404


# ── settings ──────────────────────────────────────────────

def test_settings_page_has_about_wearable_privacy_badges_and_demo(crew_client):
    page = crew_client.get("/settings").get_data(as_text=True)
    for text in ("About this prototype", "Blood pressure, glucose, respiration and the ECG-style trace are generated",
                 "Delete my mental-health data", "Badges", "Demo panel", "Judge Mode scenarios",
                 "AV-ESP32-01"):
        assert text in page, text
    assert "test-device-token" not in page and "AV-DEMO-01" not in page, "no token, no virtual device"
    assert not FORBIDDEN_LABELS.search(page)


def test_units_change_the_display_but_not_the_stored_value(seeded, crew_client):
    before = {item["key"]: item for item in crew_client.get("/api/summary").get_json()["metrics"]}
    assert crew_client.post("/settings", json={"temp_unit": "F", "glucose_unit": "mmol/L"}).get_json()["ok"]
    after = {item["key"]: item for item in crew_client.get("/api/summary").get_json()["metrics"]}
    assert after["temperature_c"]["unit"] == "°F" and after["glucose"]["unit"] == "mmol/L"
    celsius = float(before["temperature_c"]["value"])
    assert abs(float(after["temperature_c"]["value"]) - (celsius * 9 / 5 + 32)) < 0.11
    assert float(after["glucose"]["value"]) < 15
    with seeded.app_context():
        latest = (Measurement.query.filter_by(astronaut_id=crew_id(seeded, "AST-1001"), metric="temperature_c")
                  .order_by(Measurement.created_at.desc()).first())
        assert 35 < latest.value < 39, "stored in °C"
    assert crew_client.post("/settings", json={"temp_unit": "K"}).status_code == 400


def test_reminder_times_are_validated(crew_client):
    bad = crew_client.post("/settings", json={"reminders": {"cardio": "25:99"}})
    assert bad.status_code == 400
    assert crew_client.post("/settings", json={"reminders": {"cardio": "09:15"}}).status_code == 200
    assert 'value="09:15"' in crew_client.get("/settings").get_data(as_text=True)


def test_reduce_motion_setting_marks_the_page(crew_client):
    crew_client.post("/settings", json={"reduced_motion": True})
    assert '<html lang="en" class="reduce-motion">' in crew_client.get("/dashboard").get_data(as_text=True)


def test_delete_mental_data_cascades_and_rescores(seeded, crew_client):
    me = crew_id(seeded, "AST-1001")
    with seeded.app_context():
        db.session.add(ChatMessage(astronaut_id=me, role="user", content="I feel low"))
        db.session.commit()
        assert MentalCheckin.query.filter_by(astronaut_id=me).count() > 0
    refused = crew_client.post("/settings/privacy/delete-mental", json={"confirm": "yes"})
    assert refused.status_code == 400
    result = crew_client.post("/settings/privacy/delete-mental", json={"confirm": "DELETE"}).get_json()
    assert result["ok"] and result["deleted"]["checkins"] > 0 and result["deleted"]["chat_messages"] >= 1
    with seeded.app_context():
        assert MentalCheckin.query.filter_by(astronaut_id=me).count() == 0
        assert ChatMessage.query.filter_by(astronaut_id=me).count() == 0
        assert Measurement.query.filter_by(astronaut_id=me, metric="wellbeing").count() == 0
        for row in ReadinessDaily.query.filter_by(astronaut_id=me):
            assert "wellbeing" not in json.dumps(json.loads(row.breakdown_json).get("metrics", {}))
        assert AuditLog.query.filter_by(action="delete_mental_data", target_astronaut_id=me).count() == 1
        other = crew_id(seeded, "AST-1002")
        assert MentalCheckin.query.filter_by(astronaut_id=other).count() > 0, "only my data"


def test_wearable_panel_shows_real_device_state_and_never_the_token(seeded, crew_client):
    with seeded.app_context():
        device = Device.query.filter_by(device_id="AV-ESP32-01").one()
        device.astronaut_id, device.fw_version = crew_id(seeded, "AST-1002"), "1.0.0"
        device.last_seen_at, device.last_rssi = utcnow() - timedelta(minutes=10), -58
        db.session.commit()
    page = crew_client.get("/settings").get_data(as_text=True)
    assert "AV-ESP32-01" in page and "Offline" in page and "-58 dBm" in page and "1.0.0" in page
    assert "Another crew member is wearing it now" in page
    assert crew_client.post("/settings/device", json={"temp_site": "skin"}).status_code == 403
    taken = crew_client.post("/settings/device", json={"wearing": True}).get_json()
    assert taken["wearable"]["wearing"] is True
    not_settled = crew_client.post("/settings/device", json={"reference_c": 36.9})
    assert not_settled.status_code == 409
    assert crew_client.post("/settings/device", json={"temp_site": "skin"}).get_json()["wearable"]["temp_site"] == "skin"
    with seeded.app_context():
        assert AuditLog.query.filter_by(action="device_settings").count() == 2
        me = crew_id(seeded, "AST-1001")
        assert Device.query.filter_by(device_id="AV-DEMO-01").one().astronaut_id == me, "demo wearable follows"


def test_wearable_calibration_stores_the_offset_when_settled(seeded, crew_client, monkeypatch):
    with seeded.app_context():
        device = Device.query.filter_by(device_id="AV-ESP32-01").one()
        device.astronaut_id, device.last_seen_at, device.temp_offset_c = crew_id(seeded, "AST-1001"), utcnow(), 0.6
        db.session.commit()
    from app.services.sensors.live_state import LiveState

    real = LiveState.snapshot

    def settled(self, astronaut_id, now, **kwargs):
        snap = real(self, astronaut_id, now, **kwargs)
        snap["temp"] = {"state": "settled", "value_c": 36.4}  # raw 35.8 + 0.6
        return snap

    monkeypatch.setattr(LiveState, "snapshot", settled)
    reply = crew_client.post("/settings/device", json={"reference_c": 36.9}).get_json()
    assert reply["ok"] and reply["wearable"]["temp_offset_c"] == pytest.approx(1.1)
    too_far = crew_client.post("/settings/device", json={"reference_c": 39.5})
    assert too_far.status_code == 400


# ── Demo panel ────────────────────────────────────────────

def test_sensor_mode_switch_is_manual_and_audited(seeded, crew_client):
    assert crew_client.post("/settings/sensor-mode", json={"mode": "demo"}).get_json()["mode"] == "demo"
    with seeded.app_context():
        assert Mission.query.one().sensor_mode == "demo"
        row = AuditLog.query.filter_by(action="sensor_mode_change").one()
        assert json.loads(row.meta_json) == {"from": "device", "to": "demo"}


def test_force_status_writes_a_classified_reading(seeded, crew_client):
    reply = crew_client.post("/settings/demo/force", json={"metric": "blood_pressure", "status": "alert"}).get_json()
    assert reply == {"ok": True, "status": "CRITICAL"}
    alerts = crew_client.get("/api/summary").get_json()["alerts"]
    assert any(alert["metric"] == "blood_pressure" for alert in alerts)
    refused = crew_client.post("/settings/demo/force", json={"metric": "heart_rate", "status": "alert"})
    assert refused.status_code == 400 and "Demo data" in refused.get_json()["message"]
    crew_client.post("/settings/sensor-mode", json={"mode": "demo"})
    assert crew_client.post("/settings/demo/force", json={"metric": "spo2", "status": "watch"}).get_json()["ok"]


def test_forced_generated_value_is_not_overwritten_by_the_next_slot(seeded, crew_client):
    crew_client.post("/settings/demo/force", json={"metric": "blood_pressure", "status": "alert"})
    with seeded.app_context():
        from app.models import Astronaut
        from app.services.live import get_runtime

        crew = Astronaut.query.filter_by(astro_id="AST-1001").one()
        get_runtime().sim.catch_up(crew, utcnow() + timedelta(minutes=20), force=True)
        latest = (Measurement.query.filter_by(astronaut_id=crew.id, metric="blood_pressure")
                  .order_by(Measurement.created_at.desc()).first())
        assert latest.value == 186, "held for 30 minutes after a Demo-panel reading"


@pytest.mark.parametrize("code, environment, delay, day", [
    ("mars_transit", "Spacecraft", 600, 142),
    ("lunar_base", "Lunar Base", None, None),
    ("critical_bp", None, 840, None),
])
def test_judge_mode_scenarios(seeded, crew_client, code, environment, delay, day):
    assert crew_client.post(f"/settings/demo/{code}", json={}).get_json()["ok"]
    summary = crew_client.get("/api/summary").get_json()
    with seeded.app_context():
        mission = Mission.query.one()
        if environment:
            assert mission.environment == environment
        if delay is not None:
            assert mission.comms_delay_s == delay
        if day is not None:
            assert summary["mission"]["day"] == day
        assert AuditLog.query.filter_by(action="demo_scenario").count() == 1
    by_key = {item["key"]: item for item in summary["metrics"]}
    if code == "critical_bp":
        assert any("14 min" in alert["text"] for alert in summary["alerts"])
    if code == "mars_transit":
        assert by_key["heart_rate"]["status"]["key"] == "watch" and by_key["sleep_hours"]["status"]["key"] == "watch"
    if code == "lunar_base":
        assert by_key["loading_index"]["status"]["key"] == "watch"


def test_jump_day_and_reset(crew_client):
    assert crew_client.post("/settings/demo/day", json={"day": 300}).get_json()["day"] == 300
    assert crew_client.get("/api/summary").get_json()["mission"]["day"] == 300
    assert crew_client.post("/settings/demo/day", json={"day": 0}).status_code == 400
    assert crew_client.post("/settings/demo/day", json={"day": "reset"}).get_json()["day"] == 160


def test_demo_panel_is_gone_without_demo_mode(tmp_path):
    app = build_app(make_values(tmp_path / "instance", DEMO_MODE="false"))
    client = app.test_client()
    login(client)
    assert "Demo panel" not in client.get("/settings").get_data(as_text=True)
    assert client.post("/settings/demo/critical_bp", json={}).status_code == 404
    assert client.post("/settings/sensor-mode", json={"mode": "demo"}).status_code == 404


# ── Mission Control ───────────────────────────────────────

def test_mission_control_shows_status_colours_and_audits_every_view(seeded):
    surgeon = seeded.test_client()
    login(surgeon, "FS-9001")
    page = surgeon.get("/mission-control").get_data(as_text=True)
    assert page.count('class="crew card') == 3
    assert "Readiness:" in page and not re.search(r"Readiness:\s*\d", page), "colour, never the number"
    detail = surgeon.get("/mission-control/crew/AST-1001").get_data(as_text=True)
    for hidden in ("Wellbeing", "transcript", "Mood", "Voice check-in"):
        assert hidden not in detail, hidden
    assert "Heart rate" in detail and "Blood pressure" in detail
    assert surgeon.get("/mission-control/crew/FS-9001").status_code == 404
    with seeded.app_context():
        actions = [row.action for row in AuditLog.query.filter_by(actor="FS-9001")]
        assert actions.count("mission_control_view") == 1 and actions.count("mission_control_crew_view") == 1


def test_mission_control_flags_follow_up_after_a_safety_event(seeded):
    with seeded.app_context():
        checkin = MentalCheckin.query.filter_by(astronaut_id=crew_id(seeded, "AST-1002")).order_by(
            MentalCheckin.started_at.desc()).first()
        checkin.safety_flag, checkin.started_at = True, utcnow() - timedelta(hours=2)
        db.session.commit()
    surgeon = seeded.test_client()
    login(surgeon, "FS-9001")
    page = surgeon.get("/mission-control").get_data(as_text=True)
    assert page.count("Follow-up requested") == 1


def test_astronauts_cannot_open_mission_control_and_surgeons_skip_astronaut_pages(seeded, crew_client):
    assert crew_client.get("/mission-control").status_code == 302
    surgeon = seeded.test_client()
    login(surgeon, "FS-9001")
    assert surgeon.get("/history").headers["Location"].endswith("/mission-control")
    assert surgeon.get("/api/notifications/poll").status_code == 403
    page = surgeon.get("/mission-control").get_data(as_text=True)
    assert "data-bell" not in page and "/settings" not in page


def test_user_settings_row_is_created_once(seeded, crew_client):
    crew_client.get("/settings")
    crew_client.get("/settings")
    with seeded.app_context():
        assert UserSettings.query.filter_by(astronaut_id=crew_id(seeded, "AST-1001")).count() == 1
