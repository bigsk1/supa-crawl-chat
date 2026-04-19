"""Security helpers for URLs and small API hardening concerns."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, Optional, Set
from urllib.parse import urlparse


class UnsafeURL(ValueError):
    """Raised when a user supplied URL should not be fetched."""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_csv_env(name: str, *, lower: bool = True) -> Set[str]:
    raw = os.getenv(name, "")
    values = set()
    for item in raw.split(","):
        clean = item.strip()
        if not clean:
            continue
        values.add(clean.lower() if lower else clean)
    return values


def _host_matches(host: str, patterns: Iterable[str]) -> bool:
    host = host.lower().rstrip(".")
    for pattern in patterns:
        pattern = pattern.lower().rstrip(".")
        if not pattern:
            continue
        if pattern.startswith("*.") and host.endswith(pattern[1:]):
            return True
        if host == pattern:
            return True
    return False


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global


def _resolve_host(hostname: str, port: Optional[int]) -> Set[str]:
    addresses: Set[str] = set()
    infos = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.add(sockaddr[0])
    return addresses


def validate_fetch_url(url: str, *, purpose: str = "fetch") -> str:
    """Validate that a user supplied URL is safe to fetch.

    By default, only public http/https URLs are allowed. Private network targets
    can be enabled for trusted local deployments with ALLOW_PRIVATE_CRAWL_URLS=1
    or per-host with CRAWL_ALLOWED_HOSTS=example.com,*.example.org.
    """

    if not isinstance(url, str) or not url.strip():
        raise UnsafeURL(f"{purpose} URL is required")

    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURL(f"{purpose} URL must use http or https")
    if not parsed.hostname:
        raise UnsafeURL(f"{purpose} URL must include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeURL(f"{purpose} URL must not include credentials")

    hostname = parsed.hostname.lower().rstrip(".")
    allowed_hosts = parse_csv_env("CRAWL_ALLOWED_HOSTS")
    if _host_matches(hostname, allowed_hosts):
        return clean_url

    if env_bool("ALLOW_PRIVATE_CRAWL_URLS", default=False):
        return clean_url

    try:
        addresses = {hostname} if _looks_like_ip(hostname) else _resolve_host(hostname, parsed.port)
    except Exception as exc:
        raise UnsafeURL(f"Could not resolve {purpose} hostname '{hostname}': {exc}") from exc

    if not addresses:
        raise UnsafeURL(f"Could not resolve {purpose} hostname '{hostname}'")

    unsafe = []
    for address in addresses:
        try:
            if not _is_public_ip(address):
                unsafe.append(address)
        except ValueError:
            unsafe.append(address)

    if unsafe:
        raise UnsafeURL(
            f"Blocked {purpose} URL '{hostname}' because it resolves to non-public address(es): "
            f"{', '.join(sorted(unsafe))}. Set ALLOW_PRIVATE_CRAWL_URLS=1 or CRAWL_ALLOWED_HOSTS to allow it."
        )

    return clean_url


def _looks_like_ip(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False
