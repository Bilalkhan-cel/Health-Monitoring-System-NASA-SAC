"""Wearable path: ingest contract, quality gate, live state, aggregation, backlog, modes, SSE, SimRecorder."""

from __future__ import annotations

import json
import queue
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Device, DeviceEvent, Measurement, Mission, SensorSample, utcnow
from app.services import live_monitor
from app.services.sensors.aggregator import Aggregator
from app.services.sensors.device_gateway import DEMO_DEVICE_ID, flush_device, ingest, maybe_purge
from app.services.sensors.quality import FrameResult, temperature_slope
from app.services.sensors.synthetic import SyntheticWearable
from app.services.stream_hub import StreamHub, TooManyStreams, format_sse
from conftest import build_app, crew_id, load_script, login, make_values

emulator_module = load_script("device_emulator")
TOKEN = "test-device-token-0123456789"
LAN = {"Host": "127.0.0.1:5000"}
START = datetime(2026, 11, 14, 9, 0, 0)


class ClientSession:
    """Lets the real emulator talk to the Flask test client."""

    def __init__(self, client):
        self.client = client

    def post(self, url, data, headers, timeout):  # noqa: ARG002
        path = url.split("://", 1)[-1]
        path = path[path.index("/"):]
        response = self.client.post(path, data=data, headers={**headers, **LAN})

        class Wrapped:
            status_code = response.status_code
            ok = response.status_code < 400

            @staticmethod
            def json():
                return response.get_json()

        return Wrapped()


def device(app, device_id="AV-ESP32-01") -> Device:
    return Device.query.filter_by(device_id=device_id).one()


def feed(app, profile="normal", seconds=60, start=START, wearable=None, step=1.0):
    """Ingest one frame per simulated second through the gateway."""
    wearable = wearable or SyntheticWearable(profile=profile, seed=5)
    runtime = app.extensions["live"]
    results = []
    with app.app_context():
        dev = device(app)
        for i in range(seconds):
            frame = wearable.frame()
            batch = wearable.batch([frame])
            results.append(ingest(runtime, dev, batch, start + timedelta(seconds=i * step)))
    return wearable, results


def snapshot(app, astro="AST-1001", at=None):
    with app.app_context():
        return app.extensions["live"].live.snapshot(crew_id(app, astro), at or START + timedelta(seconds=59.5),
                                                    linked=True)


def post(client, batch, token=TOKEN, device_id="AV-ESP32-01", **extra):
    headers = {"X-Device-Token": token, "X-Device-Id": device_id, "Content-Type": "application/json", **LAN, **extra}
    return client.post("/api/device/ingest", data=json.dumps(batch), headers=headers)


# ── HTTP contract ─────────────────────────────────────────

def test_ping_and_ingest_need_the_token(client):
    assert client.get("/api/device/ping", headers={"X-Device-Token": TOKEN, "X-Device-Id": "AV-ESP32-01", **LAN}) \
        .get_json()["server"] == "astrovital"
    assert client.get("/api/device/ping", headers={"X-Device-Token": "nope", **LAN}).status_code == 401
    batch = SyntheticWearable().batch([SyntheticWearable().frame()])
    assert post(client, batch, token="wrong").get_json() == {"ok": False, "error": "bad_token"}


def test_token_rejections_are_logged_but_rate_limited(app, client):
    batch = SyntheticWearable().batch([SyntheticWearable().frame()])
    for _ in range(3):
        post(client, batch, token="wrong")
    with app.app_context():
        assert DeviceEvent.query.filter_by(kind="token_rejected").count() == 1


def test_device_routes_are_lan_only(client):
    batch = SyntheticWearable().batch([SyntheticWearable().frame()])
    assert post(client, batch, Host="localhost").status_code == 404
    assert post(client, batch, Host="abc.trycloudflare.com").status_code == 404
    assert post(client, batch, **{"X-Forwarded-For": "1.2.3.4"}).status_code == 404
    assert post(client, batch).status_code == 200


def test_unknown_device_and_mismatched_header(client):
    w = SyntheticWearable()
    assert post(client, w.batch([w.frame()], device_id="AV-OTHER"), device_id="AV-OTHER").status_code == 401
    assert post(client, w.batch([w.frame()]), device_id="AV-OTHER").status_code == 400


