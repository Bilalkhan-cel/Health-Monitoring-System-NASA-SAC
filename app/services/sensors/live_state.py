"""LiveState (Section 10A.7): the freshest valid wearable values per astronaut, in memory.

A value older than ``LIVE_STALE_S`` is returned as ``None``, never repeated. Backlog
frames (older than ``BACKLOG_LIVE_MAX_S`` when they arrive) never reach this class.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from config import Config

from .quality import FrameResult

LOW_SPO2 = 94
SPO2_NOTICE_TEXT = ("Oxygen reading is low. Hold still and re-measure. If you feel short of breath, tick the symptom "
                    "box or tell your crew medical officer.")
HR_NOTICE_TEXT = ("Heart rate reads outside the resting range. If you have been active, that is normal. Rest for "
                  "5 minutes and re-check.")


@dataclass
class _Value:
    value: float
    ts: datetime


@dataclass
class AstronautLive:
    device_id: str | None = None
    device_pk: int | None = None
    last_seen: datetime | None = None
    rssi: int | None = None
    fw: str | None = None
    boot_id: str | None = None
    finger: bool | None = None
    frame_state: str | None = None
    frame_ts: datetime | None = None
    q: float | None = None
    hr: _Value | None = None
    spo2: _Value | None = None
    last_hr: _Value | None = None
    temp_state: str = "missing"
    temp: _Value | None = None
    ppg: list[int] = field(default_factory=list)
    low_spo2_run: int = 0
    hr_critical_run: int = 0
    offline_announced: bool = False


class LiveState:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._by_astronaut: dict[int, AstronautLive] = {}

    def entry(self, astronaut_id: int) -> AstronautLive:
        with self._lock:
            return self._by_astronaut.setdefault(astronaut_id, AstronautLive())

    def reset(self, astronaut_id: int) -> None:
        with self._lock:
            self._by_astronaut[astronaut_id] = AstronautLive()

    def update(self, astronaut_id: int, device_id: str, device_pk: int, result: FrameResult, *,
               received_at: datetime, rssi: int | None, fw: str | None, ppg: list[int],
               hr_critical: bool, min_quality: float, consecutive: int) -> dict:
        """Apply one live frame. Returns which notices changed (for events)."""
        entry = self.entry(astronaut_id)
        with self._lock:
            entry.device_id, entry.device_pk = device_id, device_pk
            entry.last_seen, entry.rssi, entry.fw = received_at, rssi, fw
            entry.offline_announced = False
            entry.finger, entry.frame_state, entry.frame_ts, entry.q = result.finger, result.state, result.ts, result.q
            entry.ppg = ppg if result.finger else []
            if result.hr_valid and result.hr is not None:
                entry.hr = entry.last_hr = _Value(result.hr, result.ts)
            elif not result.finger:
                entry.hr = None
            if result.spo2_valid and result.spo2 is not None:
                entry.spo2 = _Value(result.spo2, result.ts)
                entry.low_spo2_run = entry.low_spo2_run + 1 if result.spo2 < LOW_SPO2 else 0
            elif not result.finger:
                entry.spo2 = None
                entry.low_spo2_run = 0
            if not result.finger:
                entry.hr_critical_run = 0
            elif result.hr_valid and hr_critical and result.q >= min_quality:
                entry.hr_critical_run += 1
            elif result.hr_valid or result.state == "poor_signal":
                entry.hr_critical_run = 0
            entry.temp_state = result.temp_state
            if result.temp_state == "settled" and result.temp_c is not None:
                entry.temp = _Value(result.temp_c, result.ts)
            elif result.temp_state in ("missing", "ambient"):
                entry.temp = None
            return {"spo2_low": entry.low_spo2_run == 5, "hr_run": entry.hr_critical_run == consecutive}

    def _fresh(self, value: _Value | None, now: datetime) -> float | None:
        if value is None or (now - value.ts).total_seconds() > self.config.live_stale_s:
            return None
        return value.value

    def snapshot(self, astronaut_id: int, now: datetime, *, linked: bool, consecutive: int = 10) -> dict:
        """What the browser sees. No value is ever older than LIVE_STALE_S."""
        entry = self.entry(astronaut_id)
        with self._lock:
            age = (now - entry.last_seen).total_seconds() if entry.last_seen else None
            online = age is not None and age <= self.config.device_offline_s
            if not linked:
                state = "no_device"
            elif not online:
                state = "device_offline"
            elif entry.finger is False:
                state = "no_finger"
            elif entry.frame_state in ("settling", "poor_signal"):
                state = entry.frame_state
            else:
                state = "ok" if entry.finger else "no_finger"
            hr = self._fresh(entry.hr, now) if online else None
            spo2 = self._fresh(entry.spo2, now) if online else None
            temp = self._fresh(entry.temp, now) if online else None
            notice = None
            if online and entry.low_spo2_run >= 5 and spo2 is not None:
                notice = {"kind": "spo2_low", "status": "watch", "text": SPO2_NOTICE_TEXT}
            elif online and entry.hr_critical_run >= consecutive and hr is not None:
                notice = {"kind": "hr_range", "status": "watch", "text": HR_NOTICE_TEXT}
            last = None
            if not online and entry.last_hr is not None:
                last = {"hr": round(entry.last_hr.value), "age_s": round((now - entry.last_hr.ts).total_seconds())}
            return {
                "state": state,
                "device": {"linked": linked, "online": online, "last_seen_age_s": round(age, 1) if age is not None else None,
                           "rssi": entry.rssi, "fw": entry.fw},
                "finger": bool(entry.finger) if online else False,
                "hr": round(hr) if hr is not None else None,
                "spo2": round(spo2) if spo2 is not None else None,
                "temp": {"state": entry.temp_state if online else "missing",
                         "value_c": round(temp, 1) if temp is not None else None},
                "q": round(entry.q) if entry.q is not None and online else None,
                "notice": notice,
                "last": last,
            }

    def offline_candidates(self, now: datetime) -> list[int]:
        """Astronauts whose device just went quiet (each reported once)."""
        found = []
        with self._lock:
            for astronaut_id, entry in self._by_astronaut.items():
                if entry.last_seen is None or entry.offline_announced:
                    continue
                if (now - entry.last_seen).total_seconds() > self.config.device_offline_s:
                    entry.offline_announced = True
                    entry.hr_critical_run = entry.low_spo2_run = 0
                    found.append(astronaut_id)
        return found
