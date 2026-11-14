"""Heart check: session flow, coverage rule, rest verification, alert table rows, symptoms, manual SpO₂."""

from __future__ import annotations

from datetime import timedelta

from app.cardio import services
from app.extensions import db
from app.models import CardioSession, DailyTask, Measurement, Notification, utcnow
from app.services.sensors.device_gateway import ingest
from app.services.sensors.synthetic import SyntheticWearable
from conftest import crew_id, login
from test_live_backbone import device


def start(client, **body):
    payload = {"glucose_context": "fasting", "symptoms": [], **body}
    response = client.post("/cardio/start", json=payload)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def feed_session(app, seconds, *, hr=None, profile="normal", start_at=None, wearable=None, quality=None):
    """Send wearable frames through the gateway (the session listener collects them)."""
    runtime = app.extensions["live"]
    wearable = wearable or SyntheticWearable(profile=profile, seed=8)
    start_at = start_at or utcnow()
    with app.app_context():
        dev = device(app)
        for i in range(seconds):
            frame = wearable.frame()
            if hr is not None and frame["finger"]:
                frame["hr"] = hr + (i % 2)
            if quality is not None and frame["finger"]:
                frame["q"] = quality
            ingest(runtime, dev, wearable.batch([frame]), start_at + timedelta(seconds=i))
    return wearable


def run_for(app, astro="AST-1001"):
    return services.runs(app.extensions["live"]).get(crew_id(app, astro))


def test_page_renders(client):
    login(client)
    page = client.get("/cardio").get_data(as_text=True)
    assert "Start assessment" in page and "Before you start" in page
    assert "Simulated" not in page and "You typed this" not in page


def test_full_session_with_the_wearable(app, client):
    login(client)
    start(client)
    measure = client.post("/cardio/measure", json={"skip_rest": True}).get_json()
    assert measure["ok"] and measure["rest_verified"] is False, "a skipped rest never verifies"
    run = run_for(app)
    run.measure_started = utcnow() - timedelta(seconds=90)
    feed_session(app, 90, start_at=utcnow() - timedelta(seconds=90))
    results = client.post("/cardio/end", json={}).get_json()["results"]
    metrics = {row["metric"]: row for row in results["rows"]}
    assert {"heart_rate", "spo2", "blood_pressure", "glucose", "respiration"} <= set(metrics)
    assert results["xp"] == 30 and results["rest_note"]
    assert len(results["actions"]) == 3 and results["history"][-1]["current"]
    with app.app_context():
        session = CardioSession.query.one()
        assert session.ended_at and session.overall_status and session.rest_verified is False
        rows = Measurement.query.filter_by(session_type="cardio", session_id=session.id).all()
        assert all(row.context in ("resting", "fasting", None) for row in rows)
        hr = next(row for row in rows if row.metric == "heart_rate")
        assert hr.context == "resting" and hr.status is not None
        assert DailyTask.query.filter_by(task_code="cardio", done=True).count() == 1
    assert client.post("/cardio/end", json={}).status_code == 404, "the session is over"


