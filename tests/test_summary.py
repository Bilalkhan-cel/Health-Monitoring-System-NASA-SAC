"""Today summary, history, tasks, seed story, the write path and the label rule."""

from __future__ import annotations

import json
from datetime import timedelta

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import bootstrap
from app.extensions import db
from app.models import Measurement, Notification, ReadinessDaily, utcnow
from app.services import measurements, summary
from conftest import ROOT, crew_id, load_script, login

verify = load_script("verify")


def test_summary_has_no_source_anywhere(seeded_app):
    client = seeded_app.test_client()
    login(client)
    for path in ("/api/summary", "/api/alerts", "/api/bodypart/heart", "/api/gamification",
                 "/api/history?metric=heart_rate&range=30d", "/api/history?metric=readiness&range=mission"):
        payload = client.get(path).get_json()
        assert verify.find_source_keys(payload) == [], path
        assert verify.scan_source_labels(json.dumps(payload)) == [], path
    page = client.get("/dashboard").get_data(as_text=True)
    assert verify.scan_source_labels(page) == []


def test_seed_tells_the_story(seeded_app):
    client = seeded_app.test_client()
    login(client)
    data = client.get("/api/summary").get_json()
    metrics = {item["key"]: item for item in data["metrics"]}
    assert metrics["heart_rate"]["value"] == "104" and metrics["heart_rate"]["status"]["verdict"] == "A bit high"
    assert "above your usual" in metrics["heart_rate"]["usual"]
    assert metrics["sleep_hours"]["status"]["key"] == "watch"
    assert data["readiness"]["score"] <= 79 and data["readiness"]["status"]["key"] == "watch"
    assert data["readiness"]["sentence"].startswith("Two things need attention: your heart rate")
    assert data["readiness"]["caption"] == "Wellness estimate · not a fitness-for-duty decision"
    assert data["alerts"] == [], "the old blood-pressure event is not fresh"
    assert data["tasks"]["done"] == 2 and data["tasks"]["streak"] >= 7
    with seeded_app.app_context():
        critical = Measurement.query.filter_by(astronaut_id=crew_id(seeded_app, "AST-1001"), status="CRITICAL").all()
        assert [(m.metric, m.value, m.value2) for m in critical] == [("blood_pressure", 186, 118)]


def test_readiness_history_shows_the_spike(seeded_app):
    client = seeded_app.test_client()
    login(client)
    history = client.get("/api/history?metric=readiness&range=30d").get_json()
    assert len(history["tiles"]) == 30
    assert any(tile["status"] == "alert" for tile in history["tiles"])
    assert history["events"] and "blood pressure" in history["events"][0]["label"]
    assert history["summary"].startswith("Readiness over the last 30 days")


def test_other_astronauts_have_their_own_story(seeded_app):
    client = seeded_app.test_client()
    login(client, "AST-1003")
    data = client.get("/api/summary").get_json()
    assert data["astronaut"]["first_name"] == "Aisha"
    assert all(item["status"] is None or item["status"]["key"] != "alert" for item in data["metrics"])


def test_history_validates_its_arguments(seeded_app):
    client = seeded_app.test_client()
    login(client)
    assert client.get("/api/history?metric=readiness&range=year").status_code == 400
    assert client.get("/api/history?metric=nope&range=7d").status_code == 400
    assert client.get("/api/bodypart/liver").status_code == 404


def test_history_is_bucketed_to_500_points():
    points = [{"t": str(i), "v": float(i)} for i in range(1999)]
    reduced = summary._bucket(points)
    assert len(reduced) <= 500 and reduced[0]["v"] == 1.5


def test_bodypart_is_environment_aware(seeded_app):
    client = seeded_app.test_client()
    login(client)
    mars = client.get("/api/bodypart/bones").get_json()
    assert any("third of Earth" in step for step in mars["steps"]) or mars["status"]["key"] == "good"
    client.post("/settings/environment", json={"environment": "Space Station"})
    station = client.get("/api/bodypart/bones").get_json()
    assert station["mission"]["comms_delay_text"] == "2 s" and station["mission"]["gravity_g"] == 0.0
    client.post("/settings/environment", json={"environment": "Mars Base"})
    assert client.post("/settings/environment", json={"environment": "Pluto"}).status_code == 400


