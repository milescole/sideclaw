"""SSRF protection: block requests to private/reserved IP ranges."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_URL_RE = re.compile(r"https?://[^\s\"'`;|<>]+", re.IGNORECASE)


def _is_private(addr: str) -> bool:
    """Check whether a resolved IP address falls in a blocked network."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in _BLOCKED_NETWORKS)


def validate_url_target(url: str) -> tuple[bool, str]:
    """Validate that a URL does not resolve to a private/reserved IP.

    Returns ``(True, "")`` when safe, ``(False, reason)`` when blocked.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return False, str(exc)

    if parsed.scheme not in {"http", "https"}:
        return False, f"Only http/https allowed, got '{parsed.scheme or 'none'}'"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname"

    try:
        addrinfos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed for {hostname}: {exc}"

    for family, _type, _proto, _canonname, sockaddr in addrinfos:
        addr = sockaddr[0]
        if _is_private(addr):
            return False, f"URL resolves to private/reserved address {addr}"

    return True, ""


def validate_resolved_url(url: str) -> tuple[bool, str]:
    """Post-redirect validation: check that the final URL is also safe."""
    return validate_url_target(url)


def contains_internal_url(command: str) -> bool:
    """Scan a shell command string for embedded URLs targeting private addresses."""
    for match in _URL_RE.finditer(command):
        url = match.group(0)
        ok, _ = validate_url_target(url)
        if not ok:
            return True
    return False
