"""JWT token creation and verification tests."""

from __future__ import annotations

from agent_chat.auth.jwt import create_access_token, verify_token
from agent_chat.config import Settings


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        jwt_secret="test-secret",
        jwt_expiry_minutes=60,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_create_and_verify():
    settings = _make_settings()
    token = create_access_token("user-123", settings)
    assert verify_token(token, settings) == "user-123"


def test_expired_token():
    settings = _make_settings(jwt_expiry_minutes=-1)
    token = create_access_token("user-123", settings)
    assert verify_token(token, settings) is None


def test_invalid_token():
    settings = _make_settings()
    assert verify_token("garbage.token.value", settings) is None


def test_wrong_secret():
    settings = _make_settings(jwt_secret="secret-a")
    token = create_access_token("user-123", settings)
    other_settings = _make_settings(jwt_secret="secret-b")
    assert verify_token(token, other_settings) is None
