"""Tests for auth middleware token extraction."""

from __future__ import annotations

from starlette.requests import Request

import pytest

from agent_chat.auth.jwt import create_access_token
from agent_chat.auth.middleware import get_current_user_id
from agent_chat.config import Settings, set_settings


def _make_request(*, authorization: str | None = None, cookie: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_bearer_jwt_header_is_accepted() -> None:
    settings = Settings(_env_file=None, jwt_secret="x" * 32)
    set_settings(settings)
    token = create_access_token("user-123", settings)

    request = _make_request(authorization=f"Bearer {token}")

    assert await get_current_user_id(request) == "user-123"


@pytest.mark.asyncio
async def test_eval_token_bypass_is_accepted() -> None:
    settings = Settings(_env_file=None, jwt_secret="x" * 32, eval_token="eval-secret")
    set_settings(settings)

    request = _make_request(authorization="Bearer eval-secret")

    assert await get_current_user_id(request) == "eval_runner"
