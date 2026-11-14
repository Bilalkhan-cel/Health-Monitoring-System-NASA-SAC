"""Dr. NOVA: context builder, engines, persona rules, bridge, sessions, mock voice, Ability build."""

from __future__ import annotations

import json
import threading
import time
from datetime import timedelta

import pytest

from app.doctor import routes as doctor_routes
from app.doctor import services
from app.extensions import db
from app.models import AuditLog, ChatMessage, DoctorSession, Notification, SleepLog, utcnow
from app.services import doctor_context, openhome_service, rules_engine
from conftest import build_app, crew_id, load_script, login, make_values
from mock_openhome import RECEIVED, MockServer

build_script = load_script("build_openhome_ability")
TOKEN = "test-bridge-token-0123456789"


def context(app, astro="AST-1001"):
    with app.app_context():
        return doctor_context.build(crew_id(app, astro), app.extensions["astrovital_config"])


def test_context_is_minimal_and_has_sources(seeded_app):
    ctx = context(seeded_app)
    text = json.dumps(ctx)
    assert "Sara" not in text and "Whitman" not in text and "AST-" not in text and "@" not in text
    assert ctx["profile"] == {"callsign": "Falcon", "role": "Commander", "age": 41}
    hr = next(item for item in ctx["latest"] if item["metric"] == "heart_rate")
    assert hr["value"] == 104 and hr["status_word"] == "Needs attention" and hr["source"] == "simulated"
    assert hr["baseline"] and hr["vs_baseline"].startswith("+")
    assert ctx["mission"]["comms_delay_one_way_s"] == 760
    other = context(seeded_app, "AST-1002")
    assert other["profile"]["callsign"] == "Atlas"


def test_rules_engine_answers_from_real_values_without_sources(seeded_app):
    ctx = context(seeded_app)
    reply = rules_engine.answer("How am I doing today?", ctx)
    assert "104" in reply and "Falcon" in reply
    for word in ("simulated", "generated", "wearable sensor", "entered by hand", "source"):
        assert word not in reply.lower(), word


def test_rules_engine_tells_the_truth_when_asked_how_a_number_was_measured(seeded_app):
    ctx = context(seeded_app)
    bp = rules_engine.answer("How was my blood pressure measured?", ctx)
    assert "generated for demonstration" in bp and "wearable sensor" not in bp
    hr = rules_engine.answer("Where does that heart rate number come from?", ctx)
    assert "generated for demonstration" in hr


def test_never_claims_the_wearable_measured_blood_pressure():
    ctx = {"latest": [{"metric": "blood_pressure", "value": {"sys": 120, "dia": 80}, "unit": "mmHg",
                       "status_word": "Okay", "source": "simulated", "data_age_h": 1}],
           "profile": {"callsign": "Falcon"}, "mission": {"environment": "Mars Base", "comms_delay_one_way_s": 760}}
    assert "measured by the wearable" not in rules_engine.answer("is my blood pressure real?", ctx)


def test_emergency_symptoms_escalate_with_the_comms_delay(seeded_app):
    reply = rules_engine.answer("I have chest pain", context(seeded_app))
    assert "crew medical officer now" in reply and "12 min 40 s" in reply


def test_no_medication_or_diagnosis(seeded_app):
    ctx = context(seeded_app)
    assert "can't recommend medicines" in rules_engine.answer("What dose of ibuprofen should I take?", ctx)
    assert "can't give a diagnosis" in rules_engine.answer("Do I have a heart problem?", ctx)


def test_missing_data_is_admitted(app):
    ctx = context(app)
    assert "don't have a recent" in rules_engine.answer("how is my oxygen?", ctx)


def test_voice_style_uses_spoken_order_words(seeded_app):
    reply = rules_engine.answer("how is my heart?", context(seeded_app), voice=True)
    assert "First," in reply and "\n" not in reply


def test_text_chat_offline_engine_and_history(app, client):
    login(client)
    reply = client.post("/doctor/chat", json={"message": "How am I doing?"}).get_json()
    assert reply["engine"] == "OFFLINE RULES" and reply["reply"]
    assert client.post("/doctor/chat", json={"message": "  "}).status_code == 400
    with app.app_context():
        assert [m.role for m in ChatMessage.query.order_by(ChatMessage.id)] == ["user", "assistant"]
    page = client.get("/doctor").get_data(as_text=True)
    assert "How am I doing?" in page and "What Dr. NOVA sees" in page
    client.post("/doctor/new", json={})
    assert "How am I doing?" not in client.get("/doctor").get_data(as_text=True)
    with app.app_context():
        assert ChatMessage.query.count() == 2, "a new consultation keeps the stored history"