def test_auto_register_binds_new_devices_to_the_wearer(env_values):
    app = build_app({**env_values, "DEVICE_AUTO_REGISTER": "true"})
    w = SyntheticWearable()
    response = post(app.test_client(), w.batch([w.frame()], device_id="AV-NEW-02"), device_id="AV-NEW-02")
    assert response.status_code == 200
    with app.app_context():
        assert Device.query.filter_by(device_id="AV-NEW-02").one().astronaut_id == crew_id(app, "AST-1001")


def test_payload_limits_and_type_errors(client):
    w = SyntheticWearable()
    good = w.batch([w.frame()])
    too_big = dict(good, padding="x" * 17000)
    assert post(client, too_big).status_code == 413
    bad_type = json.loads(json.dumps(good))
    bad_type["frames"][0]["hr"] = "seventy"
    response = post(client, bad_type)
    assert response.status_code == 400 and response.get_json()["path"] == "frames[0].hr"
    too_many = w.batch([{k: v for k, v in w.frame().items() if k != "ppg"} for _ in range(61)])
    assert post(client, too_many).get_json()["path"] == "frames"
    response = client.post("/api/device/ingest", data="{not json", headers={"X-Device-Token": TOKEN,
                                                                             "X-Device-Id": "AV-ESP32-01", **LAN})
    assert response.status_code == 400


def test_bad_values_reject_only_that_frame(client):
    w = SyntheticWearable()
    frames = [w.frame(), w.frame(), w.frame()]
    frames[1]["hr"] = 400
    frames[2]["temp_c"] = float("nan")
    batch = w.batch(frames)
    response = client.post("/api/device/ingest", data=json.dumps(batch).replace("NaN", "1e999"),
                           headers={"X-Device-Token": TOKEN, "X-Device-Id": "AV-ESP32-01",
                                    "Content-Type": "application/json", **LAN})
    body = response.get_json()
    assert (body["accepted"], body["rejected"]) == (1, 2)
    assert body["cfg"] == {"rev": 1, "send_interval_ms": 1000}


def test_retried_batches_are_idempotent(app, client):
    w = SyntheticWearable()
    batch = w.batch([w.frame(), w.frame()])
    first, second = post(client, batch).get_json(), post(client, batch).get_json()
    assert (first["accepted"], second["accepted"], second["duplicate"]) == (2, 0, 2)
    with app.app_context():
        assert SensorSample.query.count() == 2