def test_coverage_rule_saves_nothing_without_clean_readings(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    run_for(app).measure_started = utcnow() - timedelta(seconds=90)
    feed_session(app, 90, profile="no_finger", start_at=utcnow() - timedelta(seconds=90))
    results = client.post("/cardio/end", json={}).get_json()["results"]
    metrics = {row["metric"] for row in results["rows"]}
    assert "heart_rate" not in metrics and "spo2" not in metrics
    assert any("Not enough clean readings for heart rate" in text for text in results["messages"])


def test_rest_is_required_outside_demo_mode(app, client, env_values):
    from conftest import build_app

    strict = build_app({**env_values, "DEMO_MODE": "false"}).test_client()
    login(strict)
    start(strict)
    assert strict.post("/cardio/measure", json={"skip_rest": True}).get_json()["error"] == "rest_required"
    assert strict.post("/cardio/measure", json={}).get_json()["error"] == "rest_not_done"


def test_rest_verification_needs_steady_valid_frames(app, client):
    login(client)
    start(client)
    run = run_for(app)
    run.rest_started = utcnow() - timedelta(seconds=300)
    feed_session(app, 70, start_at=utcnow() - timedelta(seconds=70))
    reply = client.post("/cardio/measure", json={}).get_json()
    assert reply["rest_verified"] is True


def test_sustained_critical_heart_rate_needs_a_verified_rest(app, client):
    login(client)
    start(client)
    run = run_for(app)
    run.rest_started = utcnow() - timedelta(seconds=300)
    wearable = feed_session(app, 70, start_at=utcnow() - timedelta(seconds=140))
    client.post("/cardio/measure", json={})
    assert run.rest_verified
    run.measure_started = utcnow() - timedelta(seconds=90)
    feed_session(app, 90, hr=140, start_at=utcnow() - timedelta(seconds=60), wearable=wearable)
    assert run.gate_critical
    results = client.post("/cardio/end", json={}).get_json()["results"]
    hr = next(row for row in results["rows"] if row["metric"] == "heart_rate")
    assert hr["status"]["key"] == "alert"


def test_same_values_without_verified_rest_stay_needs_attention(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    run = run_for(app)
    run.measure_started = utcnow() - timedelta(seconds=90)
    feed_session(app, 90, hr=140, start_at=utcnow() - timedelta(seconds=90))
    assert not run.gate_critical
    results = client.post("/cardio/end", json={}).get_json()["results"]
    hr = next(row for row in results["rows"] if row["metric"] == "heart_rate")
    assert hr["status"]["key"] == "watch"
    with app.app_context():
        assert Notification.query.filter_by(type="critical").count() == 0


def test_low_quality_frames_never_pass_the_gate(app, client):
    login(client)
    start(client)
    run = run_for(app)
    run.rest_verified = True
    client.post("/cardio/measure", json={"skip_rest": True})
    run.rest_verified = True
    feed_session(app, 40, hr=140, quality=55)
    assert not run.gate_critical


def test_symptoms_make_the_check_critical(app, client):
    login(client)
    start(client, symptoms=["chest_pain", "not-a-symptom"])
    client.post("/cardio/measure", json={"skip_rest": True})
    run_for(app).measure_started = utcnow() - timedelta(seconds=90)
    results = client.post("/cardio/end", json={}).get_json()["results"]
    assert results["overall"]["key"] == "alert" and "chest pain" in results["symptoms"]
    assert results["actions"][0] == "Tell your crew medical officer now."
    alerts = client.get("/api/alerts").get_json()["alerts"]
    assert alerts and alerts[0]["text"].startswith("You reported chest pain")


def test_manual_low_oxygen_needs_confirmation(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    first = client.post("/cardio/reading", json={"via": "hand", "metric": "spo2", "value": 82}).get_json()
    assert first["status"] == "CAUTION" and first["needs_remeasure"] and first["min_gap_s"] == 60
    assert client.get("/api/alerts").get_json()["alerts"] == []
    run = run_for(app)
    with app.app_context():
        gate = app.extensions["alert_gate"]
        gate._pending_spo2[crew_id(app, "AST-1001")] -= 61
    second = client.post("/cardio/reading", json={"via": "hand", "metric": "spo2", "value": 81}).get_json()
    assert second["status"] == "CRITICAL"
    assert run.manual["spo2"]["value"] == 81


def test_manual_reading_validation(client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    assert client.post("/cardio/reading", json={"via": "hand", "metric": "spo2", "value": 300}).status_code == 400
    assert client.post("/cardio/reading", json={"via": "fax", "metric": "spo2", "value": 97}).status_code == 400
    bp = client.post("/cardio/reading", json={"via": "hand", "metric": "blood_pressure", "value": 186,
                                              "value2": 118}).get_json()
    assert bp["status"] == "CRITICAL", "a typed blood pressure is immediate (with a re-measure button)"


def test_bluetooth_strap_readings(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True, "modes": {"heart_rate": "ble"}})
    run = run_for(app)
    run.measure_started = utcnow() - timedelta(seconds=90)
    for i in range(90):
        run.ble.append((utcnow() - timedelta(seconds=89 - i), 70 + i % 3))
    assert client.post("/cardio/reading", json={"via": "strap", "metric": "spo2", "value": 97}).status_code == 400
    results = client.post("/cardio/end", json={}).get_json()["results"]
    assert next(row for row in results["rows"] if row["metric"] == "heart_rate")["value"].startswith("7")


def test_finger_off_pauses_the_countdown(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    feed_session(app, 2, profile="no_finger")
    run = run_for(app)
    with app.app_context():
        from app.models import Astronaut

        crew = Astronaut.query.filter_by(astro_id="AST-1001").one()
        payload = services.live_reading(app.extensions["live"], run, crew, app.extensions["astrovital_config"],
                                        utcnow())
    assert payload["waiting_for_finger"] is True and payload["readings"]["heart_rate"]["value"] is None
    assert payload["readings"]["blood_pressure"]["value"]


def test_pause_and_resume_track_time(app, client):
    login(client)
    start(client)
    client.post("/cardio/measure", json={"skip_rest": True})
    assert client.post("/cardio/pause", json={"paused": True}).get_json()["paused"] is True
    assert client.post("/cardio/pause", json={"paused": False}).get_json()["paused"] is False


def test_cancel_during_rest(app, client):
    login(client)
    start(client)
    assert client.post("/cardio/end", json={}).get_json()["cancelled"] is True
    with app.app_context():
        assert db.session.query(CardioSession).one().ended_at is None