def test_chat_runs_the_safety_screen_first(app, client, monkeypatch):
    called = []
    monkeypatch.setattr(rules_engine, "answer", lambda *a, **k: called.append(1) or "no")
    login(client)
    reply = client.post("/doctor/chat", json={"message": "I want to end my life"}).get_json()
    assert "crew medical officer" in reply["reply"] and called == []
    with app.app_context():
        assert Notification.query.filter_by(type="critical").count() == 1
        assert AuditLog.query.filter_by(action="safety_followup").count() == 1


def test_fallback_llm_is_used_when_configured(env_values, monkeypatch):
    app = build_app({**env_values, "FALLBACK_LLM_API_KEY": "sk-test", "OPENHOME_MOCK": "true"})
    from app.services import llm_fallback

    monkeypatch.setattr(llm_fallback, "chat", lambda *a, **k: "From the fallback model.")
    client = app.test_client()
    login(client)
    reply = client.post("/doctor/chat", json={"message": "hello"}).get_json()
    assert reply == {"ok": True, "reply": "From the fallback model.", "engine": "FALLBACK LLM"}


# ── bridge ────────────────────────────────────────────────

def bridge(client, path="/api/openhome/context", token=TOKEN, method="get", **kwargs):
    headers = {"X-AstroVital-Token": token, "Host": "abc.trycloudflare.com"}
    return getattr(client, method)(path, headers=headers, **kwargs)


def test_bridge_needs_the_token_and_an_active_session(app, client):
    assert bridge(client, token="wrong").status_code == 401
    assert bridge(client).get_json()["error"] == "no_active_session"
    login(client)
    client.post("/doctor/session", json={})
    payload = bridge(client).get_json()
    assert payload["profile"]["callsign"] == "Falcon"
    with app.app_context():
        assert AuditLog.query.filter_by(action="bridge_context").count() == 1
        assert AuditLog.query.filter_by(action="bridge_bad_token").count() == 1


def test_two_live_sessions_are_ambiguous(app, client):
    other = app.test_client()
    login(client)
    login(other, "AST-1002")
    client.post("/doctor/session", json={})
    other.post("/doctor/session", json={})
    response = bridge(app.test_client())
    assert response.status_code == 409 and response.get_json()["error"] == "ambiguous_session"


def test_stale_sessions_fail_closed(app, client):
    login(client)
    client.post("/doctor/session", json={})
    with app.app_context():
        session = DoctorSession.query.one()
        session.last_heartbeat_at = utcnow() - timedelta(seconds=46)
        db.session.commit()
    assert bridge(client).status_code == 404
    client.post("/doctor/session/end", json={})
    with app.app_context():
        assert DoctorSession.query.filter_by(active=True).count() == 0


def test_bridge_voice_log(app, client):
    login(client)
    client.post("/doctor/session", json={})
    ok = bridge(client, "/api/openhome/log", method="post", json={"metric": "sleep_hours", "value": 6.5})
    assert ok.get_json()["message"] == "Logged 6.5 hours of sleep."
    assert bridge(client, "/api/openhome/log", method="post", json={"metric": "sleep_hours", "value": 40}).status_code == 400
    assert bridge(client, "/api/openhome/log", method="post", json={"metric": "mood", "value": 7}).status_code == 200
    with app.app_context():
        assert SleepLog.query.one().source == "voice"


def test_bridge_is_reachable_through_the_tunnel_but_the_app_is_not(client):
    assert client.get("/login", headers={"Host": "abc.trycloudflare.com"}).status_code == 404
    assert bridge(client, token="wrong").status_code == 401


def test_health_reports_the_mode(client):
    login(client)
    assert client.get("/api/openhome/health").get_json()["mode"] == "mock"


def test_origin_check(app):
    with app.test_request_context():
        assert doctor_routes.origin_allowed("http://localhost:5000")
        assert doctor_routes.origin_allowed("http://127.0.0.1:5000")
        assert not doctor_routes.origin_allowed("https://evil.example")
        assert not doctor_routes.origin_allowed(None)


# ── voice upstreams ───────────────────────────────────────

def test_mock_upstream_greets_and_answers_typed_text():
    frames = []
    upstream = openhome_service.MockUpstream(frames.append, lambda text: f"Answer to {text}", "Hello Falcon.")
    time.sleep(0.4)
    upstream.send({"type": "transcribed", "data": "how am I doing"})
    time.sleep(0.6)
    upstream.close()
    finals = [f["data"] for f in frames if f["type"] == "message" and f["data"]["final"]]
    assert finals[0]["content"] == "Hello Falcon."
    assert {"role": "user", "content": "how am I doing", "live": False, "final": True} in finals
    assert finals[-1]["content"] == "Answer to how am I doing"
    assert all(f["type"] != "audio" for f in frames), "the mock sends captions only"


