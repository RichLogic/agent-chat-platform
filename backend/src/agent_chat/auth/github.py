"""GitHub OAuth helpers."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from agent_chat.config import Settings

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

# In-memory state store for CSRF protection
_pending_states: set[str] = set()


def get_authorize_url(settings: Settings) -> str:
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.frontend_url}/api/auth/callback",
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def validate_state(state: str) -> bool:
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False


async def exchange_code(code: str, settings: Settings) -> str:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient(trust_env=False) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data)}")
        return data["access_token"]


async def fetch_github_user(access_token: str) -> dict:
    """Fetch GitHub user profile."""
    async with httpx.AsyncClient(trust_env=False) as client:
        resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()