def test_water_and_sleep_tasks(app, client):
    login(client)
    for _ in range(9):
        last = client.post("/api/tasks/hydration/done", json={}).get_json()
    assert last["water_ml"] == 2250 and last["xp_gained"] == 0
    done = client.post("/api/tasks/hydration/done", json={}).get_json()
    assert done["water_ml"] == 2500 and done["xp_gained"] == 10
    sleep = client.post("/api/tasks/sleep_log/done", json={"hours": 5.5, "quality": "2"}).get_json()
    assert sleep["status"] == "CAUTION" and sleep["xp_gained"] == 10
    assert client.post("/api/tasks/sleep_log/done", json={"hours": 30}).status_code == 400
    assert client.post("/api/tasks/cardio/done", json={}).get_json()["error"] == "finish_in_module"
    tasks = {item["code"]: item for item in client.get("/api/summary").get_json()["tasks"]["items"]}
    assert tasks["hydration"]["state"] == "done" and tasks["sleep_log"]["detail"] == "5 h 30 min"


def test_record_classifies_gates_and_notifies(app):
    astronaut = crew_id(app, "AST-1001")
    with app.app_context():
        first = measurements.record(astronaut, "spo2", 82, source="manual")
        assert (first.status, first.confirmed, first.needs_remeasure) == ("CAUTION", False, True)
        note = Notification.query.one()
        assert note.title == "Re-measure your oxygen"
        later = measurements.record(astronaut, "spo2", 81, source="manual",
                                    created_at=first.measurement.created_at + timedelta(seconds=90))
        assert later.status == "CRITICAL"
        assert ReadinessDaily.query.filter_by(astronaut_id=astronaut).count() == 1
        background = measurements.record(astronaut, "heart_rate", 150, source="sensor", context="unspecified",
                                         device_pk=None, origin="wearable")
        assert background.status is None


def test_record_rejects_implausible_values(app):
    astronaut = crew_id(app, "AST-1001")
    with app.app_context():
        for metric, value, value2 in (("heart_rate", 400, None), ("blood_pressure", 80, 120), ("spo2", -1, None),
                                      ("weight", 70, None)):
            try:
                measurements.record(astronaut, metric, value, value2=value2, source="manual")
            except measurements.InvalidReading:
                continue
            raise AssertionError(f"{metric} {value} was accepted")


def test_symptom_override_is_critical_regardless_of_value(app):
    astronaut = crew_id(app, "AST-1001")
    with app.app_context():
        result = measurements.record(astronaut, "heart_rate", 72, source="manual", context="resting", symptom=True)
        assert result.status == "CRITICAL"


def test_seed_is_idempotent(seeded_app):
    with seeded_app.app_context():
        before = Measurement.query.count()
        _, seeded, _ = bootstrap.prepare_data(seeded_app, seed=True)
        assert seeded == 0 and Measurement.query.count() == before


def test_migrations_match_the_models(env_values, tmp_path):
    from app import create_app
    from config import load_config

    app = create_app(load_config({**env_values, "ASTROVITAL_INSTANCE_DIR": str(tmp_path / "mig")}), testing=True)
    assert bootstrap.ensure_database(app)
    with app.app_context():
        context = MigrationContext.configure(db.engine.connect())
        diff = compare_metadata(context, db.metadata)
    assert diff == [], diff
    assert (ROOT / "migrations" / "env.py").exists()


def test_summary_speed_with_history(seeded_app):
    import time

    client = seeded_app.test_client()
    login(client)
    timings = []
    for _ in range(10):
        started = time.perf_counter()
        client.get("/api/summary")
        timings.append(time.perf_counter() - started)
    assert sorted(timings)[-1] < 0.3


def test_readiness_is_stored_per_day(seeded_app):
    with seeded_app.app_context():
        rows = ReadinessDaily.query.filter_by(astronaut_id=crew_id(seeded_app, "AST-1001")).count()
        assert rows == 30
        assert utcnow().date() in {row.date for row in ReadinessDaily.query}
