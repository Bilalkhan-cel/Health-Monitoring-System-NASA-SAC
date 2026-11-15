"""Wearable HTTP contract (Section 10A.4 and Appendix F): batch and frame validation.

Never trust the device. Wrong *types* or a malformed batch → 400 with a field path.
Values that are well-typed but implausible (NaN, out of range) → that frame is
counted as ``rejected`` and the others are still accepted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

MAX_FRAMES = 60
MAX_BODY_BYTES = 16 * 1024
MAX_PPG = 25
BOOT_ID = re.compile(r"^[0-9a-fA-F]{1,16}$")
FLAG = re.compile(r"^[a-z0-9_]{1,24}$")
RANGES = {"hr": (30, 220), "spo2": (70, 100), "temp_c": (10, 50), "q": (0, 100)}


class BadPayload(ValueError):
    def __init__(self, path: str, message: str = "bad_payload") -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


class RejectedFrame(ValueError):
    """A well-formed frame whose values are not plausible."""


@dataclass
class Frame:
    seq: int
    up_ms: int
    finger: bool
    hr: float | None
    spo2: float | None
    hr_ok: bool
    spo2_ok: bool
    q: float
    sat: bool
    temp_c: float | None
    temp_ok: bool
    pi: float | None = None
    ir_dc: float | None = None
    ppg: list[int] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class Batch:
    v: int
    device_id: str
    boot_id: str
    sent_uptime_ms: int
    frames: list[Frame]
    fw: str = ""
    wifi_rssi: int | None = None
    dropped: int = 0


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int(data: dict, key: str, path: str, *, required: bool = True, minimum: int = 0) -> int | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise BadPayload(f"{path}{key}")
    return value


def _number(data: dict, key: str, path: str, *, nullable: bool = True) -> float | None:
    value = data.get(key)
    if value is None:
        if nullable:
            return None
        raise BadPayload(f"{path}{key}")
    if not _is_number(value):
        raise BadPayload(f"{path}{key}")
    return float(value)


def _bool(data: dict, key: str, path: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise BadPayload(f"{path}{key}")
    return value


def parse_frame(raw: object, index: int) -> Frame:
    path = f"frames[{index}]."
    if not isinstance(raw, dict):
        raise BadPayload(f"frames[{index}]")
    ppg = raw.get("ppg") or []
    if not isinstance(ppg, list) or len(ppg) > MAX_PPG or not all(_is_number(v) for v in ppg):
        raise BadPayload(f"{path}ppg")
    flags = raw.get("flags") or []
    if not isinstance(flags, list) or not all(isinstance(flag, str) and FLAG.match(flag) for flag in flags):
        raise BadPayload(f"{path}flags")
    q = _number(raw, "q", path, nullable=True)
    return Frame(
        seq=_int(raw, "seq", path), up_ms=_int(raw, "up_ms", path), finger=_bool(raw, "finger", path),
        hr=_number(raw, "hr", path), spo2=_number(raw, "spo2", path), hr_ok=_bool(raw, "hr_ok", path),
        spo2_ok=_bool(raw, "spo2_ok", path), q=0.0 if q is None else q, sat=bool(raw.get("sat", False)),
        temp_c=_number(raw, "temp_c", path), temp_ok=_bool(raw, "temp_ok", path), pi=_number(raw, "pi", path),
        ir_dc=_number(raw, "ir_dc", path), ppg=[int(v) for v in ppg], flags=list(flags)[:8],
    )


def parse_batch(payload: object) -> Batch:
    if not isinstance(payload, dict):
        raise BadPayload("$")
    if payload.get("v") != 1:
        raise BadPayload("v")
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not 1 <= len(device_id) <= 40:
        raise BadPayload("device_id")
    boot_id = payload.get("boot_id")
    if not isinstance(boot_id, str) or not BOOT_ID.match(boot_id):
        raise BadPayload("boot_id")
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames or len(frames) > MAX_FRAMES:
        raise BadPayload("frames")
    fw = payload.get("fw", "")
    if not isinstance(fw, str) or len(fw) > 20:
        raise BadPayload("fw")
    rssi = payload.get("wifi_rssi")
    if rssi is not None and (not isinstance(rssi, int) or isinstance(rssi, bool)):
        raise BadPayload("wifi_rssi")
    return Batch(
        v=1, device_id=device_id, boot_id=boot_id.lower(),
        sent_uptime_ms=_int(payload, "sent_uptime_ms", ""), fw=fw, wifi_rssi=rssi,
        dropped=_int(payload, "dropped", "", required=False) or 0,
        frames=[parse_frame(raw, index) for index, raw in enumerate(frames)],
    )


def check_values(frame: Frame) -> Frame:
    """Reject non-finite or implausible values (the frame is dropped, the batch continues)."""
    for key in ("hr", "spo2", "temp_c", "q", "pi", "ir_dc"):
        value = getattr(frame, key)
        if value is not None and (math.isnan(value) or math.isinf(value)):
            raise RejectedFrame(f"{key} is not finite")
    for key, (lo, hi) in RANGES.items():
        value = getattr(frame, key)
        if value is not None and not lo <= value <= hi:
            raise RejectedFrame(f"{key} out of range")
    if frame.up_ms > 10 ** 12:
        raise RejectedFrame("up_ms out of range")
    return frame
