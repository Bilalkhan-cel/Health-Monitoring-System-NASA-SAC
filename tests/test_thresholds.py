"""thresholds.yaml, classify() and the personal-baseline layer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import thresholds as t

RULES = t.load_rules()
TABLES = [name for name, table in RULES.items() if isinstance(table, dict) and "nominal" in table]
SWEEP = {
    "heart_rate": (0, 260), "systolic": (40, 260), "diastolic": (20, 160), "glucose_fasting": (10, 600),
    "glucose_post_meal": (10, 600), "temperature_c": (30, 45), "spo2": (0, 100), "respiration": (0, 60),
    "sleep_hours": (0, 24), "wellbeing": (0, 100), "loading_index": (0, 100),
}


def matches(table: dict, value: float) -> list[str]:
    found = []
    for status in t.STATUS_ORDER:
        for interval in table.get(status.lower(), []):
            if t._in(interval, value):
                found.append(status)
    return found


def test_every_table_is_swept():
    assert sorted(TABLES) == sorted(SWEEP)


@pytest.mark.parametrize("name", TABLES)
def test_every_value_maps_to_exactly_one_interval(name):
    table = RULES[name]
    lo, hi = SWEEP[name]
    steps = int(round((hi - lo) * 10))
    for step in range(steps + 1):
        value = round(lo + step / 10, 1)
        assert len(matches(table, value)) == 1, f"{name} {value} -> {matches(table, value)}"


@pytest.mark.parametrize("name", TABLES)
def test_intervals_are_lower_inclusive_upper_exclusive(name):
    table = RULES[name]
    for status in t.STATUS_ORDER:
        for lo, hi in table.get(status.lower(), []):
            if lo is not None:
                assert matches(table, lo) == [status]
            if hi is not None:
                assert matches(table, hi) != [status] or hi is None


@pytest.mark.parametrize("value, expected", [
    (59.9, "STABLE"), (60, "NOMINAL"), (90.9, "NOMINAL"), (91, "STABLE"), (101, "CAUTION"), (129.9, "CAUTION"),
    (130, "CRITICAL"), (39.9, "CRITICAL"), (40, "CAUTION"),
])
def test_heart_rate_boundaries(value, expected):
    assert t.classify("heart_rate", value, "resting")["status"] == expected


def test_status_words_and_verdicts():
    high = t.classify("heart_rate", 104, "resting")
    assert (high["label"], high["verdict"], high["key"], high["color"]) == ("Needs attention", "A bit high",
                                                                             "watch", "--watch")
    assert t.classify("heart_rate", 72, "resting")["label"] == "Good"
    assert t.classify("heart_rate", 95, "resting")["label"] == "Okay"
    assert t.classify("heart_rate", 150, "resting")["label"] == "Get help now"
    assert t.classify("spo2", 92)["verdict"] == "A bit low"
    assert t.classify("heart_rate", 104)["threshold_version"] == RULES["version"]


def test_max_status_caps_sleep_wellbeing_and_loading():
    assert t.classify("sleep_hours", 0.5)["status"] == "CAUTION"
    assert t.classify("wellbeing", 0)["status"] == "CAUTION"
    assert t.classify("loading_index", 0)["status"] == "CAUTION"


def test_wearable_spo2_never_exceeds_caution_but_other_sources_can_be_critical():
    for tenth in range(0, 1001):
        assert t.rank(t.classify("spo2", tenth / 10, origin="wearable")["status"]) <= t.rank("CAUTION")
    assert t.classify("spo2", 85)["status"] == "CRITICAL"
    assert t.classify("spo2", 85, origin="ble")["status"] == "CRITICAL"
    capped = t.classify("spo2", 80, origin="wearable")
    assert capped["message"] == "Re-measure to confirm."


def test_wearable_low_temperature_is_capped_but_high_is_not():
    assert t.classify("temperature_c", 34.0, origin="wearable")["status"] == "CAUTION"
    assert t.classify("temperature_c", 34.0)["status"] == "CRITICAL"
    assert t.classify("temperature_c", 39.5, origin="wearable")["status"] == "CRITICAL"


def test_blood_pressure_is_the_worst_of_both_numbers():
    assert t.classify_bp(118, 76)["status"] == "NOMINAL"
    assert t.classify_bp(118, 85)["status"] == "CAUTION"
    assert t.classify_bp(186, 118)["status"] == "CRITICAL"
    assert t.classify_bp(125, 120)["status"] == "CRITICAL"


def test_glucose_context_picks_the_table():
    assert t.classify("glucose", 105, "fasting")["status"] == "STABLE"
    assert t.classify("glucose", 105, "post_meal")["status"] == "NOMINAL"
    assert t.classify("glucose", 105, "random")["status"] == "NOMINAL"


def test_resting_vitals_are_only_classified_at_rest():
    assert t.classify_measurement("heart_rate", 150, context="unspecified") is None
    assert t.classify_measurement("heart_rate", 150, context="active") is None
    assert t.classify_measurement("heart_rate", 150, context="resting")["status"] == "CRITICAL"
    assert t.classify_measurement("blood_pressure", 186, 118, context=None) is None
    assert t.classify_measurement("spo2", 97)["status"] == "NOMINAL"
    assert t.classify_measurement("hydration_ml", 500) is None


def test_non_finite_values_are_rejected():
    with pytest.raises(ValueError):
        t.classify("heart_rate", float("nan"))
    with pytest.raises(ValueError):
        t.classify("heart_rate", float("inf"))


def test_worst_and_cap_helpers():
    assert t.worst(["NOMINAL", None, "CAUTION", "STABLE"]) == "CAUTION"
    assert t.worst([None]) is None
    assert t.cap("CRITICAL", "CAUTION") == "CAUTION"
    assert t.cap("STABLE", "CAUTION") == "STABLE"


# ── baseline ──────────────────────────────────────────────

TODAY = date(2026, 11, 8)


def series(values: list[float], end_offset: int = 3) -> dict[date, float]:
    end = TODAY - timedelta(days=end_offset)
    return {end - timedelta(days=i): value for i, value in enumerate(reversed(values))}


def test_baseline_window_excludes_the_last_three_days():
    start, end = t.baseline_window(TODAY)
    assert end == TODAY - timedelta(days=3) and (end - start).days == 13


def test_baseline_needs_seven_days():
    baseline, n = t.compute_baseline(series([72] * 6), TODAY)
    assert baseline is None and n == 6
    baseline, n = t.compute_baseline(series([72] * 7), TODAY)
    assert baseline is not None and baseline.median == 72 and n == 7


def test_recent_days_do_not_enter_the_baseline():
    data = series([70] * 10)
    data.update({TODAY - timedelta(days=d): 120 for d in range(3)})
    baseline, _ = t.compute_baseline(data, TODAY)
    assert baseline.median == 70


def test_zero_mad_uses_the_floor():
    baseline, _ = t.compute_baseline(series([72] * 10), TODAY)
    params = t.baseline_params("heart_rate")
    assert baseline.mad == 0
    assert t.robust_z(75, baseline, params["floor"]) == 1.0
    assert not t.is_notable(78, baseline, params)  # z = 2 but change 6 < min_change 8
    assert t.is_notable(104, baseline, params)


def test_escalation_needs_two_days_on_the_same_side():
    baseline, _ = t.compute_baseline(series([72] * 10), TODAY)
    params = t.baseline_params("heart_rate")
    assert t.should_escalate([84, 86], baseline, params)
    assert not t.should_escalate([84], baseline, params)
    assert not t.should_escalate([84, 60], baseline, params)
    assert not t.should_escalate([84, 74], baseline, params)


def test_baseline_never_creates_critical_or_changes_caution():
    assert t.apply_baseline("NOMINAL", True) == "CAUTION"
    assert t.apply_baseline("STABLE", True) == "CAUTION"
    assert t.apply_baseline("CAUTION", True) == "CAUTION"
    assert t.apply_baseline("CRITICAL", True) == "CRITICAL"
    assert t.apply_baseline("NOMINAL", False) == "NOMINAL"
