"""Mind check-in: safety screen, wellbeing score, chunks, background transcription, privacy."""

from __future__ import annotations

import io
import time

import pytest

from app.extensions import db
from app.mental import services
from app.models import AudioChunk, MentalCheckin, Measurement, Notification, UserSettings
from app.services import nlp_service, whisper_service
from conftest import ROOT, crew_id, login

FIXTURES = ROOT / "tests" / "fixtures"


def phrases() -> list[str]:
    lines = (FIXTURES / "safety_phrases.txt").read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.strip() and not line.startswith("#")]


def test_safety_screen_recall_is_100_percent():
    missed = [phrase for phrase in phrases() if not nlp_service.safety_screen(phrase)]
    assert missed == [], missed
    assert len(phrases()) >= 20


def test_safety_screen_leaves_ordinary_talk_alone():
    for text in nlp_service.safety_config()["benign_examples"] + [
            "We had to end it early because of the comms window", "The crew was great today, I'm just tired"]:
        assert not nlp_service.safety_screen(text), text


def test_wellbeing_formula_and_categories():
    analysis = nlp_service.Analysis(pos_ratio=1.0, neg_ratio=0.0, emotions={"joy": 1.0}, themes=[])
    assert nlp_service.wellbeing_score(analysis, 10) == 100
    low = nlp_service.Analysis(pos_ratio=0.0, neg_ratio=1.0, emotions={"sadness": 1.0},
                               themes=["stress", "fatigue", "loneliness", "homesickness"])
    assert nlp_service.wellbeing_score(low, 1) == 0
    mixed = nlp_service.Analysis(pos_ratio=0.5, neg_ratio=0.5, emotions={"neutral": 1.0}, themes=["fatigue"])
    # sentiment 0.5, emotion 0.5, flags 0.75; no self-rating -> renormalised over 0.8
    assert nlp_service.wellbeing_score(mixed, None) == pytest.approx(100 * (0.35 * .5 + 0.25 * .5 + 0.2 * .75) / 0.8,
                                                                     abs=0.1)
    assert nlp_service.mood_category(70) == ("Good", "NOMINAL")
    assert nlp_service.mood_category(55) == ("Okay", "STABLE")
    assert nlp_service.mood_category(54.9) == ("Low", "CAUTION")


def test_themes_and_summary_never_diagnose():
    analysis = nlp_service.analyse("I keep waking up at three. I miss my family and I feel so tired.",
                                   ROOT / "missing", ROOT / "missing")
    assert set(analysis.themes) >= {"sleep trouble", "homesickness", "fatigue"}
    text = nlp_service.summary_text(analysis, 50, "Low")
    assert "diagnos" not in text.lower() or "not a diagnosis" in text.lower()
    assert analysis.engine == "word lists"


def test_text_checkin_end_to_end(app, client):
    login(client)
    reply = client.post("/mental/text", json={"text": "The crew was great today. I am happy with the experiment. "
                                                      "I slept well.", "self_mood": 8, "self_sleep": 4})
    results = reply.get_json()["results"]
    assert results["category"] in ("Good", "Okay") and results["score"] > 55
    assert results["transcript"] is None, "transcripts are not stored by default"
    assert sum(results["emotions"].values()) == pytest.approx(1, abs=0.01)
    with app.app_context():
        checkin = MentalCheckin.query.one()
        assert checkin.status == "done" and checkin.transcript is None and checkin.wellbeing_score == results["score"]
        assert Measurement.query.filter_by(metric="wellbeing", source="nlp").count() == 1


def test_text_checkin_keeps_the_transcript_when_allowed(app, client):
    with app.app_context():
        UserSettings.query.filter_by(astronaut_id=crew_id(app, "AST-1001")).one().store_transcripts = True
        db.session.commit()
    login(client)
    results = client.post("/mental/text", json={"text": "A calm day."}).get_json()["results"]
    assert results["transcript"] == "A calm day."
    assert client.delete(f"/mental/{results['checkin_id']}/transcript").get_json()["ok"]
    with app.app_context():
        assert db.session.get(MentalCheckin, results["checkin_id"]).transcript is None


def test_safety_hit_skips_results_and_escalates(app, client):
    login(client)
    reply = client.post("/mental/text", json={"text": "Work was fine. Honestly I want to kill myself."}).get_json()
    assert reply["results"]["safety"] is True and "crew medical officer" in reply["results"]["message"]
    with app.app_context():
        assert Notification.query.filter_by(type="critical").count() == 1
        wellbeing = Measurement.query.filter_by(metric="wellbeing").one()
        assert wellbeing.status == "CRITICAL"
        assert MentalCheckin.query.one().safety_flag


def wav_bytes() -> bytes:
    return (FIXTURES / "audio" / "checkin_en.wav").read_bytes()


