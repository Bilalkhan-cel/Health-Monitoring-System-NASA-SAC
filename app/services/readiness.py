"""Readiness Score (Section 9.3): a wellness estimate, not a fitness-for-duty decision.

    subsystem_score = mean(points[status]) over its fresh metrics
    readiness       = sum(weight * subsystem_score) / sum(weight)   (subsystems with fresh data)
    caps            : any fresh CRITICAL -> at most 49; any fresh CAUTION -> at most 79
    fewer than 2 subsystems with fresh data -> no number

The three body-system scores shown on Today use the same formula and the same caps,
so the overall score is always the weighted mean of what the cards show.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Mapping

import yaml

from config import BASE_DIR

from .thresholds import STATUS_META, worst

INDICATORS_PATH = BASE_DIR / "config" / "indicators.yaml"
CAP_CRITICAL = 49
CAP_CAUTION = 79
MIN_SUBSYSTEMS = 2


@lru_cache(maxsize=1)
def load_indicators() -> dict:
    return yaml.safe_load(INDICATORS_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class MetricState:
    """Latest classified reading of one metric."""

    status: str | None
    age_h: float


@dataclass(frozen=True)
class SystemScore:
    score: int | None
    status: str | None


@dataclass(frozen=True)
class Readiness:
    score: int | None
    status: str | None
    subsystems: dict[str, float | None]
    systems: dict[str, SystemScore]
    fresh_subsystems: int
    lowest_subsystem: str | None = None
    worst_metric: str | None = None
    fresh_metrics: dict[str, str] = field(default_factory=dict)

    def breakdown(self) -> dict[str, object]:
        """JSON-safe breakdown stored on ``ReadinessDaily``."""
        return {
            "status": self.status,
            "subsystems": self.subsystems,
            "systems": {name: {"score": item.score, "status": item.status} for name, item in self.systems.items()},
            "worst_metric": self.worst_metric,
        }


def _capped(score: float, statuses: list[str]) -> int:
    if "CRITICAL" in statuses:
        score = min(score, CAP_CRITICAL)
    elif "CAUTION" in statuses:
        score = min(score, CAP_CAUTION)
    return round(score)


def _points(status: str) -> int:
    return int(STATUS_META[status]["points"])


def compute(states: Mapping[str, MetricState]) -> Readiness:
    """Compute readiness from the latest state of each metric."""
    indicators = load_indicators()
    weights = {name: spec["weight"] for name, spec in indicators["subsystems"].items()}
    system_of = {name: spec["system"] for name, spec in indicators["subsystems"].items()}

    fresh: dict[str, dict[str, str]] = {name: {} for name in weights}
    for metric, spec in indicators["metrics"].items():
        state = states.get(metric)
        subsystem = spec.get("subsystem")
        if not subsystem or state is None or state.status is None or state.age_h > spec["fresh_h"]:
            continue
        fresh[subsystem][metric] = state.status

    subsystem_scores: dict[str, float | None] = {}
    for name, metrics in fresh.items():
        subsystem_scores[name] = (sum(_points(s) for s in metrics.values()) / len(metrics)) if metrics else None

    systems: dict[str, SystemScore] = {}
    for system in dict.fromkeys(system_of.values()):
        members = [name for name in weights if system_of[name] == system and subsystem_scores[name] is not None]
        statuses = [status for name in members for status in fresh[name].values()]
        if not members:
            systems[system] = SystemScore(None, None)
            continue
        total = sum(weights[name] for name in members)
        raw = sum(weights[name] * subsystem_scores[name] for name in members) / total
        systems[system] = SystemScore(_capped(raw, statuses), worst(statuses))

    available = [name for name, score in subsystem_scores.items() if score is not None]
    all_statuses = [status for metrics in fresh.values() for status in metrics.values()]
    fresh_metrics = {metric: status for metrics in fresh.values() for metric, status in metrics.items()}
    if len(available) < MIN_SUBSYSTEMS:
        return Readiness(None, None, subsystem_scores, systems, len(available), fresh_metrics=fresh_metrics)

    total = sum(weights[name] for name in available)
    raw = sum(weights[name] * subsystem_scores[name] for name in available) / total
    lowest = min(available, key=lambda name: subsystem_scores[name])
    order = list(indicators["metrics"])
    worst_metric = max(fresh[lowest], key=lambda m: (_rank(fresh[lowest][m]), -order.index(m)))
    return Readiness(_capped(raw, all_statuses), worst(all_statuses), subsystem_scores, systems,
                     len(available), lowest, worst_metric, fresh_metrics)


def _rank(status: str) -> int:
    return list(STATUS_META).index(status)
