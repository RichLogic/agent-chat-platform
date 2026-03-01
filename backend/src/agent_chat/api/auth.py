"""Auth endpoints: login, callback, me, logout."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from agent_chat.auth.github import (
    exchange_code,
    fetch_github_user,
    get_authorize_url,
    validate_state,
)
from agent_chat.auth.jwt import create_access_token
from agent_chat.auth.middleware import get_current_user_id
from agent_chat.db.repository import get_user, upsert_user
from agent_chat.config import get_settings

logger = structlog.get_logger()

router = APIRouter()


@router.get("/api/auth/login")
async def login() -> dict:
    """Return the GitHub OAuth authorize URL for the frontend to redirect to."""
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured")
    url = get_authorize_url(settings)
    return {"url": url}


@router.get("/api/auth/callback")
async def callback(code: str, state: str) -> HTMLResponse:
    """Handle OAuth callback: exchange code, set cookie, redirect to frontend via HTML."""
    settings = get_settings()
    if not validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        access_token = await exchange_code(code, settings)
        gh_user = await fetch_github_user(access_token)
    except Exception as e:
        logger.error("oauth_callback_failed", error=str(e))
        raise HTTPException(status_code=502, detail="GitHub OAuth exchange failed")

    user = await upsert_user(
        github_id=gh_user["id"],
        github_login=gh_user["login"],
        display_name=gh_user.get("name") or gh_user["login"],
        avatar_url=gh_user.get("avatar_url", ""),
        email=gh_user.get("email") or "",
    )

    token = create_access_token(user["id"], settings)
    max_age = settings.jwt_expiry_minutes * 60

    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body><p>登录成功，正在跳转…</p>
<script>window.location.replace('/');</script>
</body></html>"""

    response = HTMLResponse(content=html)
    response.set_cookie(
        key="ac_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=max_age,
    )
    return response


@router.get("/api/auth/me")
async def me(user_id: str = Depends(get_current_user_id)) -> dict:
    user = await get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user["id"],
        "github_login": user["github_login"],
        "display_name": user["display_name"],
        "avatar_url": user["avatar_url"],
        "email": user["email"],
    }


@router.post("/api/auth/logout")
async def logout():
    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key="ac_token", path="/")
    return response
