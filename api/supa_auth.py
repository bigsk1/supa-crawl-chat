"""
SUPA_API_AUTH + WebUI JWT: optional Bearer auth with localhost / trusted CIDR bypass.

Env:
  SUPA_API_AUTH, SUPA_API_KEY, SUPA_API_TRUST_FORWARDED, SUPA_API_TRUST_CIDRS
  WEBUI_PASSWORD, WEBUI_SECRET, WEBUI_TOKEN_EXPIRY_DAYS
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
import time
from collections import defaultdict
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, status

from api.auth import configured_api_keys, _extract_key
from security_utils import env_bool

JWT_ALG = "HS256"
JWT_AUD = "supa-crawl-webui"


def get_client_ip(request: Request) -> str:
    if env_bool("SUPA_API_TRUST_FORWARDED", default=False):
        xf = request.headers.get("x-forwarded-for", "")
        if xf:
            return xf.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


def is_ip_trusted(ip: str) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    extra = os.getenv("SUPA_API_TRUST_CIDRS", "").strip()
    if not extra:
        return False
    for cidr in extra.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if addr in net:
                return True
        except ValueError:
            continue
    return False


def _webui_jwt_secret() -> str:
    explicit = os.getenv("WEBUI_SECRET", "").strip()
    if explicit:
        return explicit
    pw = os.getenv("WEBUI_PASSWORD", "").strip()
    if not pw:
        return ""
    return hashlib.sha256(f"supa_webui_jwt_v1:{pw}".encode()).hexdigest()


def webui_password_configured() -> bool:
    return bool(os.getenv("WEBUI_PASSWORD", "").strip())


def issue_webui_jwt() -> Dict[str, Any]:
    secret = _webui_jwt_secret()
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WebUI auth not configured")
    days = max(1, int(os.getenv("WEBUI_TOKEN_EXPIRY_DAYS", "30")))
    exp = int(time.time()) + days * 86400
    token = jwt.encode(
        {"sub": "webui", "aud": JWT_AUD, "exp": exp},
        secret,
        algorithm=JWT_ALG,
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": days * 86400}


def verify_webui_jwt(token: str) -> bool:
    secret = _webui_jwt_secret()
    if not secret or not token:
        return False
    try:
        jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALG],
            audience=JWT_AUD,
            options={"require": ["exp", "sub"]},
        )
        return True
    except jwt.PyJWTError:
        return False


async def require_supa_request_auth(request: Request) -> None:
    """
    - If neither SUPA_API_AUTH nor legacy SCC/API keys: allow (open LAN).
    - Trusted IP: allow.
    - Else: WebUI JWT, or SUPA_API_KEY, or legacy x-api-key / Bearer keys.
    """
    legacy = configured_api_keys()
    supa_on = env_bool("SUPA_API_AUTH", default=False)
    supa_key = os.getenv("SUPA_API_KEY", "").strip()

    if not supa_on and not legacy:
        return

    ip = get_client_ip(request)
    if is_ip_trusted(ip):
        return

    raw = _extract_key(request)
    if raw:
        if verify_webui_jwt(raw):
            return
        if supa_key and secrets.compare_digest(raw, supa_key):
            return
        if legacy and any(secrets.compare_digest(raw, k) for k in legacy):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --- /api/query rate limit (in-process; per-IP) ---

_query_hits: Dict[str, list] = defaultdict(list)


def check_query_rate_limit(request: Request) -> None:
    raw = os.getenv("QUERY_RATE_LIMIT_PER_MINUTE", "30").strip()
    try:
        limit = int(raw)
    except ValueError:
        limit = 30
    if limit <= 0:
        return

    ip = get_client_ip(request) or "unknown"
    now = time.time()
    window = 60.0
    bucket = _query_hits[ip]
    bucket[:] = [t for t in bucket if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Query rate limit exceeded; try again later.",
        )
    bucket.append(now)