def test_device_rate_limit(tmp_path):
    app = build_app(make_values(tmp_path / "rl", DEVICE_RATE_LIMIT="5/minute"), rate_limits=True)
    client = app.test_client()
    w = SyntheticWearable()
    codes = [post(client, w.batch([w.frame()])).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


@pytest.mark.parametrize("profile, expected", [
    ("normal", 200), ("bad_token", 401), ("malformed", 400), ("duplicate", 200), ("restart", 200),
    ("wifi_gap", 200), ("no_finger", 200), ("flatline", 200), ("probe_missing", 200),
])
def test_every_emulator_profile_talks_http(client, profile, expected):
    emu = emulator_module.Emulator("http://127.0.0.1:5000", TOKEN, "AV-ESP32-01", profile, fast=True,
                                   session=ClientSession(client), quiet=True)
    log = emu.run(25)
    assert log[0][0] == expected
    assert all(status < 500 for status, _ in log)
    if profile == "duplicate":
        assert log[1][1]["duplicate"] == 1


def test_flood_profile_hits_the_limit(tmp_path):
    app = build_app(make_values(tmp_path / "flood", DEVICE_RATE_LIMIT="20/minute"), rate_limits=True)
    emu = emulator_module.Emulator("http://127.0.0.1:5000", TOKEN, "AV-ESP32-01", "flood", fast=True,
                                   session=ClientSession(app.test_client()), quiet=True)
    assert emu.run(30)[-1][0] == 429


# ── quality gate and live state ───────────────────────────

def test_normal_frames_go_live_after_settling(app):
    feed(app, seconds=6)
    early = snapshot(app, at=START + timedelta(seconds=5.5))
    assert early["state"] == "settling" and early["hr"] is None
    feed(app, seconds=20, start=START + timedelta(seconds=6), wearable=SyntheticWearable(seed=5, seq=6, up_ms=11000))
    live = snapshot(app, at=START + timedelta(seconds=25.5))
    assert live["state"] == "ok" and 60 < live["hr"] < 90 and live["spo2"] >= 96 and live["finger"]


def test_stale_values_are_never_shown(app):
    feed(app, seconds=20)
    later = snapshot(app, at=START + timedelta(seconds=19 + 6))
    assert later["hr"] is None and later["spo2"] is None


def test_device_goes_offline_and_shows_the_last_value_with_its_age(app):
    feed(app, seconds=20)
    gone = snapshot(app, at=START + timedelta(seconds=40))
    assert gone["state"] == "device_offline" and gone["hr"] is None
    assert gone["last"]["hr"] > 0 and gone["last"]["age_s"] >= 20


def test_lifting_the_finger_clears_values_at_once(app):
    wearable, _ = feed(app, seconds=20)
    wearable.profile = "no_finger"
    feed(app, seconds=1, start=START + timedelta(seconds=20), wearable=wearable)
    off = snapshot(app, at=START + timedelta(seconds=20.5))
    assert off["state"] == "no_finger" and off["hr"] is None and off["spo2"] is None


def test_no_finger_stores_raw_frames_but_no_readings(app):
    feed(app, "no_finger", seconds=130)
    with app.app_context():
        assert SensorSample.query.count() == 130
        assert Measurement.query.filter(Measurement.metric.in_(("heart_rate", "spo2"))).count() == 0
    assert snapshot(app, at=START + timedelta(seconds=129.5))["state"] == "no_finger"


def test_weak_signal_is_excluded(app):
    feed(app, "weak_signal", seconds=130)
    assert snapshot(app, at=START + timedelta(seconds=129.5))["state"] == "poor_signal"
    with app.app_context():
        assert Measurement.query.filter_by(metric="heart_rate").count() == 0


def test_flatline_is_flagged_as_a_stuck_sensor(app):
    feed(app, "flatline", seconds=30)
    with app.app_context():
        assert DeviceEvent.query.filter_by(kind="sensor_error").count() == 1
    assert snapshot(app, at=START + timedelta(seconds=29.5))["state"] == "poor_signal"


def test_jump_filter_holds_a_spike():
    from app.services.sensors.quality import DeviceQuality
    from app.services.sensors.frames import parse_frame
    from config import load_config

    q = DeviceQuality(load_config({"FINGER_SETTLE_S": "0"}), 0.6)
    w = SyntheticWearable(seed=1)
    results = []
    for i in range(12):
        raw = w.frame()
        if i == 8:
            raw["hr"] = raw["hr"] + 60
        results.append(q.process(parse_frame(raw, 0), START + timedelta(seconds=i)))
    assert not results[8].hr_valid and "suspect_hr" in results[8].flags
    assert results[9].hr_valid and results[9].confirmed_hr is None


def test_finger_flap_never_reuses_an_old_value(app):
    feed(app, "finger_flap", seconds=40)
    with app.app_context():
        events = [e.kind for e in DeviceEvent.query.order_by(DeviceEvent.id)]
    assert events.count("finger_off") >= 3 and events.count("finger_on") >= 3


# ── temperature ───────────────────────────────────────────

def test_probe_on_the_desk_never_classifies(app):
    feed(app, "probe_ambient", seconds=200)
    assert snapshot(app, at=START + timedelta(seconds=199.5))["temp"] == {"state": "ambient", "value_c": None}
    with app.app_context():
        assert Measurement.query.filter_by(metric="temperature_c").count() == 0


def test_probe_missing_and_warming_produce_no_temperature(app):
    feed(app, "probe_missing", seconds=100)
    assert snapshot(app, at=START + timedelta(seconds=99.5))["temp"]["state"] == "missing"
    with app.app_context():
        assert DeviceEvent.query.filter_by(kind="probe_missing").count() == 1


def test_warming_probe_settles_then_aggregates(app):
    feed(app, "probe_warming", seconds=400)
    with app.app_context():
        states = [row.temp_state for row in SensorSample.query.order_by(SensorSample.ts)]
        rows = Measurement.query.filter_by(metric="temperature_c").all()
    assert states[0] == "warming" and states[-1] == "settled"
    assert rows and all(row.source == "derived" and row.raw_value is not None for row in rows)
    assert all(abs(row.value - row.raw_value - 0.6) < 0.05 for row in rows)
    assert all(row.status in ("NOMINAL", "STABLE") for row in rows)


def test_temperature_slope():
    samples = [(START + timedelta(seconds=i * 10), 30 + i * 0.1) for i in range(12)]
    assert abs(temperature_slope(samples) - 0.6) < 1e-9


# ── aggregation ───────────────────────────────────────────

def test_aggregates_close_per_minute_with_enough_valid_frames(app):
    feed(app, seconds=185)
    with app.app_context():
        hr = Measurement.query.filter_by(metric="heart_rate").order_by(Measurement.created_at).all()
        spo2 = Measurement.query.filter_by(metric="spo2").all()
    assert len(hr) == 3 and all(row.n_samples >= 20 and row.window_s == 60 for row in hr)
    assert [row.created_at.second for row in hr] == [0, 0, 0]
    assert all(row.context == "unspecified" and row.status is None for row in hr), "no rest context, no status"
    assert all(row.status in ("NOMINAL", "STABLE") and row.source == "sensor" for row in spo2)


def test_window_needs_twenty_valid_frames():
    agg = Aggregator(60, 20)
    for i in range(19):
        agg.add(1, FrameResult(ts=START + timedelta(seconds=i), finger=True, state="ok", hr=70, hr_valid=True, q=90))
    assert agg.close_before(1, START + timedelta(minutes=2)) == []
    for i in range(21):
        agg.add(1, FrameResult(ts=START + timedelta(seconds=i), finger=True, state="ok", hr=70 + (i % 3), hr_valid=True,
                               q=80))
    closed = agg.flush(1)
    assert closed[0].value == 71 and closed[0].quality == 80 and closed[0].n_samples == 21


def test_backlog_is_history_only(app):
    runtime = app.extensions["live"]
    wearable = SyntheticWearable(seed=9)
    with app.app_context():
        dev = device(app)
        frames = [wearable.frame() for _ in range(90)]
        received = START + timedelta(seconds=200)
        for chunk in range(0, 90, 20):
            batch = wearable.batch(frames[chunk:chunk + 20])
            batch["sent_uptime_ms"] = frames[-1]["up_ms"] + 60_000  # sent 60 s after the newest frame
            ingest(runtime, dev, batch, received)
        assert SensorSample.query.filter_by(buffered=True).count() == 90
        assert DeviceEvent.query.filter_by(kind="backlog_replay").count() == 5
        assert Measurement.query.filter_by(metric="heart_rate").count() >= 1, "history fills in"
    live = snapshot(app, at=received)
    assert live["hr"] is None and live["state"] in ("device_offline", "no_finger", "ok")
    assert live["hr"] is None


def test_restart_resets_live_state(app):
    wearable, _ = feed(app, seconds=30)
    wearable.restart("ffff0001")
    feed(app, seconds=3, start=START + timedelta(seconds=30), wearable=wearable)
    with app.app_context():
        assert DeviceEvent.query.filter_by(kind="boot").count() == 2
    assert snapshot(app, at=START + timedelta(seconds=32.5))["state"] == "settling"


def test_offline_monitor_flushes_windows_once(app):
    feed(app, seconds=45)
    with app.app_context():
        report = live_monitor.tick(START + timedelta(seconds=70))
        again = live_monitor.tick(START + timedelta(seconds=75))
        assert (report["offline"], again["offline"]) == (1, 0)
        assert DeviceEvent.query.filter_by(kind="offline").count() == 1
        assert Measurement.query.filter_by(metric="heart_rate").count() == 1


def test_retention_purge(app):
    runtime = app.extensions["live"]
    feed(app, seconds=5, start=utcnow() - timedelta(days=9))
    runtime.last_purge = utcnow()  # keep the ingest path from purging before the explicit call
    feed(app, seconds=5, start=utcnow() - timedelta(minutes=5), wearable=SyntheticWearable(seed=2, boot_id="b2"))
    runtime.last_purge = None
    with app.app_context():
        assert maybe_purge(runtime, utcnow()) == 5
        assert SensorSample.query.count() == 5
        assert maybe_purge(runtime, utcnow()) == 0, "at most once an hour"


# ── sensor mode ───────────────────────────────────────────

def test_mode_never_changes_by_itself(app):
    feed(app, seconds=10)
    with app.app_context():
        for minute in range(11):
            report = live_monitor.tick(START + timedelta(minutes=minute, seconds=30))
            assert report["demo_frame"] is False
        assert Mission.query.one().sensor_mode == "device"
        assert SensorSample.query.join(Device).filter(Device.device_id == DEMO_DEVICE_ID).count() == 0


def test_demo_mode_is_manual_audited_and_isolates_real_frames(app, client):
    login(client)
    assert client.post("/settings/sensor-mode", json={"mode": "demo"}).get_json() == {"ok": True, "mode": "demo"}
    w = SyntheticWearable()
    response = post(client, w.batch([w.frame()])).get_json()
    assert response["ignored"] is True and response["accepted"] == 0
    with app.app_context():
        assert SensorSample.query.count() == 0
        for second in range(30):
            live_monitor.tick(utcnow() + timedelta(seconds=second))
        demo_rows = SensorSample.query.count()
        assert demo_rows == 30
        assert AuditLog.query.filter_by(action="sensor_mode_change").count() == 1
        flush_device(app.extensions["live"], device(app, DEMO_DEVICE_ID))
        db.session.commit()
        assert {m.source for m in Measurement.query.filter(Measurement.device_pk.isnot(None))} <= {"simulated"}
    client.post("/settings/sensor-mode", json={"mode": "device"})
    assert post(client, w.batch([w.frame()])).get_json()["accepted"] == 1
    assert client.post("/settings/sensor-mode", json={"mode": "auto"}).status_code == 400


def test_sensor_mode_route_needs_demo_mode(env_values):
    app = build_app({**env_values, "DEMO_MODE": "false"})
    client = app.test_client()
    login(client)
    assert client.post("/settings/sensor-mode", json={"mode": "demo"}).status_code == 404


# ── SSE and the hub ───────────────────────────────────────

def test_hub_queues_are_bounded_and_drop_the_oldest():
    hub = StreamHub()
    sub = hub.subscribe("t")
    for i in range(150):
        hub.publish("t", "vital", {"i": i})
    assert sub.queue.qsize() == 100
    assert sub.queue.get_nowait()[1]["i"] == 50


def test_hub_allows_four_streams_and_cleans_up():
    hub = StreamHub()
    subs = [hub.subscribe("t") for _ in range(4)]
    with pytest.raises(TooManyStreams):
        hub.subscribe("t")
    for sub in subs:
        hub.unsubscribe(sub)
    assert hub.count("t") == 0
    assert hub.publish("t", "vital", {}) == 0


def test_sse_format():
    assert format_sse("vital", {"hr": 74}) == 'event: vital\ndata: {"hr":74}\n\n'


def test_stream_endpoint_sends_a_snapshot_then_events(app, client):
    login(client)
    response = client.get("/api/stream")
    assert response.mimetype == "text/event-stream" and response.headers["Cache-Control"] == "no-cache"
    chunks = response.response
    first = next(chunks)
    first = first.decode() if isinstance(first, bytes) else first
    assert first.startswith("event: snapshot") and '"state":"no_device"' not in first
    runtime = app.extensions["live"]
    runtime.hub.publish_to(crew_id(app, "AST-1001"), "summary", {"metrics": ["spo2"]})
    second = next(chunks)
    assert (second.decode() if isinstance(second, bytes) else second).startswith("event: summary")
    response.close()
    assert runtime.hub.count(runtime.hub.topic_for(crew_id(app, "AST-1001"))) == 0


def test_saved_readings_publish_after_commit(app):
    runtime = app.extensions["live"]
    sub = runtime.hub.subscribe(runtime.hub.topic_for(crew_id(app, "AST-1001")))
    sub.queue = queue.Queue(maxsize=1000)  # this test checks publishing, not bounding
    feed(app, seconds=125)
    names = []
    while True:
        try:
            names.append(sub.queue.get_nowait()[0])
        except queue.Empty:
            break
    assert "vital" in names and "summary" in names and "device" in names


def test_live_endpoint_without_a_device(client):
    login(client, "AST-1002")
    assert client.get("/api/live").get_json()["state"] == "no_device"


# ── generated attributes ──────────────────────────────────

def test_sim_recorder_is_idempotent_and_never_fills_sensor_metrics(app):
    runtime = app.extensions["live"]
    with app.app_context():
        from app.models import Astronaut

        sara = Astronaut.query.filter_by(astro_id="AST-1001").one()
        now = datetime(2026, 11, 14, 12, 0, 0)
        first = runtime.sim.catch_up(sara, now, force=True)
        second = runtime.sim.catch_up(sara, now, force=True)
        assert first == 288 and second == 0
        assert runtime.sim.catch_up(sara, now + timedelta(minutes=12)) == 0, "rate limited"
        assert runtime.sim.catch_up(sara, now + timedelta(minutes=12), force=True) == 2
        metrics = {row.metric for row in Measurement.query.filter_by(source="simulated")}
        assert metrics == {"blood_pressure", "glucose", "respiration"}
        assert all(row.status in ("NOMINAL", "STABLE") for row in Measurement.query.filter_by(source="simulated"))
