"""DemoWearableSource (Section 10A.11): an in-process virtual ESP32 for SENSOR_MODE=demo.

It produces the same frames as the firmware once per second and feeds the same
DeviceGateway, so the UI, SSE, aggregation and alerts behave exactly as with hardware.
Readings are stored with ``source = simulated``. It only runs when a person switched the
mode to Demo data; nothing ever switches the mode automatically.
"""

from __future__ import annotations

from datetime import datetime

from ...models import Device
from .device_gateway import DEMO_DEVICE_ID, ingest
from .synthetic import SyntheticWearable


class DemoWearableSource:
    def __init__(self) -> None:
        self.wearable = SyntheticWearable(profile="demo", seed=11, hr_base=74, boot_id="de0001")
        self.last_tick: datetime | None = None

    def step(self, runtime, now: datetime) -> bool:
        """Send at most one frame per second. Returns True when a frame was sent."""
        if self.last_tick is not None and (now - self.last_tick).total_seconds() < 0.95:
            return False
        device = Device.query.filter_by(device_id=DEMO_DEVICE_ID).first()
        if device is None:
            return False
        self.last_tick = now
        frame = self.wearable.frame()
        batch = self.wearable.batch([frame], device_id=DEMO_DEVICE_ID)
        ingest(runtime, device, batch, now, remote_ip="in-process")
        return True
