"""OpenHome (Dr. NOVA) connection: voice WebSocket upstream, one-shot text call, health check, mock.

Protocol (verified against the official ``openhome-client`` 0.1.1 source, 2026-11):
* ``wss://app.openhome.com/websocket/voice-stream/{api_key}/{agent_id}`` with a browser-like
  User-Agent and a single ``Origin: https://app.openhome.com`` header;
* client → server: ``{"type": "audio", "data": <base64 PCM16 16 kHz mono>}``,
  ``{"type": "transcribed", "data": "<text>"}``, ``{"type": "text", "data": "bot-speaking" |
  "bot-speak-end" | "interrupt-event"}``, ``{"type": "ack", "data": "audio-received"}``,
  ``{"type": "ping", "data": null}``;
* server → client: ``{"type": "message", "data": {role, content, live, final}}``,
  ``{"type": "text", "data": "audio-init" | "audio-end"}``, ``{"type": "audio", "data": <mp3>}``,
  ``{"type": "error-event", "data": {message}}``.

The API key lives in the URL, so every log line is redacted. All OpenHome code lives here
and in ``openhome_ability/``.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from config import Config

log = logging.getLogger(__name__)

WS_ORIGIN = "https://app.openhome.com"
API_BASE = "https://app.openhome.com"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
TEXT_TIMEOUT_S = 25
AUDIO_END_GRACE_S = 1.5  # after the reply, wait this long for audio-end before hanging up
HEALTH_TTL_S = 60
_health_cache: dict[str, tuple[float, str]] = {}

Frame = dict
OnFrame = Callable[[Frame], None]


def redact(text: str, config: Config) -> str:
    for secret in (config.openhome_api_key, config.openhome_bridge_token):
        if secret:
            text = text.replace(secret, "***")
    return text


def voice_url(config: Config) -> str:
    return config.openhome_voice_ws.format(api_key=config.openhome_api_key, agent_id=config.openhome_agent_id)


def mode(config: Config) -> str:
    """mock | live | needs_keys | off."""
    if not config.openhome_enabled:
        return "off"
    if config.openhome_mock:
        return "mock"
    return "live" if config.openhome_configured else "needs_keys"


class Upstream:
    """Base class for a voice conversation (real OpenHome or the local mock)."""

    kind = "base"

    def __init__(self, on_frame: OnFrame) -> None:
        self.on_frame = on_frame
        self.closed = threading.Event()

    def send(self, frame: Frame) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.closed.set()


class OpenHomeUpstream(Upstream):
    """Real OpenHome voice stream over websocket-client, one reader thread."""

    kind = "openhome"

    def __init__(self, config: Config, on_frame: OnFrame, on_close: Callable[[int], None] | None = None) -> None:
        super().__init__(on_frame)
        from websocket import WebSocketApp

        self.config = config
        self._lock = threading.Lock()
        self._opened = threading.Event()
        self._on_close = on_close
        self.app = WebSocketApp(
            voice_url(config), header=[f"User-Agent: {USER_AGENT}"],
            on_open=lambda _ws: self._opened.set(),
            on_message=self._message, on_error=self._error, on_close=self._closed,
        )
        self.thread = threading.Thread(target=self.app.run_forever,
                                       kwargs={"ping_interval": 0, "origin": WS_ORIGIN, "suppress_origin": False},
                                       daemon=True, name="openhome-upstream")
        self.thread.start()

    def wait_open(self, timeout: float = 8) -> bool:
        return self._opened.wait(timeout)

    def _message(self, _ws, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            return
        self.on_frame(frame)

    def _error(self, _ws, error: Exception) -> None:
        log.warning("OpenHome voice stream error: %s", redact(str(error), self.config))

    def _closed(self, _ws, code, _msg) -> None:
        self.closed.set()
        if self._on_close:
            self._on_close(code or 1000)

    def send(self, frame: Frame) -> None:
        sock = self.app.sock
        if sock is None or not sock.connected:
            return
        with self._lock:
            self.app.send(json.dumps(frame))

    def close(self) -> None:
        super().close()
        try:
            self.app.close()
        except Exception:  # noqa: BLE001
            pass


class MockUpstream(Upstream):
    """Local stand-in for OpenHome (OPENHOME_MOCK=true): captions only, no audio.

    Typed text (``transcribed``) is answered at once. Microphone audio is buffered and,
    after a pause in speech, transcribed with the local Whisper model when it is installed.
    Answers come from the same engine chain as the text chat (fallback LLM, then rules).
    """

    kind = "mock"
    SILENCE_RMS = 0.012
    SILENCE_FRAMES = 6  # ~1.2 s of quiet audio after speech

    def __init__(self, on_frame: OnFrame, answer: Callable[[str], str], greeting: str,
                 transcribe: Callable[[bytes], str | None] | None = None) -> None:
        super().__init__(on_frame)
        self.answer = answer
        self.transcribe = transcribe
        self.pcm = bytearray()
        self.quiet = 0
        self.heard_speech = False
        self.speaking = False
        threading.Thread(target=self._say, args=(greeting,), daemon=True).start()

    def _say(self, text: str) -> None:
        self.speaking = True
        words = text.split()
        for index in range(4, len(words), 6):
            if self.closed.is_set():
                return
            self.on_frame({"type": "message", "data": {"role": "assistant", "content": " ".join(words[:index]),
                                                       "live": True, "final": False}})
            time.sleep(0.05)
        self.on_frame({"type": "message", "data": {"role": "assistant", "content": text, "live": False,
                                                   "final": True}})
        self.speaking = False

    def _user(self, text: str) -> None:
        self.on_frame({"type": "message", "data": {"role": "user", "content": text, "live": False, "final": True}})
        threading.Thread(target=lambda: self._say(self.answer(text)), daemon=True).start()

    def send(self, frame: Frame) -> None:
        kind, data = frame.get("type"), frame.get("data")
        if kind == "transcribed" and isinstance(data, str) and data.strip():
            self._user(data.strip())
        elif kind == "audio" and isinstance(data, str) and self.transcribe is not None and not self.speaking:
            try:
                chunk = base64.b64decode(data)
            except ValueError:
                return
            self.pcm.extend(chunk)
            if _rms(chunk) > self.SILENCE_RMS:
                self.heard_speech, self.quiet = True, 0
            else:
                self.quiet += 1
            if self.heard_speech and self.quiet >= self.SILENCE_FRAMES:
                audio, self.pcm = bytes(self.pcm), bytearray()
                self.heard_speech, self.quiet = False, 0
                threading.Thread(target=self._from_audio, args=(audio,), daemon=True).start()
            elif len(self.pcm) > 16000 * 2 * 30:
                self.pcm = self.pcm[-16000 * 2 * 10:]

    def _from_audio(self, audio: bytes) -> None:
        text = self.transcribe(audio) if self.transcribe else None
        if text:
            self._user(text)


def _rms(chunk: bytes) -> float:
    import array

    samples = array.array("h")
    samples.frombytes(chunk[: len(chunk) // 2 * 2])
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768


def text_call(config: Config, message: str, timeout: float = TEXT_TIMEOUT_S) -> str | None:
    """One text turn with the real Dr. NOVA agent over the voice stream (text-only mode).

    Waits for the agent's greeting, sends the message as ``transcribed`` text, and returns
    the next final assistant message. None on any failure (the caller falls back).
    """
    if mode(config) != "live":
        return None
    state = {"sent": False, "reply": None, "speaking": False}
    done = threading.Event()
    spoken = threading.Event()  # the agent finished its utterance (audio-end), so closing is clean

    def on_frame(frame: Frame) -> None:
        kind, data = frame.get("type"), frame.get("data")
        if kind == "text" and data == "audio-init":
            state["speaking"] = True
            spoken.clear()
            upstream.send({"type": "text", "data": "bot-speaking"})
        elif kind == "text" and data == "audio-end":
            state["speaking"] = False
            upstream.send({"type": "text", "data": "bot-speak-end"})
            spoken.set()
        elif kind == "audio":
            upstream.send({"type": "ack", "data": "audio-received"})
        elif kind == "error-event":
            done.set()
        elif kind == "message" and isinstance(data, dict) and data.get("role") == "assistant" and data.get("final"):
            if not state["sent"]:
                state["sent"] = True
                upstream.send({"type": "transcribed", "data": message})
            else:
                state["reply"] = data.get("content")
                done.set()

    try:
        upstream = OpenHomeUpstream(config, on_frame, on_close=lambda _code: done.set())
        if not upstream.wait_open(8):
            upstream.close()
            return None
        def nudge() -> None:
            if not state["sent"]:
                state["sent"] = True
                upstream.send({"type": "transcribed", "data": message})
        threading.Timer(8, nudge).start()
        done.wait(timeout)
        if state["reply"] is not None and state["speaking"]:
            spoken.wait(AUDIO_END_GRACE_S)  # let the agent finish instead of hanging up mid-sentence
        upstream.close()
    except Exception as error:  # noqa: BLE001 (any failure falls back)
        log.warning("OpenHome text call failed: %s", redact(str(error), config))
        return None
    return state["reply"]


def health(config: Config) -> str:
    """live | mock | needs_keys | off | unreachable (cached for a minute)."""
    current = mode(config)
    if current != "live":
        return current
    cached = _health_cache.get(config.openhome_api_key)
    if cached and time.monotonic() - cached[0] < HEALTH_TTL_S:
        return cached[1]
    import requests

    try:
        response = requests.post(f"{API_BASE}/api/sdk/verify_apikey", json={"api_key": config.openhome_api_key},
                                 timeout=5)
        status = "live" if response.status_code == 200 else "needs_keys"
    except requests.RequestException:
        status = "unreachable"
    _health_cache[config.openhome_api_key] = (time.monotonic(), status)
    return status


@dataclass
class EngineReply:
    text: str
    engine: str  # OPENHOME | FALLBACK LLM | OFFLINE RULES
