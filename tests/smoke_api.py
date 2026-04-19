#!/usr/bin/env python3
"""
Quick HTTP checks against a running Supa-Crawl-Chat API (for dev or after deploy).

  API_BASE_URL=http://192.168.70.54:8001 python tests/smoke_api.py

Requires: pip install requests (already a project dependency)
"""

from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    timeout = float(os.environ.get("API_SMOKE_TIMEOUT", "30"))
    api_key = (
        os.environ.get("API_SMOKE_API_KEY")
        or os.environ.get("SCC_API_KEYS", "").split(",", 1)[0].strip()
        or os.environ.get("API_KEYS", "").split(",", 1)[0].strip()
    )
    headers = {"x-api-key": api_key} if api_key else None

    checks = [
        ("GET", f"{base}/api", None),
        ("GET", f"{base}/api/sites", None),
        ("GET", f"{base}/api/chat/profiles", None),
    ]

    print(f"Smoke test API_BASE_URL={base} timeout={timeout}s\n")

    for method, url, body in checks:
        try:
            r = requests.request(method, url, timeout=timeout, json=body, headers=headers)
            ok = r.status_code < 400
            sym = "OK" if ok else "FAIL"
            print(f"[{sym}] {method} {url} -> {r.status_code}")
            if not ok:
                print(f"      body: {r.text[:500]}")
        except requests.RequestException as e:
            print(f"[FAIL] {method} {url} -> {e}")
            return 1

    # Chat (may call OpenAI — optional skip)
    if os.environ.get("API_SMOKE_SKIP_CHAT"):
        print("\nSkip POST /api/chat (API_SMOKE_SKIP_CHAT set)")
        return 0

    try:
        r = requests.post(
            f"{base}/api/chat",
            params={"model": os.environ.get("CHAT_MODEL")},
            headers=headers,
            json={
                "message": "ping",
                "session_id": "smoke-test-session",
                "profile": "default",
            },
            timeout=timeout,
        )
        ok = r.status_code < 500
        sym = "OK" if ok else "FAIL"
        print(f"[{sym}] POST {base}/api/chat -> {r.status_code}")
        if not ok:
            print(f"      body: {r.text[:800]}")
        elif r.status_code == 200:
            data = r.json()
            print(f"      response preview: {str(data.get('response', ''))[:120]}...")
    except requests.RequestException as e:
        print(f"[FAIL] POST {base}/api/chat -> {e}")
        return 1

    print("\nSmoke test finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
