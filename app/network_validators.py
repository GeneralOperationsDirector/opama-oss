"""
SSRF protection — blocks requests to private/internal IP ranges.

Call assert_public_url() before making any server-side HTTP request to a
user-supplied URL (webhook targets, remote plugin URLs, manifest URLs from
untrusted sources).

Covers:
  - RFC 1918 private ranges (10.x, 172.16-31.x, 192.168.x)
  - Loopback (127.x, ::1)
  - Link-local / cloud metadata (169.254.x — AWS/GCP/Azure IMDS)
  - Multicast (224.x, ff00::/8)
  - Unspecified (0.0.0.0, ::)
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space (RFC 6598)
    ipaddress.ip_network("198.18.0.0/15"),     # benchmarking (RFC 2544)
    ipaddress.ip_network("240.0.0.0/4"),       # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # unique local
    ipaddress.ip_network("fe80::/10"),         # link-local
    ipaddress.ip_network("ff00::/8"),          # multicast
]

_ALLOWED_SCHEMES = {"http", "https"}


def assert_public_url(url: str, label: str = "URL") -> None:
    """
    Raise ValueError if `url` is not a safe, publicly-routable destination.

    Checks:
      - Scheme must be http or https
      - Hostname must be present
      - Resolved IP must not be in a blocked range
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError(f"{label} is not a valid URL")

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"{label} scheme must be http or https, got '{parsed.scheme}'")

    host = parsed.hostname
    if not host:
        raise ValueError(f"{label} is missing a hostname")

    # Reject bare 'localhost' by name
    if host.lower() in ("localhost", "localhost."):
        raise ValueError(f"{label} points to localhost — internal addresses are not allowed")

    try:
        resolved = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"{label} hostname '{host}' could not be resolved")

    for family, _type, _proto, _canon, sockaddr in resolved:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(
                    f"{label} resolves to a private or reserved address ({addr}) — "
                    "internal network access is not permitted"
                )
