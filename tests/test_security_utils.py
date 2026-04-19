import pytest

from security_utils import UnsafeURL, parse_csv_env, validate_fetch_url


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
