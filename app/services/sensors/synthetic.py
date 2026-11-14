"""Synthetic wearable frames shaped exactly like the ESP32 firmware's (Appendix F).

Used by the in-process demo wearable (``SENSOR_MODE=demo``), by
``scripts/device_emulator.py`` and by the tests, so all three exercise the same contract.
Deterministic for a given seed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

PPG_POINTS = 25


def ppg_wave(t: float, bpm: float, scale: float = 70.0) -> list[int]:
    """One second of an IR pulse wave (25 samples), mean removed, like the firmware sends."""
    points = []
    for i in range(PPG_POINTS):
        phase = ((t + i / PPG_POINTS) * bpm / 60.0) % 1.0
        systolic = math.exp(-((phase - 0.18) ** 2) / 0.006)
        dicrotic = 0.35 * math.exp(-((phase - 0.48) ** 2) / 0.01)
        points.append(systolic + dicrotic)
    mean = sum(points) / len(points)
    return [int(round((p - mean) * scale)) for p in points]


@dataclass
class SyntheticWearable:
    """A virtual ESP32: call ``frame()`` once per second."""

    profile: str = "normal"
    seed: int = 7
    hr_base: float = 72.0
    spo2_base: float = 98.0
    temp_target: float = 35.4
    boot_id: str = "a1b2c3d4"
    seq: int = 0
    up_ms: int = 5_000
    temp_raw: float = 35.4
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        if self.profile == "probe_warming":
            self.temp_raw = 31.0
        if self.profile == "probe_ambient":
            self.temp_raw = 23.5

    def _finger(self) -> bool:
        if self.profile == "no_finger":
            return False
        if self.profile == "finger_flap":
            return (self.seq // 6) % 2 == 0
        if self.profile == "demo":
            return self.seq % 180 < 174  # a short finger-off gap every 3 minutes exercises the states
        return True

    def frame(self) -> dict:
        t = self.up_ms / 1000.0
        finger = self._finger()
        hr = self.hr_base + 3 * math.sin(t / 23.0) + self.rng.uniform(-1.2, 1.2)
        if self.profile == "spike" and self.seq % 30 == 15:
            hr += 60
        spo2 = self.spo2_base + self.rng.choice([-1, 0, 0, 0, 1]) * 0.5
        q = 90 + self.rng.uniform(-6, 6)
        if self.profile == "weak_signal":
            q = 30 + self.rng.uniform(-8, 8)
        if self.profile == "flatline":
            hr, spo2, q = 74.0, 97.0, 85.0
        if self.profile == "probe_warming":
            self.temp_raw = min(self.temp_target, self.temp_raw + 0.03)
        elif self.profile not in ("probe_ambient",):
            self.temp_raw += (self.temp_target - self.temp_raw) * 0.1 + self.rng.uniform(-0.01, 0.01)
        temp_ok = self.profile != "probe_missing"
        frame = {
            "seq": self.seq, "up_ms": self.up_ms, "finger": finger,
            "hr": round(hr) if finger else None, "spo2": round(spo2) if finger else None,
            "hr_ok": finger, "spo2_ok": finger,
            "pi": round(1.8 + self.rng.uniform(-0.3, 0.3), 2) if finger else 0.0,
            "ir_dc": int(91000 + self.rng.uniform(-900, 900)) if finger else int(4200 + self.rng.uniform(-50, 50)),
            "q": round(q) if finger else 0, "sat": False,
            "temp_c": round(self.temp_raw, 2) if temp_ok else None, "temp_ok": temp_ok,
            "flags": [],
        }
        if finger:
            frame["ppg"] = ppg_wave(t, hr)
        if self.profile == "flatline":
            frame["ppg"] = [0] * PPG_POINTS
            frame["ir_dc"], frame["pi"] = 91000, 1.8
        self.seq += 1
        self.up_ms += 1000
        return frame

    def batch(self, frames: list[dict], device_id: str = "AV-ESP32-01", dropped: int = 0) -> dict:
        return {"v": 1, "device_id": device_id, "fw": "1.0.0", "boot_id": self.boot_id,
                "sent_uptime_ms": frames[-1]["up_ms"] if frames else self.up_ms, "wifi_rssi": -57,
                "dropped": dropped, "frames": frames}

    def restart(self, boot_id: str) -> None:
        self.boot_id, self.seq, self.up_ms = boot_id, 0, 3_000