def test_chunks_are_idempotent_owned_and_size_limited(app, client, monkeypatch):
    monkeypatch.setattr(whisper_service, "transcribe", lambda *a, **k: "just a short test")
    login(client)
    checkin_id = client.post("/mental/start", json={"mode": "voice"}).get_json()["checkin_id"]
    send = lambda seq, data=None, cid=checkin_id: client.post(  # noqa: E731
        "/mental/chunk", data={"checkin_id": str(cid), "seq": str(seq),
                               "audio": (io.BytesIO(data or wav_bytes()), "c.wav")}, content_type="multipart/form-data")
    assert send(0).get_json()["stored"] is True
    assert send(0).get_json()["stored"] is False
    assert send(1, b"not audio").status_code == 400
    assert send(2, b"RIFF" + b"\0" * (2 * 1024 * 1024 + 10)).status_code == 413
    other = app.test_client()
    login(other, "AST-1002")
    response = other.post("/mental/chunk", data={"checkin_id": str(checkin_id), "seq": "5",
                                                 "audio": (io.BytesIO(wav_bytes()), "c.wav")},
                          content_type="multipart/form-data")
    assert response.status_code == 404, "another astronaut cannot add to my check-in"
    for _ in range(50):
        if client.get(f"/mental/status/{checkin_id}").get_json()["pending"] == 0:
            break
        time.sleep(0.1)
    status = client.get(f"/mental/status/{checkin_id}").get_json()
    assert status["preview"] == "just a short test"
    config = app.extensions["astrovital_config"]
    assert list(config.uploads_dir.glob(f"checkin-{checkin_id}-*.wav")) == [], "audio deleted after reading"


def test_voice_checkin_flow_with_injected_transcript(app, client, monkeypatch):
    monkeypatch.setattr(whisper_service, "transcribe",
                        lambda *a, **k: "The crew was great today. I am tired and I miss my family.")
    login(client)
    checkin_id = client.post("/mental/start", json={"mode": "voice"}).get_json()["checkin_id"]
    client.post("/mental/chunk", data={"checkin_id": str(checkin_id), "seq": "0",
                                       "audio": (io.BytesIO(wav_bytes()), "c.wav")}, content_type="multipart/form-data")
    reply = None
    for _ in range(60):
        reply = client.post("/mental/finish", json={"checkin_id": checkin_id, "duration_s": 75, "self_mood": 6})
        if reply.status_code == 200:
            break
        time.sleep(0.1)
    results = reply.get_json()["results"]
    assert {"fatigue", "homesickness"} <= set(results["themes"])
    with app.app_context():
        assert AudioChunk.query.one().status == "done"


def test_too_short_voice_checkin_is_not_scored(client, monkeypatch):
    monkeypatch.setattr(whisper_service, "transcribe", lambda *a, **k: "hi")
    login(client)
    checkin_id = client.post("/mental/start", json={"mode": "voice"}).get_json()["checkin_id"]
    results = client.post("/mental/finish", json={"checkin_id": checkin_id, "duration_s": 10}).get_json()["results"]
    assert results["too_short"] is True


def test_three_low_days_send_a_supportive_note(app, client):
    from datetime import timedelta

    from app.models import utcnow
    from app.services import measurements

    astronaut = crew_id(app, "AST-1001")
    with app.app_context():
        for days in (2, 1):
            measurements.record(astronaut, "wellbeing", 40, source="nlp", created_at=utcnow() - timedelta(days=days))
    login(client)
    client.post("/mental/text", json={"text": "Everything feels awful and sad. I am so tired and lonely."})
    with app.app_context():
        assert Notification.query.filter(Notification.dedupe_key.like("mood_low:%")).count() == 1


@pytest.mark.skipif(not whisper_service.available(ROOT / "ml_models" / "whisper" / "base"),
                    reason="Whisper model not downloaded")
def test_whisper_transcribes_the_recorded_clip():
    text = whisper_service.transcribe(FIXTURES / "audio" / "checkin_en.wav", ROOT / "ml_models" / "whisper" / "base")
    lowered = text.lower()
    assert "crew" in lowered and "tired" in lowered and "home" in lowered


@pytest.mark.skipif(not nlp_service.models_available(ROOT / "ml_models" / "sentiment", ROOT / "ml_models" / "emotion"),
                    reason="NLP models not downloaded")
def test_local_models_analyse_text():
    analysis = nlp_service.analyse("I love this mission. Today was wonderful. I feel hopeless and sad tonight.",
                                   ROOT / "ml_models" / "sentiment", ROOT / "ml_models" / "emotion")
    assert analysis.engine == "models"
    assert analysis.pos_ratio > 0 and analysis.neg_ratio > 0
    assert max(analysis.emotions, key=analysis.emotions.get) in ("joy", "sadness")
