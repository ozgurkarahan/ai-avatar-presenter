"""SSRF-safe URL fetching for optional URL ingestion.

Disabled unless ``ENABLE_URL_INGEST=true``. When enabled:
- only http/https, no credentials in the URL, standard ports only;
- every DNS answer must be a public unicast address (private, loopback,
  link-local, reserved, multicast, unspecified, IPv4-mapped/compat IPv6,
  NAT64/6to4/Teredo-embedded and cloud metadata addresses are rejected);
- numeric hosts in any inet_aton form (decimal, octal, hex) are decoded and
  checked the same way;
- redirects are followed manually (max 3), re-validating every hop;
- connect/read timeouts and a 5 MB streamed body cap.

Residual risk: DNS re-binding between validation and connect is not fully
prevented (no IP pinning); keep the feature disabled in shared deployments.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0
_STANDARD_PORTS = {"http": {80}, "https": {443}}
_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
    ipaddress.ip_address("100.100.100.200"),
}
_BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal", "metadata.azure.com"}


class UnsafeURLError(ValueError):
    """Raised when a URL (or one of its redirects) is not allowed."""


def url_ingest_enabled() -> bool:
    return (os.environ.get("ENABLE_URL_INGEST") or "").strip().lower() in {"1", "true", "yes"}


def _parse_inet_aton(host: str) -> Optional[ipaddress.IPv4Address]:
    """Decode legacy numeric IPv4 forms (``2130706433``, ``0x7f.1``, ``0177.0.0.1``)."""
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    nums: list[int] = []
    for p in parts:
        if not p:
            return None
        try:
            if p.lower().startswith("0x"):
                n = int(p[2:] or "0", 16)
            elif len(p) > 1 and p.startswith("0"):
                n = int(p, 8)
            else:
                n = int(p, 10)
        except ValueError:
            return None
        nums.append(n)
    widths = {1: [32], 2: [8, 24], 3: [8, 8, 16], 4: [8, 8, 8, 8]}[len(nums)]
    value = 0
    for n, w in zip(nums, widths):
        if n < 0 or n >= (1 << w):
            return None
        value = (value << w) | n
    return ipaddress.IPv4Address(value)


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip in _METADATA_IPS:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return False
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
        # IPv4-compatible (::a.b.c.d) and NAT64 well-known prefix.
        if int(ip) >> 32 == 0:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    if (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified or not ip.is_global
    ):
        return False
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return True


Resolver = Callable[[str, int], list[str]]


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def validate_url(url: str, resolver: Optional[Resolver] = None) -> str:
    """Validate ``url``; returns it unchanged or raises :class:`UnsafeURLError`."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise UnsafeURLError("Invalid URL")
    url = url.strip()
    if any(c in url for c in ("\\", "\x00", "\r", "\n", "\t", " ")):
        raise UnsafeURLError("Invalid characters in URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("Invalid URL") from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in _STANDARD_PORTS:
        raise UnsafeURLError("Only http(s) URLs are allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeURLError("Credentials in URL are not allowed")
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeURLError("URL has no host")
    if port is not None and port not in _STANDARD_PORTS[scheme]:
        raise UnsafeURLError("Non-standard port")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".internal"):
        raise UnsafeURLError("Host not allowed")

    literal: Optional[ipaddress.IPv4Address | ipaddress.IPv6Address] = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = _parse_inet_aton(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("Address not allowed")
        return url

    resolve = resolver or _default_resolver
    try:
        answers = resolve(host, port or (443 if scheme == "https" else 80))
    except OSError as exc:
        raise UnsafeURLError("Host could not be resolved") from exc
    if not answers:
        raise UnsafeURLError("Host could not be resolved")
    for addr in answers:
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError as exc:
            raise UnsafeURLError("Address not allowed") from exc
        if not is_public_ip(ip):
            raise UnsafeURLError("Address not allowed")
    return url


def fetch_url(url: str, *, resolver: Optional[Resolver] = None, client=None) -> tuple[str, str]:
    """Fetch ``url`` safely. Returns ``(final_url, text)``."""
    import httpx

    own_client = client is None
    if own_client:
        client = httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=5.0),
            headers={"User-Agent": "Mozilla/5.0 (compatible; ai-presenter/1.0)"},
            trust_env=False,
        )
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current, resolver)
            with client.stream("GET", current) as resp:
                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    if not location:
                        raise UnsafeURLError("Redirect without location")
                    current = urljoin(current, location)
                    continue
                resp.raise_for_status()
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                    raise UnsafeURLError("Response too large")
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise UnsafeURLError("Response too large")
                encoding = resp.encoding or "utf-8"
                return current, bytes(body).decode(encoding, errors="replace")
        raise UnsafeURLError("Too many redirects")
    finally:
        if own_client:
            client.close()
