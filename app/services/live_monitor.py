"""LiveMonitor: a small background thread (no scheduler dependency) that, once a second,

* notices a wearable that stopped sending (device offline event, closes its windows),
* drives the demo wearable while the sensor mode is Demo data,
* purges old raw frames at most once an hour.

Tests call ``tick`` directly instead of starting the thread.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from flask import Flask

from ..extensions import db
from ..models import Device, DeviceEvent, Mission, utcnow
from .live import get_runtime
from .sensors.demo_wearable import DemoWearableSource
from .sensors.device_gateway import DEMO_DEVICE_ID, flush_device, maybe_purge
from .stream_hub import queue_event

log = logging.getLogger(__name__)


def tick(now: datetime) -> dict:
    """One pass. Must run inside an app context."""
    runtime = get_runtime()
    report = {"offline": 0, "demo_frame": False}
    for astronaut_id in runtime.live.offline_candidates(now):
        for device in Device.query.filter_by(astronaut_id=astronaut_id).all():
            if device.last_seen_at is None:
                continue
            flush_device(runtime, device)
            db.session.add(DeviceEvent(device_pk=device.id, ts=now, kind="offline"))
        snapshot = runtime.live.snapshot(astronaut_id, now, linked=True)
        queue_event(db.session, astronaut_id, "device", {"kind": "offline", **snapshot})
        report["offline"] += 1
    db.session.commit()

    mission = Mission.query.first()
    if mission is not None and mission.sensor_mode == "demo":
        demo = getattr(runtime, "demo_source", None)
        if demo is None:
            demo = runtime.demo_source = DemoWearableSource()
        report["demo_frame"] = demo.step(runtime, now)
    maybe_purge(runtime, now)
    return report


class LiveMonitor(threading.Thread):
    def __init__(self, app: Flask, interval_s: float = 1.0) -> None:
        super().__init__(name="astrovital-live-monitor", daemon=True)
        self.app = app
        self.interval_s = interval_s
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            try:
                with self.app.app_context():
                    tick(utcnow())
                    db.session.remove()
            except Exception:  # noqa: BLE001 (the monitor must never die; log and continue)
                log.exception("Live monitor pass failed")

    def stop(self) -> None:
        self._stop_event.set()


def is_demo_device(device: Device) -> bool:
    return device.device_id == DEMO_DEVICE_ID
