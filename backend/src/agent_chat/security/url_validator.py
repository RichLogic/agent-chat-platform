"""URL validation — SSRF protection, protocol/redirect/size limits."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

# Allowed schemes
_ALLOWED_SCHEMES = {"http", "https"}

# Default max redirects
DEFAULT_MAX_REDIRECTS = 5

# Default max response body (bytes) — 5 MB
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# Allowed content-type prefixes
ALLOWED_CONTENT_TYPES = {"text/", "application/json", "application/xml", "application/xhtml"}

# Private / reserved IP ranges to block
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # "this" network
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 private
    ipaddress.ip_network("127.0.0.0/8"),         # loopback
    ipaddress.ip_network("172.16.0.0/12"),       # RFC 1918 private
    ipaddress.ip_network("192.168.0.0/16"),      # RFC 1918 private
    ipaddress.ip_network("224.0.0.0/4"),         # multicast
    ipaddress.ip_network("240.0.0.0/4"),         # reserved
    # IPv6
    ipaddress.ip_network("::1/128"),             # loopback
    ipaddress.ip_network("fc00::/7"),            # unique local
    ipaddress.ip_network("fe80::/10"),           # link-local
    # Cloud metadata — the real SSRF target
    ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure metadata
]

# Hostnames to always block
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
}


class URLValidationError(Exception):
    """Raised when a URL fails security validation."""


def validate_url(
    url: str,
    *,
    allowed_schemes: set[str] | None = None,
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
) -> str:
    """Validate a URL for SSRF safety. Returns the normalized URL.

    Raises URLValidationError on failure.
    """
    schemes = allowed_schemes or _ALLOWED_SCHEMES

    # Parse
    try:
        parsed = urlparse(url)
    except Exception:
        raise URLValidationError(f"Invalid URL: {url}")

    # Scheme check
    if parsed.scheme not in schemes:
        raise URLValidationError(
            f"Blocked scheme '{parsed.scheme}' — only {', '.join(sorted(schemes))} allowed"
        )

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname")

    # Denylist (explicit domain blocks)
    if denylist:
        for pattern in denylist:
            if hostname == pattern or hostname.endswith("." + pattern):
                raise URLValidationError(f"Hostname '{hostname}' is in deny list")

    # Allowlist (if set, ONLY these domains pass)
    if allowlist:
        allowed = False
        for pattern in allowlist:
            if hostname == pattern or hostname.endswith("." + pattern):
                allowed = True
                break
        if not allowed:
            raise URLValidationError(f"Hostname '{hostname}' is not in allow list")

    # Blocked hostnames
    hostname_lower = hostname.lower()
    if hostname_lower in _BLOCKED_HOSTNAMES:
        raise URLValidationError(f"Blocked hostname: {hostname}")

    # Resolve hostname and check IP
    _check_resolved_ip(hostname)

    return url


def _check_resolved_ip(hostname: str) -> None:
    """Resolve hostname to IP and check against blocked ranges."""
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        raise URLValidationError(f"Cannot resolve hostname: {hostname}")

    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise URLValidationError(
                    f"Blocked: {hostname} resolves to private/reserved IP {ip_str}"
                )


def is_allowed_content_type(content_type: str | None) -> bool:
    """Check if a response content-type is allowed."""
    if not content_type:
        return True  # missing content-type — allow, parser will handle
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPES)
