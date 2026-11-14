"""DeviceGateway (Section 10A.1): wearable frames → validate → persist raw → live state →
publish → aggregate. One short transaction per ingest request.

The device never sends wall-clock time: each frame's timestamp is
``received_at − (sent_uptime_ms − up_ms)``. Frames older than ``BACKLOG_LIVE_MAX_S`` on
arrival are history only: stored and aggregated by their timestamp, never live.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import OperationalError

from ...extensions import db
from ...models import Astronaut, Device, DeviceEvent, Mission, Notification, SensorSample
from .. import measurements
from ..live import LiveRuntime
from ..stream_hub import queue_event
from ..thresholds import classify, load_rules
from .aggregator import Aggregate
from .frames import Batch, RejectedFrame, check_values, parse_batch
from .live_state import SPO2_NOTICE_TEXT
from .quality import FrameResult

log = logging.getLogger(__name__)

DEMO_DEVICE_ID = "AV-DEMO-01"
PURGE_EVERY = timedelta(hours=1)
PURGE_BATCH = 5000
CATCH_UP_EVERY_S = 60
DB_RETRIES = 2


class DatabaseBusy(Exception):
    """The database stayed locked after retries (answer 503)."""


@dataclass
class IngestResult:
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    ignored: bool = False

    def as_json(self, now: datetime, send_interval_ms: int = 1000) -> dict:
        body = {"ok": True, "server_time": now.isoformat(timespec="seconds") + "Z", "accepted": self.accepted,
                "duplicate": self.duplicate, "rejected": self.rejected,
                "cfg": {"rev": 1, "send_interval_ms": send_interval_ms}}
        if self.ignored:
            body["ignored"] = True
        return body


def _event(device: Device, kind: str, ts: datetime, detail: dict | None = None) -> None:
    db.session.add(DeviceEvent(device_pk=device.id, ts=ts, kind=kind,
                               detail_json=json.dumps(detail) if detail else None))


def store_aggregates(runtime: LiveRuntime, device: Device, aggregates: list[Aggregate],
                     resting_session: dict | None = None) -> list[str]:
    """Save closed windows through the one write path. Returns the metrics written."""
    written = []
    for agg in aggregates:
        when = agg.start + timedelta(seconds=agg.window_s)
        context = None
        source = "sensor"
        if agg.metric == "heart_rate":
            context = "resting" if resting_session else "unspecified"
        if agg.metric == "temperature_c":
            source = "derived"
        if device.device_id == DEMO_DEVICE_ID:
            source = "simulated"  # demo wearable: generated, never mixed with real readings
        gate = {"settled": agg.settled}
        if agg.metric == "heart_rate":
            gate.update(in_resting_session=bool(resting_session),
                        rest_verified=bool(resting_session and resting_session.get("rest_verified")),
                        device_key=device.device_id)
        try:
            measurements.record(
                device.astronaut_id, agg.metric, agg.value, source=source, context=context, origin="wearable",
                created_at=when, device_pk=device.id, quality=agg.quality, n_samples=agg.n_samples,
                window_s=agg.window_s, raw_value=agg.raw_value, gate_context=gate, commit=False,
                session_type="cardio" if resting_session else None,
                session_id=resting_session.get("id") if resting_session else None,
            )
            written.append(agg.metric)
        except measurements.InvalidReading:
            log.warning("Skipped an implausible %s aggregate from %s", agg.metric, device.device_id)
    return written


def _purge(runtime: LiveRuntime, now: datetime) -> int:
    """Delete raw frames older than RAW_RETENTION_DAYS in small batches."""
    cutoff = now - timedelta(days=runtime.config.raw_retention_days)
    removed = 0
    while True:
        ids = [row.id for row in db.session.query(SensorSample.id).filter(SensorSample.ts < cutoff).limit(PURGE_BATCH)]
        if not ids:
            break
        db.session.query(SensorSample).filter(SensorSample.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        removed += len(ids)
    runtime.last_purge = now
    if removed:
        log.info("Purged %d raw wearable frames older than %d days", removed, runtime.config.raw_retention_days)
    return removed


def maybe_purge(runtime: LiveRuntime, now: datetime) -> int:
    if runtime.last_purge is not None and now - runtime.last_purge < PURGE_EVERY:
        return 0
    return _purge(runtime, now)


def _notice_spo2(astronaut_id: int, when: datetime) -> None:
    key = f"spo2_wearable_low:{when.date().isoformat()}"
    if Notification.query.filter_by(astronaut_id=astronaut_id, dedupe_key=key).first():
        return
    db.session.add(Notification(astronaut_id=astronaut_id, type="attention", severity="watch",
                                title="Oxygen reading is low", message=SPO2_NOTICE_TEXT, action_url="/dashboard",
                                dedupe_key=key, created_at=when))


def _process(runtime: LiveRuntime, device: Device, batch: Batch, received_at: datetime) -> tuple[IngestResult, dict]:
    config = runtime.config
    result = IngestResult()
    astronaut_id = device.astronaut_id
    quality = runtime.device_quality(device.id, device.temp_offset_c)
    events: list[tuple[str, dict]] = []

    if device.last_boot_id and device.last_boot_id != batch.boot_id:
        quality.reset()
        runtime.live.reset(astronaut_id)
        runtime.aggregator.flush(device.id)
        measurements.get_gate().reset_run(astronaut_id, device.device_id)
        _event(device, "boot", received_at, {"boot_id": batch.boot_id, "fw": batch.fw})
        events.append(("device", {"kind": "boot"}))
    elif device.last_boot_id is None:
        _event(device, "boot", received_at, {"boot_id": batch.boot_id, "fw": batch.fw})
    was_offline = device.last_seen_at is None or \
        (received_at - device.last_seen_at).total_seconds() > config.device_offline_s

    seqs = [frame.seq for frame in batch.frames]
    existing = {row.seq for row in db.session.query(SensorSample.seq).filter(
        SensorSample.device_pk == device.id, SensorSample.boot_id == batch.boot_id, SensorSample.seq.in_(seqs))}
    seen: set[int] = set()
    newest_live: tuple[FrameResult, list[int]] | None = None
    buffered_count = 0
    rules = load_rules()["alert_confirm"]["heart_rate"]["wearable"]
    for frame in sorted(batch.frames, key=lambda item: item.seq):
        if frame.seq in existing or frame.seq in seen:
            result.duplicate += 1
            continue
        seen.add(frame.seq)
        try:
            frame = check_values(frame)
        except RejectedFrame:
            result.rejected += 1
            continue
        ts = received_at - timedelta(milliseconds=max(0, batch.sent_uptime_ms - frame.up_ms))
        buffered = (received_at - ts).total_seconds() > config.backlog_live_max_s
        processed = quality.process(frame, ts)
        db.session.add(SensorSample(
            astronaut_id=astronaut_id, device_pk=device.id, boot_id=batch.boot_id, seq=frame.seq, ts=ts,
            received_at=received_at, buffered=buffered, finger=frame.finger,
            hr=frame.hr, spo2=frame.spo2, temp_raw_c=processed.temp_raw, temp_c=processed.temp_c,
            temp_state=processed.temp_state, pi=frame.pi, quality=frame.q,
            flags_json=json.dumps(processed.flags) if processed.flags else None))
        runtime.aggregator.add(device.id, processed)
        for kind in processed.events:
            if not buffered:
                _event(device, kind, ts)
                events.append(("device", {"kind": kind}))
        for listener in runtime.listeners:
            listener(astronaut_id, processed, buffered)
        if buffered:
            buffered_count += 1
            continue
        hr_critical = processed.hr_valid and processed.hr is not None and \
            classify("heart_rate", processed.hr, "resting")["status"] == "CRITICAL"
        changes = runtime.live.update(
            astronaut_id, device.device_id, device.id, processed, received_at=received_at, rssi=batch.wifi_rssi,
            fw=batch.fw, ppg=frame.ppg, hr_critical=hr_critical, min_quality=rules["min_quality"],
            consecutive=rules["consecutive_frames"])
        if changes["spo2_low"]:
            _notice_spo2(astronaut_id, ts)
        newest_live = (processed, frame.ppg)
        result.accepted += 1
    result.accepted += buffered_count

    if buffered_count:
        _event(device, "backlog_replay", received_at, {"frames": buffered_count})
    latest = max((frame.up_ms for frame in batch.frames), default=batch.sent_uptime_ms)
    latest_ts = received_at - timedelta(milliseconds=max(0, batch.sent_uptime_ms - latest))
    session_info = runtime_session(runtime, astronaut_id)
    metrics = store_aggregates(runtime, device, runtime.aggregator.close_before(device.id, latest_ts), session_info)

    device.last_seen_at = received_at
    device.last_boot_id = batch.boot_id
    device.last_seq = max(seqs)
    device.last_rssi = batch.wifi_rssi
    device.fw_version = batch.fw or device.fw_version
    if was_offline:
        _event(device, "online", received_at)
        events.append(("device", {"kind": "online"}))
    snapshot = runtime.live.snapshot(astronaut_id, received_at, linked=True,
                                     consecutive=rules["consecutive_frames"])
    if newest_live is not None:
        processed, ppg = newest_live
        vital = {"t": processed.ts.isoformat(timespec="seconds") + "Z", "state": snapshot["state"],
                 "finger": processed.finger, "hr": snapshot["hr"], "spo2": snapshot["spo2"], "temp": snapshot["temp"],
                 "q": snapshot["q"], "notice": snapshot["notice"]}
        if ppg and processed.finger:
            vital["ppg"] = ppg
        events.append(("vital", vital))
    if metrics:
        events.append(("summary", {"metrics": sorted(set(metrics))}))
    for name, data in events:
        if name == "device":
            data = {**data, **snapshot}
        queue_event(db.session, astronaut_id, name, data)
    return result, snapshot


def runtime_session(runtime: LiveRuntime, astronaut_id: int) -> dict | None:
    """The astronaut's active resting cardio session, if any (set by the cardio module)."""
    sessions = getattr(runtime, "resting_sessions", None) or {}
    return sessions.get(astronaut_id)


