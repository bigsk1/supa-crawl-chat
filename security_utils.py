"""Security helpers for URLs and small API hardening concerns."""

from __future__ import annotations

import ipaddress
import os
import posixpath
import socket
from typing import Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests


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


def same_hostname(url: str, other_url: str) -> bool:
    """Return True when two URLs share the same normalized hostname."""
    left = (urlparse(url).hostname or "").lower().rstrip(".")
    right = (urlparse(other_url).hostname or "").lower().rstrip(".")
    return bool(left and right and left == right)


def safe_join_url(base_url: str, candidate: str, *, purpose: str = "fetch") -> str:
    """Resolve a possibly-relative URL against *base_url* and validate the result."""
    joined = urljoin(base_url, (candidate or "").strip())
    return validate_fetch_url(joined, purpose=purpose)


def fetch_validated_url(
    url: str,
    *,
    purpose: str = "fetch",
    timeout: int = 30,
    max_redirects: int = 5,
    headers: Optional[dict] = None,
) -> requests.Response:
    """Fetch a URL while validating every redirect hop.

    ``requests`` follows redirects automatically by default, which can turn a
    public URL into a private-network fetch after the initial validation. This
    helper disables automatic redirects, validates each Location target, and
    only then continues.
    """

    current_url = validate_fetch_url(url, purpose=purpose)
    session = requests.Session()

    for _ in range(max_redirects + 1):
        response = session.get(
            current_url,
            timeout=timeout,
            headers=headers,
            allow_redirects=False,
        )
        if not response.is_redirect:
            response.url = current_url
            return response

        location = response.headers.get("Location")
        if not location:
            raise UnsafeURL(f"{purpose} redirect did not include a Location header")

        current_url = safe_join_url(current_url, location, purpose=f"{purpose} redirect")

    raise UnsafeURL(f"{purpose} exceeded redirect limit ({max_redirects})")


def filter_safe_crawl_urls(
    urls: Iterable[str],
    *,
    source_url: Optional[str] = None,
    purpose: str = "crawl",
    allow_external_hosts: bool = False,
) -> List[str]:
    """Validate and deduplicate URLs before they are passed to the crawler.

    If ``source_url`` is provided, relative URLs are resolved against it. When
    ``allow_external_hosts`` is false, URLs whose host differs from the source
    host are skipped. Skipped URLs are intentionally silent at this layer so
    callers can decide how noisy logs should be.
    """

    safe: List[str] = []
    seen: Set[str] = set()
    for raw in urls:
        if not raw:
            continue
        try:
            candidate = (
                safe_join_url(source_url, raw, purpose=purpose)
                if source_url
                else validate_fetch_url(str(raw), purpose=purpose)
            )
        except UnsafeURL:
            continue

        parsed = urlparse(candidate)
        clean_path = posixpath.normpath(parsed.path or "/")
        if parsed.path.endswith("/") and not clean_path.endswith("/"):
            clean_path += "/"
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=clean_path,
            fragment="",
        ).geturl()

        if source_url and not allow_external_hosts and not same_hostname(source_url, normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        safe.append(normalized)

    return safe
