import pytest
import requests
from fastapi import HTTPException

import security_utils
from api.routers.crawl import CrawlRequest, _advanced_options
from security_utils import (
    UnsafeURL,
    fetch_validated_url,
    filter_safe_crawl_urls,
    parse_csv_env,
    validate_fetch_url,
)


def test_parse_csv_env_can_preserve_case(monkeypatch):
    monkeypatch.setenv("SCC_API_KEYS", "KeyOne,SecondKEY")

    assert parse_csv_env("SCC_API_KEYS", lower=False) == {"KeyOne", "SecondKEY"}


def test_validate_fetch_url_blocks_private_ip_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_CRAWL_URLS", raising=False)
    monkeypatch.delenv("CRAWL_ALLOWED_HOSTS", raising=False)

    with pytest.raises(UnsafeURL):
        validate_fetch_url("http://127.0.0.1:8000")


def test_validate_fetch_url_allows_private_ip_when_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_CRAWL_URLS", "true")
    monkeypatch.delenv("CRAWL_ALLOWED_HOSTS", raising=False)

    assert validate_fetch_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_validate_fetch_url_allows_explicit_host(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_CRAWL_URLS", raising=False)
    monkeypatch.setenv("CRAWL_ALLOWED_HOSTS", "localhost")

    assert validate_fetch_url("http://localhost:8000") == "http://localhost:8000"


def test_validate_fetch_url_rejects_credentials(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_CRAWL_URLS", "true")

    with pytest.raises(UnsafeURL):
        validate_fetch_url("https://user:pass@example.com")


def test_filter_safe_crawl_urls_blocks_private_and_external_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_CRAWL_URLS", raising=False)
    monkeypatch.delenv("CRAWL_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(security_utils, "_resolve_host", lambda hostname, port: {"93.184.216.34"})

    urls = filter_safe_crawl_urls(
        [
            "https://example.com/docs",
            "https://other.example.com/docs",
            "http://127.0.0.1:8000/admin",
            "/relative",
        ],
        source_url="https://example.com/sitemap.xml",
        purpose="sitemap URL",
        allow_external_hosts=False,
    )

    assert urls == [
        "https://example.com/docs",
        "https://example.com/relative",
    ]


def test_filter_safe_crawl_urls_can_allow_public_external_hosts(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_CRAWL_URLS", raising=False)
    monkeypatch.delenv("CRAWL_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(security_utils, "_resolve_host", lambda hostname, port: {"93.184.216.34"})

    urls = filter_safe_crawl_urls(
        ["https://example.com/docs", "https://example.org/guide"],
        source_url="https://example.com/sitemap.xml",
        purpose="sitemap URL",
        allow_external_hosts=True,
    )

    assert urls == ["https://example.com/docs", "https://example.org/guide"]


def test_fetch_validated_url_blocks_redirect_to_private_host(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_CRAWL_URLS", raising=False)
    monkeypatch.delenv("CRAWL_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(security_utils, "_resolve_host", lambda hostname, port: {"93.184.216.34"})

    class FakeResponse(requests.Response):
        def __init__(self):
            super().__init__()
            self.status_code = 302
            self.headers["Location"] = "http://127.0.0.1:8000/metadata"
            self.url = "https://example.com/redirect"

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(security_utils.requests, "Session", lambda: FakeSession())

    with pytest.raises(UnsafeURL):
        fetch_validated_url("https://example.com/redirect", purpose="sitemap crawl")


def test_crawl_advanced_options_block_external_links_by_default(monkeypatch):
    monkeypatch.delenv("CRAWL_ALLOW_EXTERNAL_LINKS", raising=False)

    request = CrawlRequest(url="https://example.com", follow_external_links=True)

    with pytest.raises(HTTPException) as exc_info:
        _advanced_options(request)

    assert "follow_external_links is disabled" in exc_info.value.detail


def test_crawl_advanced_options_allow_external_links_when_enabled(monkeypatch):
    monkeypatch.setenv("CRAWL_ALLOW_EXTERNAL_LINKS", "true")

    request = CrawlRequest(url="https://example.com", follow_external_links=True)

    assert _advanced_options(request)["follow_external_links"] is True
