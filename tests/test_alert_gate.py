"""AlertGate: one test per row of the Section 9.7 table, plus "a gate never raises"."""

from __future__ import annotations

import copy
import itertools

import pytest

from app.services.alert_gate import AlertGate, GateInput
from app.services.thresholds import STATUS_ORDER, load_rules, rank


def gate(**overrides) -> AlertGate:
    rules = copy.deepcopy(load_rules())
    for path, value in overrides.items():
        node = rules["alert_confirm"]
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return AlertGate(rules=rules)


def reading(**kwargs) -> GateInput:
    base = {"astronaut_id": 1, "metric": "heart_rate", "status": "CRITICAL", "origin": "wearable", "ts": 0.0,
            "quality": 90.0, "in_resting_session": True, "rest_verified": True}
    base.update(kwargs)
    return GateInput(**base)


def hr_run(g: AlertGate, frames: int, start: float = 0.0, **kwargs) -> list[str]:
    return [g.evaluate(reading(ts=start + i, **kwargs)).status for i in range(frames)]


def test_symptom_is_immediate():
    result = AlertGate().evaluate(reading(metric="spo2", origin="manual", symptom=True))
    assert result.status == "CRITICAL"


def test_manual_spo2_needs_a_confirming_entry():
    g = AlertGate()
    first = g.evaluate(reading(metric="spo2", origin="manual", ts=0))
    assert (first.status, first.confirmed, first.needs_remeasure) == ("CAUTION", False, True)
    too_soon = g.evaluate(reading(metric="spo2", origin="manual", ts=30))
    assert too_soon.status == "CAUTION"
    confirmed = g.evaluate(reading(metric="spo2", origin="manual", ts=61))
    assert confirmed.status == "CRITICAL"


def test_manual_spo2_first_entry_expires_after_the_window():
    g = AlertGate()
    g.evaluate(reading(metric="spo2", origin="manual", ts=0))
    late = g.evaluate(reading(metric="spo2", origin="manual", ts=11 * 60))
    assert late.status == "CAUTION" and late.needs_remeasure
    assert g.spo2_pending(1, 11 * 60 + 1)


def test_manual_spo2_normal_second_entry_clears_the_prompt():
    g = AlertGate()
    g.evaluate(reading(metric="spo2", origin="manual", ts=0))
    assert g.evaluate(reading(metric="spo2", origin="manual", status="NOMINAL", ts=70)).status == "NOMINAL"
    assert not g.spo2_pending(1, 71)
    assert g.evaluate(reading(metric="spo2", origin="manual", ts=140)).status == "CAUTION"


def test_symptom_tick_confirms_manual_spo2_at_once():
    g = AlertGate()
    g.evaluate(reading(metric="spo2", origin="manual", ts=0))
    assert g.evaluate(reading(metric="spo2", origin="manual", ts=5, symptom=True)).status == "CRITICAL"


def test_manual_other_metrics_are_immediate():
    assert AlertGate().evaluate(reading(metric="blood_pressure", origin="manual")).status == "CRITICAL"


@pytest.mark.parametrize("metric", ["spo2", "glucose"])
def test_ble_fast_path_metrics_alert_on_the_first_reading(metric):
    assert AlertGate().evaluate(reading(metric=metric, origin="ble")).status == "CRITICAL"


def test_single_wearable_heart_rate_frame_is_needs_attention():
    assert AlertGate().evaluate(reading()).status == "CAUTION"


def test_wearable_heart_rate_needs_ten_sustained_frames():
    statuses = hr_run(AlertGate(), 10)
    assert statuses[:9] == ["CAUTION"] * 9 and statuses[9] == "CRITICAL"


@pytest.mark.parametrize("kwargs", [{"in_resting_session": False}, {"rest_verified": False}])
def test_heart_rate_run_outside_a_verified_session_stays_caution(kwargs):
    assert set(hr_run(AlertGate(), 15, **kwargs)) == {"CAUTION"}


def test_low_quality_or_invalid_frame_resets_the_run():
    g = AlertGate()
    hr_run(g, 9)
    assert g.evaluate(reading(ts=9, quality=40)).status == "CAUTION"
    assert hr_run(g, 9, start=10) == ["CAUTION"] * 9
    g.evaluate(reading(ts=19, valid=False))
    assert hr_run(g, 9, start=20)[-1] == "CAUTION"


def test_explicit_reset_clears_the_run():
    g = AlertGate()
    hr_run(g, 9)
    g.reset_run(1)
    assert hr_run(g, 1, start=9) == ["CAUTION"]


def test_span_requirement_is_read_from_the_yaml():
    g = gate(**{"heart_rate.wearable.min_span_s": 30})
    assert set(hr_run(g, 20)) == {"CAUTION"}
    g = gate(**{"heart_rate.wearable.consecutive_frames": 3, "heart_rate.wearable.min_span_s": 3})
    assert hr_run(g, 3)[-1] == "CRITICAL"


def test_wearable_spo2_is_never_critical():
    assert AlertGate().evaluate(reading(metric="spo2")).status == "CAUTION"


def test_wearable_temperature_needs_two_settled_aggregates():
    g = AlertGate()
    assert g.evaluate(reading(metric="temperature_c", settled=False)).status == "CAUTION"
    assert g.evaluate(reading(metric="temperature_c", ts=60)).status == "CAUTION"
    assert g.evaluate(reading(metric="temperature_c", ts=120)).status == "CRITICAL"


def test_generated_values_need_two_readings_five_seconds_apart():
    g = AlertGate()
    assert g.evaluate(reading(metric="blood_pressure", origin="generated", ts=0)).status == "CAUTION"
    assert g.evaluate(reading(metric="blood_pressure", origin="generated", ts=2)).status == "CAUTION"
    assert g.evaluate(reading(metric="blood_pressure", origin="generated", ts=6)).status == "CRITICAL"


def test_a_normal_generated_reading_resets_the_count():
    g = AlertGate()
    g.evaluate(reading(metric="blood_pressure", origin="generated", ts=0))
    g.evaluate(reading(metric="blood_pressure", origin="generated", status="NOMINAL", ts=6))
    assert g.evaluate(reading(metric="blood_pressure", origin="generated", ts=12)).status == "CAUTION"


def test_scenario_writes_are_direct():
    assert AlertGate().evaluate(reading(metric="blood_pressure", origin="scenario")).status == "CRITICAL"


def test_gate_never_raises_a_status():
    origins = ["manual", "wearable", "generated", "ble", "symptom", "scenario"]
    metrics = ["heart_rate", "spo2", "temperature_c", "blood_pressure", "glucose"]
    for origin, metric, status in itertools.product(origins, metrics, STATUS_ORDER):
        g = AlertGate()
        for ts in range(0, 40, 6):
            result = g.evaluate(reading(metric=metric, origin=origin, status=status, ts=ts))
            assert rank(result.status) <= rank(status), (origin, metric, status, result)
