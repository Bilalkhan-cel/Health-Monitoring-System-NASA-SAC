"""Bone & Muscle: rep state machines on synthetic keypoints, cadence, loading index, routes."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import DailyTask, ExerciseSession, ExerciseSet, Measurement
from app.services import loading_index as li
from app.services import pose_service as ps
from conftest import login

CONF = 0.9


def arm(shoulder, angle_deg, length=0.12, direction=1):
    """Elbow and wrist so that the angle at the elbow is ``angle_deg`` (wrist below/above the shoulder)."""
    half = math.radians(angle_deg) / 2
    reach = 2 * length * math.sin(half)
    wrist = (shoulder[0], shoulder[1] + direction * reach)
    mid = ((shoulder[0] + wrist[0]) / 2, (shoulder[1] + wrist[1]) / 2)
    offset = length * math.cos(half)
    elbow = (mid[0] - offset, mid[1])
    return elbow, wrist


def pushup_frame(elbow_angle, hips_drop=0.0, conf=CONF):
    shoulder = (0.40, 0.50)
    elbow, wrist = arm(shoulder, elbow_angle)
    hip = (0.65, 0.51 + hips_drop)
    ankle = (0.90, 0.52)
    kp = {"l_shoulder": shoulder, "l_elbow": elbow, "l_wrist": wrist, "l_hip": hip, "l_ankle": ankle,
          "l_knee": (0.78, 0.515), "nose": (0.33, 0.48)}
    return {name: (x, y, conf) for name, (x, y) in kp.items()}


def pullup_frame(elbow_angle, up):
    shoulder = (0.50, 0.40)
    elbow, wrist = arm(shoulder, elbow_angle, direction=-1)
    nose_y = wrist[1] - 0.03 if up else shoulder[1] - 0.06
    kp = {"l_shoulder": shoulder, "l_elbow": elbow, "l_wrist": wrist, "r_wrist": (wrist[0] + 0.1, wrist[1]),
          "nose": (0.5, nose_y)}
    return {name: (x, y, CONF) for name, (x, y) in kp.items()}


def squat_frame(knee_angle):
    hip = (0.50, 0.50)
    half = math.radians(knee_angle) / 2
    length = 0.15
    ankle = (0.50, hip[1] + 2 * length * math.sin(half))
    knee = (0.50 + length * math.cos(half), (hip[1] + ankle[1]) / 2)
    return {"l_hip": (*hip, CONF), "l_knee": (*knee, CONF), "l_ankle": (*ankle, CONF)}


def sweep(counter, frames_per_rep, angles, t0=0.0, step=0.05, make=pushup_frame):
    """Feed a sequence of angles; returns the last update and the time reached."""
    t = t0
    update = None
    for angle_value in angles:
        update = counter.update(t, make(angle_value))
        t += step
    return update, t


def rep_angles(low, high=170, steps=12):
    down = [high - (high - low) * i / steps for i in range(steps + 1)]
    return down + list(reversed(down))


def test_angle():
    assert ps.angle((0, 1, 1), (0, 0, 1), (1, 0, 1)) == pytest.approx(90)
    assert ps.angle((-1, 0, 1), (0, 0, 1), (1, 0, 1)) == pytest.approx(180)


def test_five_clean_pushups_count_five():
    counter = ps.PushUpCounter()
    t = 0.0
    for _ in range(5):
        _, t = sweep(counter, 0, rep_angles(70), t0=t)
    assert counter.reps == 5 and counter.form >= 80


def test_half_pushups_do_not_count_and_get_a_cue():
    counter = ps.PushUpCounter()
    cues = []
    t = 0.0
    for _ in range(3):
        for value in rep_angles(110):
            update = counter.update(t, pushup_frame(value))
            cues.append(update.cue)
            t += 0.05
    assert counter.reps == 0 and "Go lower." in cues


def test_sagging_hips_block_the_rep():
    counter = ps.PushUpCounter()
    cues = []
    t = 0.0
    for value in rep_angles(70):
        cues.append(counter.update(t, pushup_frame(value, hips_drop=0.12)).cue)
        t += 0.05
    assert counter.reps == 0 and "Keep your body in a straight line." in cues


def test_reps_faster_than_the_minimum_are_rejected():
    counter = ps.PushUpCounter()
    t = 0.0
    for _ in range(3):
        _, t = sweep(counter, 0, rep_angles(70, steps=3), t0=t, step=0.02)
    assert counter.reps == 1


def test_low_confidence_frames_are_ignored():
    counter = ps.PushUpCounter()
    t = 0.0
    for value in rep_angles(70):
        update = counter.update(t, pushup_frame(value, conf=0.2))
        t += 0.05
    assert counter.reps == 0 and update.cue.startswith("Step back")


def test_pullups_need_full_extension():
    counter = ps.PullUpCounter()
    t = 0.0
    for _ in range(4):
        for value in rep_angles(55, high=170):
            counter.update(t, pullup_frame(value, value < 90))
            t += 0.06
    assert counter.reps == 4
    cheat = ps.PullUpCounter()
    t = 0.0
    for _ in range(3):  # bounce between the top and half-way, never back to straight arms
        for value in rep_angles(55, high=120):
            cheat.update(t, pullup_frame(value, value < 90))
            t += 0.06
    assert cheat.reps == 1, "without returning to full extension only the first rep counts"


def test_squats():
    counter = ps.SquatCounter()
    t = 0.0
    for _ in range(6):
        _, t = sweep(counter, 0, rep_angles(85, high=175), t0=t, make=squat_frame)
    assert counter.reps == 6
    shallow = ps.SquatCounter()
    sweep(shallow, 0, rep_angles(120, high=175), make=squat_frame)
    assert shallow.reps == 0


def test_running_cadence_from_alternating_ankles():
    tracker = ps.CadenceTracker()
    fps, cadence = 15, 160
    update = None
    for frame in range(fps * 20):
        t = frame / fps
        swing = 0.04 * math.sin(2 * math.pi * (cadence / 120) * t)
        kp = {"l_ankle": (0.4, 0.8 + swing, CONF), "r_ankle": (0.6, 0.8 - swing, CONF)}
        update = tracker.update(t, kp)
    assert update.cadence == pytest.approx(cadence, rel=0.08)
    assert 50 <= tracker.steps <= 56


def test_cadence_needs_ten_frames_per_second():
    tracker = ps.CadenceTracker()
    for frame in range(60):
        t = frame / 6
        swing = 0.04 * math.sin(2 * math.pi * 1.3 * t)
        update = tracker.update(t, {"l_ankle": (0.4, 0.8 + swing, CONF), "r_ankle": (0.6, 0.8 - swing, CONF)})
    assert update.cadence is None


def test_keypoint_parsing_rejects_bad_values():
    assert ps.parse_keypoints({"nose": [0.5, 0.5, 0.9], "tail": [1, 2, 3]}) == {"nose": (0.5, 0.5, 0.9)}
    assert ps.parse_keypoints({"nose": [0.5, "x", 0.9]}) is None
    assert ps.parse_keypoints({"nose": [0.5, 0.5, 1.5]}) is None
    assert ps.parse_keypoints("nope") is None


# ── loading index ─────────────────────────────────────────

NOW = datetime(2026, 11, 14, 12)


def test_loading_index_formula():
    sets = [li.SetSummary("device_log", NOW - timedelta(days=d), duration_s=60 * 60, effort_1_10=6)
            for d in range(5)]
    result = li.compute(sets, "Mars Base")
    # 300 of 300 minutes, 5 of 5 days, MET 6 of 5 (capped), no camera sets
    assert result["score"] == 100 and result["minutes"] == 300 and result["days"] == 5


def test_rep_sets_convert_to_minutes_and_form_counts():
    pushups = li.SetSummary("pushup", NOW, reps=40, duration_s=60, form_score=60)
    assert li.active_minutes(pushups) == 2.0
    result = li.compute([pushups], "Lunar Base")
    expected = 100 * (0.40 * 2 / 240 + 0.30 * 1 / 5 + 0.20 * 3.8 / 5 + 0.10 * 60 / 80)
    assert result["score"] == round(expected)
    assert li.compute([], "Mars Base")["score"] == 0


def test_run_met_scales_with_cadence():
    slow = li.met(li.SetSummary("run", NOW, duration_s=600, cadence_spm=100))
    fast = li.met(li.SetSummary("run", NOW, duration_s=600, cadence_spm=180))
    assert slow < fast <= 8 * 1.2


# ── routes ────────────────────────────────────────────────

def test_page_shows_the_honesty_banner_and_environment_picker(client):
    login(client)
    page = client.get("/musculoskeletal").get_data(as_text=True)
    assert "A camera can't measure bone density" in page
    assert 'data-exercise="pushup"' in page
    client.post("/settings/environment", json={"environment": "Space Station"})
    page = client.get("/musculoskeletal").get_data(as_text=True)
    assert 'data-exercise="pushup"' not in page and "Harnessed treadmill" in page


def test_camera_workout_end_to_end(app, client):
    login(client)
    assert client.post("/musculoskeletal/start", json={"exercise": "pushup"}).get_json()["ok"]
    frames, t = [], 0.0
    for _ in range(5):
        for value in rep_angles(70):
            frames.append({"t": t, "kp": {k: list(v) for k, v in pushup_frame(value).items()}})
            t += 0.05
    reply = None
    for start in range(0, len(frames), 25):
        reply = client.post("/musculoskeletal/keypoints", json={"frames": frames[start:start + 25]}).get_json()
    assert reply["reps"] == 5 and reply["form"] and reply["preview"] >= 0
    results = client.post("/musculoskeletal/end", json={}).get_json()["results"]
    assert results["saved"] and results["sets"][0]["reps"] == 5 and results["xp"] == 40
    with app.app_context():
        assert ExerciseSet.query.one().reps == 5
        row = Measurement.query.filter_by(metric="loading_index").one()
        assert row.source == "cv" and row.status is not None
        assert DailyTask.query.filter_by(task_code="exercise", done=True).count() == 1


def test_device_log_only_workout(app, client):
    login(client)
    client.post("/musculoskeletal/start", json={})
    bad = client.post("/musculoskeletal/set", json={"exercise_type": "device_log", "device": "Rowing", "minutes": 30,
                                                      "effort": 6})
    assert bad.status_code == 400
    client.post("/musculoskeletal/set", json={"exercise_type": "device_log", "device": "ARED", "minutes": 45,
                                              "effort": 7})
    results = client.post("/musculoskeletal/end", json={}).get_json()["results"]
    assert results["sets"][0]["effort_1_10"] == 7
    with app.app_context():
        assert Measurement.query.filter_by(metric="loading_index").one().source == "manual"


def test_unavailable_exercise_is_refused(client):
    login(client)
    client.post("/settings/environment", json={"environment": "Space Station"})
    response = client.post("/musculoskeletal/start", json={"exercise": "pushup"})
    assert response.status_code == 400


def test_empty_workout_saves_nothing(app, client):
    login(client)
    client.post("/musculoskeletal/start", json={"exercise": "squat"})
    results = client.post("/musculoskeletal/end", json={}).get_json()["results"]
    assert results["saved"] is False
    with app.app_context():
        assert db.session.query(ExerciseSession).count() == 0


def test_server_pose_route_is_off_in_fast_mode(client):
    login(client)
    assert client.post("/musculoskeletal/frame", json={}).status_code == 409


def test_idle_days_force_needs_attention(seeded_app):
    client = seeded_app.test_client()
    login(client, "AST-1002")
    load = next(item for item in client.get("/api/summary").get_json()["metrics"] if item["key"] == "loading_index")
    assert load["status"]["key"] == "watch"
