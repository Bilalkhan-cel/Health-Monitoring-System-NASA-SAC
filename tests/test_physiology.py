"""PhysiologyModel: determinism, bounds, change rates, pulse pressure, meals, coupling to heart rate."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.sensors.physiology import PhysiologyModel, smooth_noise, stable_seed
from app.services.thresholds import classify, classify_bp

START = datetime(2026, 11, 1)


def model(name: str = "AST-1001") -> PhysiologyModel:
    return PhysiologyModel(stable_seed(name, "ARES-SURFACE-01"))


def test_same_time_same_values():
    a, b = model(), model()
    moment = START + timedelta(hours=7, minutes=13)
    assert a.sample(moment) == b.sample(moment)
    assert model("AST-1002").sample(moment) != a.sample(moment)


def test_noise_stays_in_range():
    seed = stable_seed("x")
    assert all(-1 <= smooth_noise(seed, t * 37.0, 480) <= 1 for t in range(2000))


def test_seven_days_stay_in_bounds_and_change_slowly():
    m = model()
    previous = None
    for minute in range(7 * 24 * 60):
        sample = m.sample(START + timedelta(minutes=minute))
        assert 98 <= sample["systolic"] <= 135 and 62 <= sample["diastolic"] <= 86
        assert 32 <= sample["systolic"] - sample["diastolic"] <= 55
        assert 72 <= sample["glucose"] <= 145 and 11 <= sample["respiration"] <= 19
        assert classify_bp(sample["systolic"], sample["diastolic"])["status"] in ("NOMINAL", "STABLE")
        assert classify("respiration", sample["respiration"], "resting")["status"] in ("NOMINAL", "STABLE")
        if previous:
            assert abs(sample["systolic"] - previous["systolic"]) <= 6
            assert abs(sample["glucose"] - previous["glucose"]) <= 8
            assert abs(sample["respiration"] - previous["respiration"]) <= 1.5
        previous = sample


def test_glucose_peaks_about_45_minutes_after_a_meal():
    m = PhysiologyModel(stable_seed("meal"), meal_times=("12:30",))
    day = START + timedelta(days=2)
    readings = {minute: m.sample(day + timedelta(hours=11, minutes=minute))["glucose"] for minute in range(0, 240)}
    peak = max(readings, key=readings.get)
    assert 105 <= peak <= 150  # minutes after 11:00: meal at 12:30 +/- 15 min, peak about 45 min later
    assert m.glucose_context(day + timedelta(hours=6)) == "fasting"
    assert m.glucose_context(day + timedelta(hours=14, minutes=30)) in ("post_meal", "random")


def test_live_heart_rate_raises_generated_blood_pressure():
    m = model()
    moments = [START + timedelta(minutes=31 * i) for i in range(200)]
    calm = sum(m.sample(t, hr_live=60)["systolic"] for t in moments)
    racing = sum(m.sample(t, hr_live=110)["systolic"] for t in moments)
    assert racing > calm
