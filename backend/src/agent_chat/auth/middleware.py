"""Authentication middleware and dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from agent_chat.auth.jwt import verify_token
from agent_chat.config import get_settings


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    return request.cookies.get("ac_token")


async def get_current_user_id(request: Request) -> str:
    """Extract and verify auth token from Authorization header or cookie."""
    settings = get_settings()
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if settings.eval_token and token == settings.eval_token:
        return settings.eval_user_id

    user_id = verify_token(token, settings)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id
