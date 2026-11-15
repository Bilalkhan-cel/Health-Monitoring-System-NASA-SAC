"""Appendix D, the 6-minute judge demo, run end to end through the test client.

The wearable steps use the real emulator over the real ingest route (no hardware). Each
step asserts what the presenter says on stage, so a broken demo fails the build.
"""

from __future__ import annotations

import re

from conftest import build_app, load_script, login, make_values

emulator_module = load_script("device_emulator")
TOKEN = "test-device-token-0123456789"
LAN = {"Host": "127.0.0.1:5000"}


class ClientSession:
    """Lets the real emulator talk to the Flask test client."""

    def __init__(self, client):
        self.client = client

    def post(self, url, data, headers, timeout):  # noqa: ARG002
        path = url.split("://", 1)[-1]
        response = self.client.post(path[path.index("/"):], data=data, headers={**headers, **LAN})

        class Wrapped:
            status_code = response.status_code
            ok = response.status_code < 400

            @staticmethod
            def json():
                return response.get_json()

        return Wrapped()


def emulate(app, profile: str, seconds: int) -> list[tuple[int, dict]]:
    emu = emulator_module.Emulator("http://127.0.0.1:5000", TOKEN, "AV-ESP32-01", profile, fast=True,
                                   session=ClientSession(app.test_client()), quiet=True)
    return emu.run(seconds)


def test_appendix_d_demo_script(tmp_path):
    app = build_app(make_values(tmp_path / "instance", DEMO_MODE="true"), seed=True)
    anonymous = app.test_client()

    # 0:00 Landing: live Earth + ISS, three checks, twin, Dr. NOVA, "22 minutes away".
    landing = anonymous.get("/").get_data(as_text=True)
    for text in ("data-hero-canvas", "Three quick checks.", "data-demo-twin", "Dr. NOVA", "22 minutes away."):
        assert text in landing, text

    # 0:50 Login with AST-1001; a wrong ID is rejected.
    wrong = anonymous.post("/login", data={"astro_id": "AST-9999"})
    assert wrong.status_code in (200, 400, 401) and "Location" not in wrong.headers
    crew = app.test_client()
    login(crew)

    # 1:10 Today + live strip. The disclosure lives in Settings → About.
    today = crew.get("/dashboard").get_data(as_text=True)
    assert "Your body" in today
    assert crew.get("/api/live").get_json()["state"] in ("no_device", "device_offline")
    log = emulate(app, "normal", 30)
    assert all(status == 200 for status, _ in log)
    live = crew.get("/api/live").get_json()
    assert live["device"]["online"] and live["finger"] is True
    emulate(app, "no_finger", 3)
    lifted = crew.get("/api/live").get_json()
    assert lifted["hr"] is None and lifted["spo2"] is None, "lifting the finger clears the numbers"
    about = crew.get("/settings").get_data(as_text=True)
    assert "are generated for demonstration because no sensor for them is attached" in about

    # 2:00 Heart · 2:40 Bones & muscle · 3:20 Mind: every check opens.
    for path, text in (("/cardio", "Heart"), ("/musculoskeletal", "Bones"), ("/mental", "really?")):
        page = crew.get(path)
        assert page.status_code == 200 and text in page.get_data(as_text=True), path

    # 4:30 Dr. NOVA cites real data, then the Critical BP scenario escalates with the comms delay.
    reply = crew.post("/doctor/chat", json={"message": "Dr. Nova, how am I doing?"}).get_json()
    assert reply["ok"] and reply["reply"]
    assert crew.post("/settings/demo/critical_bp", json={}).get_json()["ok"]
    alerts = crew.get("/api/summary").get_json()["alerts"]
    assert alerts and ("186/118" in alerts[0]["text"] or "187/119" in alerts[0]["text"])
    assert "14 min" in alerts[0]["text"]

    # 5:30 History heatmap → Downlink Report PDF → Mission Control crew view.
    history = crew.get("/history").get_data(as_text=True)
    assert len(re.findall(r'class="heat__day', history)) == 30
    assert crew.get("/history/report.pdf").data[:5] == b"%PDF-"
    surgeon = app.test_client()
    login(surgeon, "FS-9001")
    grid = surgeon.get("/mission-control").get_data(as_text=True)
    assert "Cmdr. Sara Whitman" in grid and "Readiness: Get help now" in grid

    # Spare: if the wearable fails mid-demo, Settings → Demo panel → Wearable mode → Demo data.
    assert crew.post("/settings/sensor-mode", json={"mode": "demo"}).get_json()["mode"] == "demo"
