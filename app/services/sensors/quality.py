"""QualityGate (Section 10A.5) and the body-temperature state machine (Section 10A.6).

One ``DeviceQuality`` per device keeps the little history the rules need: the finger
state, the last valid values for the jump filter, a flatline counter and 120 s of raw
probe readings. ``process`` turns a raw frame into a ``FrameResult``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from config import Config

from .frames import Frame

JUMP_HR = 25
JUMP_HR_CONFIRM = 10
JUMP_SPO2 = 6
JUMP_SPO2_CONFIRM = 3
JUMP_WINDOW_S = 3
FLATLINE_FRAMES = 15
TEMP_WINDOW_S = 120
TEMP_MIN_SPAN_S = 90


@dataclass
class FrameResult:
    ts: datetime
    finger: bool
    state: str  # no_finger | settling | poor_signal | ok
    hr: float | None = None
    spo2: float | None = None
    hr_valid: bool = False
    spo2_valid: bool = False
    q: float = 0
    temp_state: str = "missing"  # missing | ambient | warming | settled
    temp_raw: float | None = None
    temp_c: float | None = None
    flags: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    confirmed_hr: float | None = None  # a suspect value that the next frame confirmed
    confirmed_spo2: float | None = None


@dataclass
class _Suspect:
    value: float
    ts: datetime


@dataclass
class DeviceQuality:
    config: Config
    temp_offset_c: float
    finger: bool | None = None
    finger_on_at: datetime | None = None
    last_hr: tuple[float, datetime] | None = None
    last_spo2: tuple[float, datetime] | None = None
    suspect_hr: _Suspect | None = None
    suspect_spo2: _Suspect | None = None
    same_count: int = 0
    last_signature: tuple | None = None
    stuck: bool = False
    temps: deque = field(default_factory=lambda: deque(maxlen=400))
    temp_seen: bool | None = None

    def reset(self) -> None:
        """New boot: forget everything about the previous run."""
        self.finger = None
        self.finger_on_at = None
        self.last_hr = self.last_spo2 = None
        self.suspect_hr = self.suspect_spo2 = None
        self.same_count, self.last_signature, self.stuck = 0, None, False
        self.temps.clear()
        self.temp_seen = None

    # ── pulse ─────────────────────────────────────────────
    def _jump(self, kind: str, value: float, ts: datetime) -> tuple[bool, float | None]:
        """Apply the jump filter. Returns (accept_now, confirmed_suspect_value)."""
        threshold, confirm = (JUMP_HR, JUMP_HR_CONFIRM) if kind == "hr" else (JUMP_SPO2, JUMP_SPO2_CONFIRM)
        last: tuple[float, datetime] | None = getattr(self, f"last_{kind}")
        suspect: _Suspect | None = getattr(self, f"suspect_{kind}")
        if suspect is not None:
            setattr(self, f"suspect_{kind}", None)
            if abs(value - suspect.value) <= confirm and (ts - suspect.ts).total_seconds() <= JUMP_WINDOW_S:
                setattr(self, f"last_{kind}", (value, ts))
                return True, suspect.value
        if last is not None and (ts - last[1]).total_seconds() <= JUMP_WINDOW_S and abs(value - last[0]) > threshold:
            setattr(self, f"suspect_{kind}", _Suspect(value, ts))
            return False, None
        setattr(self, f"last_{kind}", (value, ts))
        return True, None

    def _flatline(self, frame: Frame) -> bool:
        # ir_dc and pi are part of the signature: a live optical sensor never repeats them exactly, while
        # a smoothed integer heart rate easily stays the same for 15 s when no ppg is sent.
        signature = (frame.hr, frame.spo2, tuple(frame.ppg), frame.ir_dc, frame.pi)
        if frame.finger and signature == self.last_signature and frame.hr is not None:
            self.same_count += 1
        else:
            self.same_count = 1
            self.stuck = False
        self.last_signature = signature
        return self.same_count >= FLATLINE_FRAMES

    # ── temperature ───────────────────────────────────────
    def _temperature(self, frame: Frame, ts: datetime, result: FrameResult) -> None:
        if not frame.temp_ok or frame.temp_c is None:
            result.temp_state = "missing"
            if self.temp_seen is not False:
                result.events.append("probe_missing")
            self.temp_seen = False
            self.temps.clear()
            return
        if self.temp_seen is False:
            result.events.append("probe_ok")
        self.temp_seen = True
        raw = frame.temp_c
        self.temps.append((ts, raw))
        while self.temps and (ts - self.temps[0][0]).total_seconds() > TEMP_WINDOW_S:
            self.temps.popleft()
        result.temp_raw = raw
        if raw < self.config.temp_contact_min_c:
            result.temp_state = "ambient"
            return
        span = (ts - self.temps[0][0]).total_seconds()
        slope = temperature_slope(self.temps)
        settled = (span >= TEMP_MIN_SPAN_S and raw >= self.config.temp_settle_min_raw_c
                   and slope is not None and abs(slope) <= self.config.temp_settle_slope_c_per_min)
        result.temp_state = "settled" if settled else "warming"
        if settled:
            result.temp_c = round(raw + self.temp_offset_c, 2)

    # ── main ──────────────────────────────────────────────
    def process(self, frame: Frame, ts: datetime) -> FrameResult:
        result = FrameResult(ts=ts, finger=frame.finger, state="ok", q=frame.q, flags=list(frame.flags))
        self._temperature(frame, ts, result)

        if not frame.finger:
            if self.finger:
                result.events.append("finger_off")
            self.finger, self.finger_on_at = False, None
            self.last_hr = self.last_spo2 = None
            self.suspect_hr = self.suspect_spo2 = None
            self.same_count, self.last_signature = 0, None
            result.state = "no_finger"
            return result
        if not self.finger:
            result.events.append("finger_on")
            self.finger_on_at = ts
        self.finger = True

        result.hr, result.spo2 = frame.hr, frame.spo2
        if self._flatline(frame):
            if not self.stuck:
                result.events.append("sensor_error")
            self.stuck = True
            result.flags.append("stuck")
            result.state = "poor_signal"
            return result
        if self.finger_on_at and (ts - self.finger_on_at).total_seconds() < self.config.finger_settle_s:
            result.state = "settling"
            return result

        good = frame.q >= self.config.min_signal_quality and not frame.sat
        if good and frame.hr_ok and frame.hr is not None:
            accept, confirmed = self._jump("hr", frame.hr, ts)
            result.hr_valid, result.confirmed_hr = accept, confirmed
            if not accept:
                result.flags.append("suspect_hr")
        if good and frame.spo2_ok and frame.spo2 is not None:
            accept, confirmed = self._jump("spo2", frame.spo2, ts)
            result.spo2_valid, result.confirmed_spo2 = accept, confirmed
            if not accept:
                result.flags.append("suspect_spo2")
        if not (result.hr_valid or result.spo2_valid):
            result.state = "poor_signal"
        return result


def temperature_slope(samples) -> float | None:
    """Least-squares slope of the raw probe readings in °C per minute."""
    if len(samples) < 3:
        return None
    t0 = samples[0][0]
    xs = [(ts - t0).total_seconds() / 60 for ts, _ in samples]
    ys = [value for _, value in samples]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