def sensor_mode(device: Device) -> str:
    astronaut = db.session.get(Astronaut, device.astronaut_id)
    mission = db.session.get(Mission, astronaut.mission_id) if astronaut else None
    return mission.sensor_mode if mission else "device"


def ingest(runtime: LiveRuntime, device: Device, payload: object, received_at: datetime,
           remote_ip: str | None = None) -> IngestResult:
    """Validate and store one batch. Raises BadPayload or DatabaseBusy."""
    batch = parse_batch(payload)
    if sensor_mode(device) == "demo" and device.device_id != DEMO_DEVICE_ID:
        # Real and generated readings never mix: acknowledge, store nothing.
        return IngestResult(accepted=0, ignored=True)
    for attempt in range(DB_RETRIES + 1):
        try:
            result, _snapshot = _process(runtime, device, batch, received_at)
            device.last_ip = remote_ip
            db.session.commit()
            break
        except OperationalError as error:
            db.session.rollback()
            if "locked" not in str(error).lower() or attempt == DB_RETRIES:
                raise DatabaseBusy() from error
            time.sleep(0.05 * (attempt + 1))
    maybe_catch_up(runtime, device.astronaut_id, received_at)
    maybe_purge(runtime, received_at)
    return result


def maybe_catch_up(runtime: LiveRuntime, astronaut_id: int, now: datetime) -> None:
    astronaut = db.session.get(Astronaut, astronaut_id)
    if astronaut is None:
        return
    snapshot = runtime.live.snapshot(astronaut_id, now, linked=True)
    runtime.sim.catch_up(astronaut, now, hr_live=snapshot["hr"])


def flush_device(runtime: LiveRuntime, device: Device, *, resting_session: dict | None = None) -> list[str]:
    """Close every open window for a device (offline, session end). Does not commit."""
    metrics = store_aggregates(runtime, device, runtime.aggregator.flush(device.id), resting_session)
    if metrics:
        queue_event(db.session, device.astronaut_id, "summary", {"metrics": sorted(set(metrics))})
    return metrics