def test_mock_upstream_transcribes_speech_after_a_pause():
    import struct

    frames, heard = [], []
    upstream = openhome_service.MockUpstream(frames.append, lambda text: "ok", "Hi.",
                                             transcribe=lambda pcm: heard.append(len(pcm)) or "hello there")
    time.sleep(0.3)
    loud = struct.pack("<3200h", *([8000, -8000] * 1600))
    quiet = bytes(6400)
    import base64

    for chunk in [loud] * 3 + [quiet] * 7:
        upstream.send({"type": "audio", "data": base64.b64encode(chunk).decode()})
    time.sleep(0.5)
    upstream.close()
    assert heard and any(f["data"].get("content") == "hello there" for f in frames if f["type"] == "message")


def test_text_call_contract_against_the_mock_server(env_values):
    from config import load_config

    with MockServer() as server:
        config = load_config({**env_values, "OPENHOME_MOCK": "false", "OPENHOME_API_KEY": "test-key",
                              "OPENHOME_AGENT_ID": "42", "OPENHOME_VOICE_WS": server.url_template})
        assert openhome_service.mode(config) == "live"
        reply = openhome_service.text_call(config, "how am I doing?", timeout=10)
    assert reply == "You said: how am I doing?"
    expected = {("transcribed", "how am I doing?"), ("text", "bot-speaking"), ("ack", "audio-received")}
    deadline = time.monotonic() + 2.0  # the mock records frames on its own thread
    while time.monotonic() < deadline:
        kinds = {(frame["type"], frame["data"]) for frame in list(RECEIVED) if isinstance(frame.get("data"), str)}
        if expected <= kinds:
            break
        time.sleep(0.02)
    assert expected <= kinds, kinds


def test_live_upstream_relays_frames_both_ways(env_values):
    from config import load_config

    with MockServer() as server:
        config = load_config({**env_values, "OPENHOME_MOCK": "false", "OPENHOME_API_KEY": "test-key",
                              "OPENHOME_AGENT_ID": "42", "OPENHOME_VOICE_WS": server.url_template})
        frames = []
        upstream = openhome_service.OpenHomeUpstream(config, frames.append)
        assert upstream.wait_open(5)
        upstream.send({"type": "transcribed", "data": "Doctor Nova, check my health"})
        deadline = time.time() + 5
        while time.time() < deadline and not any(f.get("type") == "audio" for f in frames):
            time.sleep(0.05)
        upstream.close()
    assert any(f["type"] == "audio" for f in frames) and any(f["type"] == "text" for f in frames)


def test_redaction_hides_the_key(env_values):
    from config import load_config

    config = load_config({**env_values, "OPENHOME_API_KEY": "secret-openhome-key"})
    assert "secret-openhome-key" not in openhome_service.redact(openhome_service.voice_url(config), config)


# ── Ability build ─────────────────────────────────────────

def test_ability_renders_and_passes_the_openhome_rules():
    persona = 'Say "hi" and use """triple quotes""" safely.'
    code = build_script.render("https://abc.trycloudflare.com/", "tok123", persona)
    assert build_script.validate(code) == []
    assert 'ASTROVITAL_URL = "https://abc.trycloudflare.com"' in code and 'BRIDGE_TOKEN = "tok123"' in code
    namespace: dict = {}
    compile(code, "main.py", "exec")
    assert "resume_normal_flow()" in code and "#{{register capability}}" in code
    assert build_script.validate(code.replace("finally:", "finally:\n            print('x')"))


def test_ability_exit_phrases_and_log_patterns():
    code = build_script.render("http://x", "t", "p")
    head = code.split("class AstroVitalHealthContext")[0]
    for line in ("from src.agent.capability import MatchingCapability",
                 "from src.agent.capability_worker import CapabilityWorker", "from src.main import AgentWorker"):
        head = head.replace(line, "")
    namespace: dict = {}
    exec(compile(head, "ability_head", "exec"), namespace)  # noqa: S102 (test of our own rendered template)
    assert namespace["_is_exit"]("Thanks, Dr. Nova!") and namespace["_is_exit"]("goodbye")
    assert not namespace["_is_exit"]("I can't stop coughing")
    pattern = dict(namespace["_LOG_PATTERNS"])["sleep_hours"]
    assert pattern.search(namespace["_normalize"]("Log my 6.5 hours of sleep")).group(1) == "6.5"
