"""WebUI login (JWT) and public auth status — no Bearer required on these routes."""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.supa_auth import issue_webui_jwt, webui_password_configured
from security_utils import env_bool

router = APIRouter()


class WebUILoginBody(BaseModel):
    password: str = Field(..., min_length=1, max_length=500)


@router.get("/webui/status")
async def webui_status():
    """Whether the SPA must show a login page, and whether API Bearer auth is enabled."""
    return {
        "webui_login_required": webui_password_configured(),
        "supa_api_auth": env_bool("SUPA_API_AUTH", default=False),
    }


@router.post("/webui/login")
async def webui_login(body: WebUILoginBody):
    """Exchange WEBUI_PASSWORD for a short-lived JWT used as Authorization: Bearer on API calls."""
    expected = os.getenv("WEBUI_PASSWORD", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WebUI password is not configured",
        )
    if not secrets.compare_digest(body.password, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    return issue_webui_jwt()
