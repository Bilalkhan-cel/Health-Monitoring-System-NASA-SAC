"""Firmware side of the wearable contract: shared fixtures, field names, pins and device_setup.py."""

from __future__ import annotations

import json
import re

import pytest

from app.services.sensors.frames import BadPayload, parse_batch
from conftest import ROOT, load_script

FIXTURES = ROOT / "tests" / "fixtures" / "device_frames"
FIRMWARE = ROOT / "firmware"
device_setup = load_script("device_setup")


@pytest.mark.parametrize("name", ["normal", "no_finger", "weak_signal", "probe_ambient", "probe_missing",
                                  "backlog_90s"])
def test_good_fixtures_validate_against_the_server_schema(name):
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    batch = parse_batch(payload)
    assert batch.frames and batch.boot_id == "7f3a91c2"


@pytest.mark.parametrize("name, path", [("malformed_type", "frames[0].hr"), ("malformed_version", "v"),
                                        ("malformed_missing_boot", "boot_id")])
def test_malformed_fixtures_are_rejected_with_a_path(name, path):
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    with pytest.raises(BadPayload) as caught:
        parse_batch(payload)
    assert caught.value.path == path


def test_firmware_sends_exactly_the_contract_fields():
    source = (FIRMWARE / "src" / "net_client.cpp").read_text(encoding="utf-8")
    batch_keys = set(re.findall(r'doc\["(\w+)"\]', source))
    frame_keys = set(re.findall(r'o\["(\w+)"\]', source))
    fixture = json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))
    assert batch_keys == set(fixture) - {"note"}
    assert frame_keys == set(fixture["frames"][0])
    assert '"X-Device-Token"' in source and '"X-Device-Id"' in source


def test_every_pin_lives_in_pins_h():
    for path in (FIRMWARE / "src").glob("*.cpp"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(begin|pinMode|OneWire)\s*\(\s*\d", text), f"hard-coded pin in {path.name}"
    pins = (FIRMWARE / "include" / "pins.h").read_text(encoding="utf-8")
    assert "#define PIN_I2C_SDA 21" in pins and "#define PIN_I2C_SCL 22" in pins and "#define PIN_ONEWIRE 4" in pins


def test_platformio_pins_exact_versions():
    ini = (FIRMWARE / "platformio.ini").read_text(encoding="utf-8")
    assert "platform = espressif32@6.12.0" in ini
    for line in ini.splitlines():
        if "/" in line and "@" in line and line.startswith("    "):
            assert re.search(r"@\d+\.\d+\.\d+$", line.strip()), line


def test_secrets_are_ignored_and_the_example_has_no_real_values():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "firmware/include/secrets.h" in gitignore
    example = (FIRMWARE / "include" / "secrets.example.h").read_text(encoding="utf-8")
    assert "your-password" in example


def test_device_setup_renders_secrets(tmp_path):
    text = device_setup.render_secrets("Hotspot", "pa55word", "http://192.168.43.10:5000", "tok", "AV-ESP32-01")
    assert '#define SERVER_URL "http://192.168.43.10:5000"' in text and '#define WIFI_PASS "pa55word"' in text
    assert device_setup.ascii_only("Plain-Name_1") and not device_setup.ascii_only('quote"') \
        and not device_setup.ascii_only("Café")


def test_device_setup_ranks_real_adapters_first():
    ranked = device_setup.rank([("172.20.0.1", "vEthernet (WSL)"), ("192.168.43.10", "Wireless LAN adapter Wi-Fi"),
                                ("10.8.0.2", "Ethernet adapter VPN")])
    assert ranked[0][0] == "192.168.43.10"


def test_device_setup_reads_env_and_prints_a_firewall_command(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PORT=5000                                      # comment\nDEVICE_TOKEN=abc\nDEVICE_LAN_IP=\n",
                   encoding="utf-8")
    values = device_setup.read_env(env)
    assert values == {"PORT": "5000", "DEVICE_TOKEN": "abc", "DEVICE_LAN_IP": ""}
    assert device_setup.server_url(values, "192.168.1.5") == "http://192.168.1.5:5000"
    command = device_setup.firewall_command("5000")
    assert "-RemoteAddress LocalSubnet" in command and "-LocalPort 5000" in command


def test_hardware_docs_exist_and_claim_nothing():
    test_doc = (ROOT / "docs" / "HARDWARE_TEST.md").read_text(encoding="utf-8")
    for step in ("T-1", "T0", "T1", "T2", "T3", "T4", "T5", "T5b", "T6", "T7", "T8", "T9", "T10", "T11", "T12",
                 "T13", "T13a", "T13b", "T14"):
        assert f"**{step} " in test_doc, step
    readme = (FIRMWARE / "README.md").read_text(encoding="utf-8")
    assert "V3" in readme and "do not modify the board" in readme.lower()
