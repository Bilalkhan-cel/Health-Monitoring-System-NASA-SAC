"""Host guard (Section 3 of PROMPT.md).

* Hosts in ``TRUSTED_HOSTS`` reach the whole app.
* Any host (for example a cloudflared tunnel) reaches only ``/api/openhome/*`` and
  ``/healthz``, so exposing Flask to OpenHome never exposes the login page or health data.
* ``/api/device/*`` is reachable only when the Host header is a private, loopback or
  link-local IP literal (or listed in ``DEVICE_HOSTS``) and the request carries no
  forwarding headers, so a tunnel can never reach the wearable routes.
"""

from __future__ import annotations

import ipaddress
from typing import Mapping

PUBLIC_ANY_HOST = ("/api/openhome/",)
PUBLIC_EXACT = ("/healthz",)
DEVICE_PREFIX = "/api/device/"
FORWARDING_HEADERS = ("X-Forwarded-For", "CF-Connecting-IP", "Forwarded", "X-Real-IP")


def host_name(host_header: str) -> str:
    """Strip the port (and IPv6 brackets) from a Host header."""
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host[1:]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host


LAN_NETWORKS = tuple(ipaddress.ip_network(net) for net in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",   # private (phone hotspots use these)
    "127.0.0.0/8", "169.254.0.0/16",                    # loopback, link-local
    "::1/128", "fc00::/7", "fe80::/10",
))


def is_lan_ip(host: str) -> bool:
    """True for private, loopback or link-local IP literals.

    Python's ``is_private`` also covers documentation and reserved ranges, so the
    networks are listed explicitly.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in LAN_NETWORKS if network.version == address.version)


def allowed(host_header: str, path: str, headers: Mapping[str, str], trusted_hosts: tuple[str, ...],
            device_hosts: tuple[str, ...]) -> bool:
    """Decide whether a request may reach the app at all."""
    host = host_name(host_header)
    if path.startswith(DEVICE_PREFIX):
        if any(headers.get(name) for name in FORWARDING_HEADERS):
            return False
        return is_lan_ip(host) or host in device_hosts
    if host in trusted_hosts:
        return True
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_ANY_HOST)
