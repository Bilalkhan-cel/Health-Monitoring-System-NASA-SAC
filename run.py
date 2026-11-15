"""AstroVital entry point: bootstrap, print the boot checklist, serve.

Usage:  python run.py [--host 127.0.0.1] [--port 5000]
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap_env import ensure_environment  # noqa: E402

ensure_environment()

from app import bootstrap, create_app  # noqa: E402
from config import VERSION, build_checklist, load_config, render_checklist  # noqa: E402


def _console_supports(text: str) -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _write(line: str = "") -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start AstroVital.")
    parser.add_argument("--host", help="address to listen on (overrides BIND_HOST), for example 127.0.0.1")
    parser.add_argument("--port", type=int, help="port to listen on (overrides PORT)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Start AstroVital. Returns a process exit code."""
    args = _parse_args(argv)
    config = load_config()
    overrides = {key: value for key, value in (("bind_host", args.host), ("port", args.port)) if value}
    if overrides:
        config = dataclasses.replace(config, **overrides)
    app = create_app(config)
    report = bootstrap.run(app)

    checklist = build_checklist(
        config,
        db_ready=report.db_ready,
        crew_loaded=report.crew_loaded,
        wearable_last_seen_s=report.wearable_last_seen_s,
        sensor_mode=report.sensor_mode,
    )
    _write()
    _write(f"ASTROVITAL {VERSION} - {config.mission_name}")
    for line in render_checklist(checklist, unicode=_console_supports("✓✗→")):
        _write(f"  {line}")
    _write()
    _write(f"  Open http://localhost:{config.port} in your browser. Press Ctrl+C to stop.")
    _write()

    if not report.db_ready:
        return 1
    from app.services.live_monitor import LiveMonitor

    monitor = LiveMonitor(app)
    monitor.start()
    advertiser = advertise(config)
    try:
        # Single process, threaded, no reloader: the live stream hub lives in memory.
        app.run(host=config.bind_host, port=config.port, threaded=True, use_reloader=False, debug=config.debug)
    finally:
        monitor.stop()
        if advertiser is not None:
            advertiser()
    return 0


def advertise(config):
    """Announce _astrovital._tcp on the LAN so the wearable can find the server. Failure is harmless."""
    if not (config.device_enabled and config.zeroconf_enabled) or config.bind_host.startswith("127."):
        return None
    try:
        import socket

        from zeroconf import ServiceInfo, Zeroconf

        from config import detect_lan_ip

        address = detect_lan_ip(config)
        info = ServiceInfo("_astrovital._tcp.local.", "AstroVital._astrovital._tcp.local.",
                           addresses=[socket.inet_aton(address)], port=config.port, properties={"path": "/"})
        zc = Zeroconf()
        zc.register_service(info)
    except Exception:  # noqa: BLE001 (mDNS is optional; the server URL can always be set by hand)
        return None

    def close() -> None:
        try:
            zc.unregister_service(info)
            zc.close()
        except Exception:  # noqa: BLE001
            pass

    return close


if __name__ == "__main__":
    raise SystemExit(main())
