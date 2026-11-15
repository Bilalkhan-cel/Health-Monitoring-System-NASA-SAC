"""Aggregator (Section 10A.8): 60 s tumbling windows aligned to the minute.

A window produces a Measurement per metric only when it holds at least
``AGG_MIN_VALID`` valid frames: value = median, quality = mean q. Heart rate and SpO₂
are ``sensor`` readings; temperature is ``derived`` and only from settled frames.
Windows close when a later frame arrives, when the device goes offline and when a
cardio session ends.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from .quality import FrameResult


@dataclass
class Window:
    start: datetime
    hr: list[float] = field(default_factory=list)
    spo2: list[float] = field(default_factory=list)
    temp: list[float] = field(default_factory=list)
    temp_raw: list[float] = field(default_factory=list)
    q: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class Aggregate:
    metric: str
    value: float
    start: datetime
    window_s: int
    n_samples: int
    quality: float
    raw_value: float | None = None
    settled: bool = True


class Aggregator:
    def __init__(self, window_s: int = 60, min_valid: int = 20) -> None:
        self.window_s = window_s
        self.min_valid = min_valid
        self._lock = threading.Lock()
        self._open: dict[int, dict[datetime, Window]] = {}

    def window_start(self, ts: datetime) -> datetime:
        """Align to the minute (or to multiples of ``window_s`` since midnight, UTC)."""
        midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds = int((ts - midnight).total_seconds())
        return midnight + timedelta(seconds=seconds - seconds % self.window_s)

    def add(self, device_pk: int, result: FrameResult) -> None:
        start = self.window_start(result.ts)
        with self._lock:
            window = self._open.setdefault(device_pk, {}).setdefault(start, Window(start))
            if result.hr_valid and result.hr is not None:
                window.hr.append(result.hr)
                window.q.append(result.q)
            if result.confirmed_hr is not None:
                window.hr.append(result.confirmed_hr)
            if result.spo2_valid and result.spo2 is not None:
                window.spo2.append(result.spo2)
            if result.confirmed_spo2 is not None:
                window.spo2.append(result.confirmed_spo2)
            if result.temp_state == "settled" and result.temp_c is not None:
                window.temp.append(result.temp_c)
                window.temp_raw.append(result.temp_raw)

    def close_before(self, device_pk: int, latest: datetime) -> list[Aggregate]:
        """Close every window that ended before ``latest``."""
        with self._lock:
            windows = self._open.get(device_pk, {})
            done = [start for start in windows if start + timedelta(seconds=self.window_s) <= latest]
            closed = [windows.pop(start) for start in sorted(done)]
        return [aggregate for window in closed for aggregate in self._summarise(window)]

    def flush(self, device_pk: int) -> list[Aggregate]:
        """Close every open window (device offline, session end)."""
        with self._lock:
            windows = self._open.pop(device_pk, {})
        return [aggregate for start in sorted(windows) for aggregate in self._summarise(windows[start])]

    def open_count(self, device_pk: int) -> int:
        with self._lock:
            return len(self._open.get(device_pk, {}))

    def _summarise(self, window: Window) -> list[Aggregate]:
        quality = sum(window.q) / len(window.q) if window.q else 0.0
        out = []
        if len(window.hr) >= self.min_valid:
            out.append(Aggregate("heart_rate", round(median(window.hr), 1), window.start, self.window_s,
                                 len(window.hr), round(quality, 1)))
        if len(window.spo2) >= self.min_valid:
            out.append(Aggregate("spo2", round(median(window.spo2), 1), window.start, self.window_s,
                                 len(window.spo2), round(quality, 1)))
        if len(window.temp) >= self.min_valid:
            out.append(Aggregate("temperature_c", round(median(window.temp), 2), window.start, self.window_s,
                                 len(window.temp), round(quality, 1), raw_value=round(median(window.temp_raw), 2)))
        return out
