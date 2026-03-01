"""Authentication middleware and dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from agent_chat.auth.jwt import verify_token
from agent_chat.config import get_settings


async def get_current_user_id(request: Request) -> str:
    """Extract and verify JWT from cookie, return user_id."""
    settings = get_settings()
    token = request.cookies.get("ac_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_token(token, settings)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id
