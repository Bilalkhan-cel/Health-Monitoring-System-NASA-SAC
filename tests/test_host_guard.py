"""The host guard table from Section 3."""

from __future__ import annotations

import pytest

from app.security import allowed, host_name, is_lan_ip
from conftest import build_app

TRUSTED = ("localhost", "127.0.0.1")
PATHS = ("/login", "/api/openhome/context", "/api/device/ingest", "/healthz")

# host -> expected result for (login, openhome, device, healthz)
TABLE = {
    "localhost": (True, True, False, True),
    "localhost:5000": (True, True, False, True),
    "127.0.0.1": (True, True, True, True),
    "192.168.1.23:5000": (False, True, True, True),
    "10.0.0.7": (False, True, True, True),
    "203.0.113.9": (False, True, False, True),
    "abc.trycloudflare.com": (False, True, False, True),
    "astrovital.local": (False, True, False, True),
}


@pytest.mark.parametrize("host", TABLE)
def test_host_table(host):
    for path, expected in zip(PATHS, TABLE[host]):
        assert allowed(host, path, {}, TRUSTED, ()) is expected, (host, path)


def test_device_hosts_opens_only_the_device_routes():
    assert allowed("astrovital.local", "/api/device/ingest", {}, TRUSTED, ("astrovital.local",))
    assert not allowed("astrovital.local", "/login", {}, TRUSTED, ("astrovital.local",))


@pytest.mark.parametrize("header", ["X-Forwarded-For", "CF-Connecting-IP", "Forwarded"])
def test_forwarded_requests_never_reach_device_routes(header):
    assert not allowed("192.168.1.23:5000", "/api/device/ingest", {header: "1.2.3.4"}, TRUSTED, ())


def test_host_parsing():
    assert host_name("Example.COM:8080") == "example.com"
    assert host_name("[::1]:5000") == "::1"
    assert is_lan_ip("169.254.10.2") and is_lan_ip("::1") and not is_lan_ip("8.8.8.8")


def test_guard_runs_inside_the_app(env_values):
    client = build_app(env_values).test_client()
    assert client.get("/login", headers={"Host": "abc.trycloudflare.com"}).status_code == 404
    assert client.get("/static/css/theme.css", headers={"Host": "abc.trycloudflare.com"}).status_code == 404
    assert client.get("/healthz", headers={"Host": "abc.trycloudflare.com"}).status_code == 200
    assert client.get("/login", headers={"Host": "localhost:5000"}).status_code == 200
    assert client.get("/login", headers={"Host": "192.168.1.23:5000"}).status_code == 404
