"""Readiness Score (Section 9.3)."""

from __future__ import annotations

from app.services.readiness import MetricState, compute


def state(status: str, age_h: float = 1.0) -> MetricState:
    return MetricState(status, age_h)


def test_needs_two_fresh_subsystems():
    assert compute({"heart_rate": state("NOMINAL")}).score is None
    result = compute({"heart_rate": state("NOMINAL"), "sleep_hours": state("NOMINAL")})
    assert result.score == 100 and result.fresh_subsystems == 2


def test_all_good_is_one_hundred():
    states = {key: state("NOMINAL") for key in ("heart_rate", "spo2", "wellbeing", "sleep_hours", "loading_index")}
    result = compute(states)
    assert result.score == 100 and result.status == "NOMINAL"


def test_weighted_mean_of_subsystems():
    states = {"heart_rate": state("STABLE"), "wellbeing": state("NOMINAL"), "sleep_hours": state("NOMINAL"),
              "loading_index": state("NOMINAL")}
    # cardio 85 (30 %), bones 100 (25 %), mental 100 (25 %), sleep 100 (20 %)
    assert compute(states).score == round((30 * 85 + 70 * 100) / 100)


def test_caution_caps_at_79_and_critical_at_49():
    good = {key: state("NOMINAL") for key in ("spo2", "wellbeing", "sleep_hours", "loading_index")}
    assert compute({**good, "heart_rate": state("CAUTION")}).score <= 79
    critical = compute({**good, "heart_rate": state("CRITICAL")})
    assert critical.score <= 49 and critical.status == "CRITICAL"


def test_stale_metrics_do_not_count():
    states = {"heart_rate": state("CRITICAL", age_h=49), "wellbeing": state("NOMINAL"),
              "sleep_hours": state("NOMINAL", age_h=37), "loading_index": state("NOMINAL", age_h=24 * 6)}
    result = compute(states)
    assert result.score == 100
    assert "heart_rate" not in result.fresh_metrics and "sleep_hours" not in result.fresh_metrics


def test_unclassified_metrics_are_ignored():
    result = compute({"heart_rate": MetricState(None, 1), "wellbeing": state("NOMINAL")})
    assert result.score is None


def test_system_scores_use_the_same_caps():
    states = {"heart_rate": state("CAUTION"), "spo2": state("NOMINAL"), "wellbeing": state("STABLE"),
              "sleep_hours": state("CAUTION"), "loading_index": state("NOMINAL")}
    result = compute(states)
    assert result.systems["heart"].score <= 79 and result.systems["heart"].status == "CAUTION"
    assert result.systems["mind"].status == "CAUTION"
    assert result.systems["bones"].score == 100
    assert result.lowest_subsystem == "sleep" and result.worst_metric == "sleep_hours"
    assert set(result.breakdown()) == {"status", "subsystems", "systems", "worst_metric"}
