"""Is the server reachable, is the token valid, and when did the wearable last send?

    python scripts/device_check.py [--url http://192.168.1.23:5000]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap_env import ROOT, ensure_environment  # noqa: E402

ensure_environment("requests")
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from config import detect_lan_ip, load_config  # noqa: E402


def last_frame_age(config) -> float | None:
    """Seconds since the last stored raw frame of DEVICE_ID (reads the database directly)."""
    from app import create_app
    from app.models import Device, SensorSample

    app = create_app(config, testing=True)
    with app.app_context():
        device = Device.query.filter_by(device_id=config.device_id).first()
        if device is None:
            return None
        newest = SensorSample.query.filter_by(device_pk=device.id).order_by(SensorSample.ts.desc()).first()
        if newest is None:
            return None
        return (datetime.now(timezone.utc).replace(tzinfo=None) - newest.received_at).total_seconds()


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description="Check the wearable's connection to AstroVital.")
    parser.add_argument("--url", default=f"http://{detect_lan_ip(config)}:{config.port}")
    args = parser.parse_args(argv)
    write = sys.stdout.write
    ok = True
    headers = {"X-Device-Token": config.device_token, "X-Device-Id": config.device_id}
    try:
        response = requests.get(f"{args.url}/api/device/ping", headers=headers, timeout=4)
        write(f"  server reachable at {args.url}\n")
        if response.status_code == 200:
            write("  token valid\n")
        elif response.status_code == 401:
            write("  token REJECTED: run python scripts/device_setup.py and re-flash the wearable\n")
            ok = False
        elif response.status_code == 404:
            write("  device routes not reachable on this address (host rule): use the laptop's LAN IP\n")
            ok = False
        else:
            write(f"  unexpected answer {response.status_code}\n")
            ok = False
    except requests.RequestException as error:
        write(f"  server NOT reachable at {args.url}: {type(error).__name__}\n")
        write("  Is python run.py running? Is the address right (python scripts/device_setup.py --show)?\n")
        ok = False
    age = last_frame_age(config)
    if age is None:
        write(f"  no frame from {config.device_id} stored yet\n")
    else:
        write(f"  last frame from {config.device_id}: {age:.0f} s ago\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
