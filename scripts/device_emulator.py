"""Pretend to be the ESP32 wearable over real HTTP (Section 10A.11).

    python scripts/device_emulator.py --profile normal
    python scripts/device_emulator.py --profile wifi_gap --seconds 120
    python scripts/device_emulator.py --list

It posts to /api/device/ingest with the real token from .env, so it exercises the
whole network path without hardware. Keep it running in a second terminal during a
demo as a spare wearable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap_env import ROOT, ensure_environment  # noqa: E402

ensure_environment("requests")
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app.services.sensors.synthetic import SyntheticWearable  # noqa: E402
from config import load_config  # noqa: E402

PROFILES = {
    "normal": "steady finger, good signal, probe under the arm",
    "no_finger": "nothing on the sensor",
    "finger_flap": "finger on for 6 s, off for 6 s",
    "weak_signal": "finger on but low signal quality",
    "spike": "a 60 bpm jump every 30 s (rejected by the jump filter)",
    "flatline": "identical frames (stuck sensor)",
    "probe_missing": "temperature probe unplugged",
    "probe_ambient": "probe lying on the desk",
    "probe_warming": "probe warming up under the arm",
    "wifi_gap": "90 s offline, then the buffered backlog arrives",
    "duplicate": "every batch sent twice",
    "bad_token": "wrong token (expect 401)",
    "malformed": "a frame with a wrong type (expect 400)",
    "flood": "requests as fast as possible (expect 429)",
    "restart": "reboots after 20 s (new boot_id)",
}
BASE_PROFILE = {"wifi_gap": "normal", "duplicate": "normal", "bad_token": "normal", "malformed": "normal",
                "flood": "normal", "restart": "normal"}


class Emulator:
    def __init__(self, url: str, token: str, device_id: str, profile: str, *, fast: bool = False,
                 session=None, quiet: bool = False) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.device_id = device_id
        self.profile = profile
        self.fast = fast
        self.quiet = quiet
        self.http = session or requests.Session()
        self.wearable = SyntheticWearable(profile=BASE_PROFILE.get(profile, profile), seed=3,
                                          boot_id=f"{int(time.time()) & 0xFFFFFFFF:08x}")
        self.log: list[tuple[int, dict]] = []

    def headers(self, token: str | None = None) -> dict:
        return {"X-Device-Token": token if token is not None else self.token, "X-Device-Id": self.device_id,
                "Content-Type": "application/json"}

    def post(self, batch: dict, *, token: str | None = None, raw: str | None = None) -> tuple[int, dict]:
        body = raw if raw is not None else json.dumps(batch)
        response = self.http.post(f"{self.url}/api/device/ingest", data=body, headers=self.headers(token), timeout=5)
        try:
            data = response.json()
        except ValueError:
            data = {}
        self.log.append((response.status_code, data))
        if not self.quiet:
            counts = f"accepted {data.get('accepted', '-')} duplicate {data.get('duplicate', '-')} " \
                     f"rejected {data.get('rejected', '-')}" if response.ok else data.get("error", "")
            sys.stdout.write(f"  {response.status_code}  {counts}\n")
            sys.stdout.flush()
        return response.status_code, data

    def wait(self, seconds: float) -> None:
        if not self.fast:
            time.sleep(seconds)

    def run(self, seconds: int) -> list[tuple[int, dict]]:
        profile = self.profile
        if profile == "bad_token":
            self.post(self.wearable.batch([self.wearable.frame()], self.device_id), token="wrong-token")
            return self.log
        if profile == "malformed":
            batch = self.wearable.batch([self.wearable.frame()], self.device_id)
            batch["frames"][0]["hr"] = "seventy"
            self.post(batch)
            return self.log
        if profile == "flood":
            for _ in range(max(seconds, 150)):
                status, _ = self.post(self.wearable.batch([self.wearable.frame()], self.device_id))
                if status == 429:
                    break
            return self.log
        if profile == "wifi_gap":
            for _ in range(min(10, seconds)):
                self.post(self.wearable.batch([self.wearable.frame()], self.device_id))
                self.wait(1)
            backlog = [self.wearable.frame() for _ in range(90)]
            if not self.quiet:
                sys.stdout.write("  (Wi-Fi back: sending a 90 s backlog)\n")
            for start in range(0, len(backlog), 20):
                chunk = backlog[start:start + 20]
                batch = self.wearable.batch(chunk, self.device_id)
                batch["sent_uptime_ms"] = backlog[-1]["up_ms"]
                self.post(batch)
            seconds -= 10
        for second in range(max(seconds, 0)):
            if profile == "restart" and second == 20:
                self.wearable.restart(f"{(int(time.time()) + 1) & 0xFFFFFFFF:08x}")
            batch = self.wearable.batch([self.wearable.frame()], self.device_id)
            self.post(batch)
            if profile == "duplicate":
                self.post(batch)
            self.wait(1)
        return self.log


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description="Emulate the AstroVital ESP32 wearable over HTTP.")
    parser.add_argument("--profile", default="normal", choices=sorted(PROFILES))
    parser.add_argument("--seconds", type=int, default=600, help="how long to run (default 600)")
    parser.add_argument("--url", default=f"http://127.0.0.1:{config.port}", help="server URL")
    parser.add_argument("--device-id", default=config.device_id)
    parser.add_argument("--token", default=config.device_token, help="device token (default: DEVICE_TOKEN in .env)")
    parser.add_argument("--fast", action="store_true", help="do not wait between frames (tests)")
    parser.add_argument("--list", action="store_true", help="list the profiles and exit")
    args = parser.parse_args(argv)
    if args.list:
        for name, text in PROFILES.items():
            sys.stdout.write(f"  {name:14} {text}\n")
        return 0
    if not args.token:
        sys.stdout.write("DEVICE_TOKEN is empty. Run python scripts/setup.py first.\n")
        return 1
    sys.stdout.write(f"Emulating {args.device_id} ({args.profile}: {PROFILES[args.profile]}) -> {args.url}\n")
    try:
        Emulator(args.url, args.token, args.device_id, args.profile, fast=args.fast).run(args.seconds)
    except requests.ConnectionError:
        sys.stdout.write(f"Cannot reach {args.url}. Is python run.py running?\n")
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
