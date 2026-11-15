"""The live runtime: one object per app holding the in-memory parts of the wearable path."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from flask import Flask, current_app

from config import Config

from .sensors.aggregator import Aggregator
from .sensors.live_state import LiveState
from .sensors.quality import DeviceQuality
from .sensors.simulated import SimRecorder
from .stream_hub import StreamHub, install_session_hooks

FrameListener = Callable[[int, object, bool], None]  # (astronaut_id, FrameResult, buffered)


@dataclass
class LiveRuntime:
    config: Config
    hub: StreamHub = field(default_factory=StreamHub)
    quality: dict[int, DeviceQuality] = field(default_factory=dict)
    listeners: list[FrameListener] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_purge: datetime | None = None
    token_rejections: dict[str, datetime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.live = LiveState(self.config)
        self.aggregator = Aggregator(self.config.agg_window_s, self.config.agg_min_valid)
        self.sim = SimRecorder(self.config)

    def device_quality(self, device_pk: int, temp_offset_c: float) -> DeviceQuality:
        with self.lock:
            state = self.quality.get(device_pk)
            if state is None:
                state = self.quality[device_pk] = DeviceQuality(self.config, temp_offset_c)
            state.temp_offset_c = temp_offset_c
            return state


def init_live(app: Flask, config: Config) -> LiveRuntime:
    runtime = LiveRuntime(config)
    app.extensions["live"] = runtime
    install_session_hooks()
    return runtime


def get_runtime() -> LiveRuntime:
    return current_app.extensions["live"]
