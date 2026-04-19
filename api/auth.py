"""Optional API key authentication for local or exposed deployments."""

from __future__ import annotations

import secrets
from typing import Set

from fastapi import HTTPException, Request, status

from security_utils import parse_csv_env


def configured_api_keys() -> Set[str]:
    return parse_csv_env("SCC_API_KEYS", lower=False) | parse_csv_env("API_KEYS", lower=False)


def _extract_key(request: Request) -> str:
    header_key = request.headers.get("x-api-key", "").strip()
    if header_key:
        return header_key

    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    return ""


async def require_api_key(request: Request) -> None:
    keys = configured_api_keys()
    if not keys:
        return

    supplied = _extract_key(request)
    if any(secrets.compare_digest(supplied, key) for key in keys):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )
