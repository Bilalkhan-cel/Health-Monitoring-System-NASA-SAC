"""Status classification and the personal-baseline layer.

IMPORTANT: every range in ``config/thresholds.yaml`` is an **educational prototype
range pending clinical validation**. Sources: AHA resting heart rate 60-100; AHA/ACC
2017 blood-pressure categories (crisis at 180 systolic or 120 diastolic); ADA Standards
of Care for glucose (the 100-110 split is a prototype UI subdivision); clinical
convention for temperature, SpO2 and respiration; AASM/NSF for sleep; prototype scales
for the two scores. Nothing here is medical advice.

``classify`` is a pure function of the value. Anything that needs time or history
(consecutive frames, confirmation, resting sessions) lives in ``alert_gate.AlertGate``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Iterable, Mapping, Sequence

import yaml

from config import BASE_DIR

THRESHOLDS_PATH = BASE_DIR / "config" / "thresholds.yaml"

STATUS_ORDER: tuple[str, ...] = ("NOMINAL", "STABLE", "CAUTION", "CRITICAL")
STATUS_META: dict[str, dict[str, object]] = {
    "NOMINAL": {"key": "good", "color": "--good", "label": "Good", "icon": "circle-check",
                "points": 100, "message": "Keep it up."},
    "STABLE": {"key": "okay", "color": "--okay", "label": "Okay", "icon": "circle-dot",
               "points": 85, "message": "Nothing to do."},
    "CAUTION": {"key": "watch", "color": "--watch", "label": "Needs attention", "icon": "triangle-alert",
                "points": 55, "message": "Do this today."},
    "CRITICAL": {"key": "alert", "color": "--alert", "label": "Get help now", "icon": "octagon-alert",
                 "points": 20, "message": "Tell your crew medical officer now."},
}
REST_CONTEXT = "resting"
BASELINE_WINDOW_DAYS = 14
BASELINE_EXCLUDE_DAYS = 3
BASELINE_MIN_DAYS = 7


@lru_cache(maxsize=4)
def load_rules(path: Path = THRESHOLDS_PATH) -> dict:
    """Read thresholds.yaml once."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def rank(status: str | None) -> int:
    """Severity rank; ``None`` (not classified) ranks below everything."""
    return STATUS_ORDER.index(status) if status in STATUS_ORDER else -1


def worst(statuses: Iterable[str | None]) -> str | None:
    """Worst-of ordering: CRITICAL > CAUTION > STABLE > NOMINAL."""
    ranked = [status for status in statuses if status in STATUS_ORDER]
    return max(ranked, key=rank) if ranked else None


def cap(status: str, ceiling: str | None) -> str:
    """Lower ``status`` to ``ceiling`` when it is worse."""
    return ceiling if ceiling and rank(status) > rank(ceiling) else status


def table_name(indicator: str, context: str | None = None) -> str:
    """Map an indicator (and glucose context) to its table in thresholds.yaml."""
    if indicator == "glucose":
        return "glucose_fasting" if context == "fasting" else "glucose_post_meal"
    return indicator


def requires_rest(indicator: str, rules: Mapping | None = None) -> bool:
    rules = rules or load_rules()
    if indicator == "blood_pressure":
        return True
    return bool(rules.get(indicator, {}).get("requires_rest"))


def is_classifiable(indicator: str, context: str | None, rules: Mapping | None = None) -> bool:
    """Resting vitals are only classified when measured at rest (Section 10A.1)."""
    if indicator == "hydration_ml":
        return False
    return context == REST_CONTEXT or not requires_rest(indicator, rules)


def _in(interval: Sequence[float | None], value: float) -> bool:
    lo, hi = interval
    return (lo is None or value >= lo) and (hi is None or value < hi)


def _raw_status(table: Mapping, value: float) -> str:
    for status in STATUS_ORDER:
        if any(_in(interval, value) for interval in table.get(status.lower(), [])):
            return status
    raise ValueError(f"value {value} matches no interval")


def _direction(table: Mapping, value: float) -> str | None:
    lows = [interval[0] for interval in table["nominal"] if interval[0] is not None]
    highs = [interval[1] for interval in table["nominal"] if interval[1] is not None]
    if lows and value < min(lows):
        return "low"
    if highs and value >= max(highs):
        return "high"
    return None


