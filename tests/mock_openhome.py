"""A standalone OpenHome voice-stream mock for contract tests.

    python tests/mock_openhome.py            serve on ws://127.0.0.1:8765/websocket/voice-stream/<key>/<agent>

Speaks the same frames as app.openhome.com: a greeting on connect; for a `transcribed`
phrase it sends audio-init, one audio frame, audio-end, then live and final `message`
captions. It records every frame the client sent so tests can check the handshake.
"""

from __future__ import annotations

import base64
import json
import threading
import time

from flask import Flask
from flask_sock import Sock
from werkzeug.serving import make_server

RECEIVED: list[dict] = []
FAKE_MP3 = base64.b64encode(b"ID3" + b"\0" * 64).decode()


def create_app() -> Flask:
    app = Flask(__name__)
    sock = Sock(app)

    @sock.route("/websocket/voice-stream/<api_key>/<agent_id>")
    def voice(ws, api_key, agent_id):  # noqa: ARG001
        if api_key != "test-key":
            ws.close(1008, "bad key")
            return
        ws.send(json.dumps({"type": "message", "data": {"role": "assistant", "content": "Hello, I'm Dr. Nova.",
                                                         "live": False, "final": True}}))
        while True:
            raw = ws.receive()
            if raw is None:
                continue
            frame = json.loads(raw)
            RECEIVED.append(frame)
            if frame.get("type") == "transcribed":
                text = frame["data"]
                ws.send(json.dumps({"type": "message", "data": {"role": "user", "content": text, "live": False,
                                                                 "final": True}}))
                ws.send(json.dumps({"type": "text", "data": "audio-init"}))
                ws.send(json.dumps({"type": "audio", "data": FAKE_MP3}))
                ws.send(json.dumps({"type": "message", "data": {"role": "assistant", "content": "You said",
                                                                 "live": True, "final": False}}))
                ws.send(json.dumps({"type": "message", "data": {"role": "assistant", "content": f"You said: {text}",
                                                                 "live": False, "final": True}}))
                ws.send(json.dumps({"type": "text", "data": "audio-end"}))

    return app


class MockServer:
    def __init__(self, port: int = 0) -> None:
        self.server = make_server("127.0.0.1", port, create_app(), threaded=True)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "MockServer":
        RECEIVED.clear()
        self.thread.start()
        time.sleep(0.1)
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()

    @property
    def url_template(self) -> str:
        return f"ws://127.0.0.1:{self.port}/websocket/voice-stream/{{api_key}}/{{agent_id}}"


if __name__ == "__main__":
    with MockServer(8765) as server:
        print(f"Mock OpenHome on {server.url_template}")  # noqa: T201 (dev tool output)
        server.thread.join()