def describe(status: str, direction: str | None = None, *, capped: bool = False) -> dict[str, object]:
    """UI facts for a status: colour token, word, icon and tone."""
    meta = STATUS_META[status]
    verdict = meta["label"]
    if status == "CAUTION" and direction in ("high", "low"):
        verdict = f"A bit {direction}"
    message = "Re-measure to confirm." if capped else meta["message"]
    return {"status": status, "key": meta["key"], "color": meta["color"], "label": meta["label"],
            "verdict": verdict, "icon": meta["icon"], "message": message, "direction": direction}


def classify(indicator: str, value: float, context: str | None = None, origin: str | None = None,
             rules: Mapping | None = None) -> dict[str, object]:
    """Classify one value. Returns status, colour, label, icon, message and threshold version."""
    rules = rules or load_rules()
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("value must be a finite number")
    table = rules[table_name(indicator, context)]
    raw = _raw_status(table, value)
    direction = _direction(table, value)
    status = cap(raw, table.get("max_status"))
    if origin:
        status = cap(status, (table.get("max_status_by_origin") or {}).get(origin))
        # A skin or under-arm probe cannot establish hypothermia (Section 10A.6).
        if origin == "wearable" and indicator == "temperature_c" and direction == "low":
            status = cap(status, "CAUTION")
    result = describe(status, direction, capped=status != raw)
    result["threshold_version"] = rules["version"]
    return result


def classify_bp(systolic: float, diastolic: float, rules: Mapping | None = None) -> dict[str, object]:
    """Blood pressure status is the worst of systolic and diastolic."""
    parts = [classify("systolic", systolic, rules=rules), classify("diastolic", diastolic, rules=rules)]
    chosen = max(parts, key=lambda part: rank(part["status"]))
    return dict(chosen)


def classify_measurement(metric: str, value: float, value2: float | None = None, context: str | None = None,
                         origin: str | None = None, rules: Mapping | None = None) -> dict[str, object] | None:
    """Classify a stored metric, or return ``None`` when it must not be classified."""
    if not is_classifiable(metric, context, rules):
        return None
    if metric == "blood_pressure":
        return classify_bp(value, value2 if value2 is not None else 70.0, rules)
    return classify(metric, value, context, origin, rules)


# ── personal baseline (Section 9.2a) ──────────────────────

@dataclass(frozen=True)
class Baseline:
    """A person's usual value for one metric."""

    median: float
    mad: float
    n: int
    start: date
    end: date


def baseline_window(today: date) -> tuple[date, date]:
    """The 14 days ending 3 days ago (so a developing trend does not shift the baseline)."""
    end = today - timedelta(days=BASELINE_EXCLUDE_DAYS)
    return end - timedelta(days=BASELINE_WINDOW_DAYS - 1), end


def compute_baseline(daily: Mapping[date, float], today: date) -> tuple[Baseline | None, int]:
    """Return ``(baseline, days_available)``; the baseline is ``None`` until 7 days exist."""
    start, end = baseline_window(today)
    values = [value for day, value in daily.items() if start <= day <= end]
    if len(values) < BASELINE_MIN_DAYS:
        return None, len(values)
    centre = median(values)
    mad = median(abs(value - centre) for value in values)
    return Baseline(centre, mad, len(values), start, end), len(values)


def baseline_params(metric: str, context: str | None = None, rules: Mapping | None = None) -> dict | None:
    rules = rules or load_rules()
    key = "systolic" if metric == "blood_pressure" else table_name(metric, context)
    return (rules.get("baseline") or {}).get(key)


def robust_z(value: float, baseline: Baseline, floor: float) -> float:
    """z = (x - median) / max(1.4826 * MAD, floor)."""
    return (value - baseline.median) / max(1.4826 * baseline.mad, floor)


def is_notable(value: float, baseline: Baseline, params: Mapping) -> bool:
    """Annotate when |z| >= 2 and the change is at least ``min_change``."""
    z = robust_z(value, baseline, params["floor"])
    return abs(z) >= 2 and abs(value - baseline.median) >= params["min_change"]


def should_escalate(recent_daily: Sequence[float], baseline: Baseline, params: Mapping) -> bool:
    """True when the last two daily values both sit at |z| >= 3 in the same direction."""
    if len(recent_daily) < 2:
        return False
    z_values = [robust_z(value, baseline, params["floor"]) for value in recent_daily[-2:]]
    same_side = all(z >= 3 for z in z_values) or all(z <= -3 for z in z_values)
    return same_side


def apply_baseline(status: str, escalate: bool) -> str:
    """Baseline logic can only lift NOMINAL or STABLE to CAUTION. It never creates CRITICAL."""
    if escalate and status in ("NOMINAL", "STABLE"):
        return "CAUTION"
    return status
