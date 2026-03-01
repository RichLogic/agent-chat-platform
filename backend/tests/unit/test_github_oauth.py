"""GitHub OAuth URL generation and state validation tests."""

from __future__ import annotations

from agent_chat.auth.github import _pending_states, get_authorize_url, validate_state
from agent_chat.config import Settings


def _make_settings() -> Settings:
    return Settings(
        _env_file=None,
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
        frontend_url="http://localhost:3000",
    )


def test_authorize_url():
    settings = _make_settings()
    url = get_authorize_url(settings)
    assert "client_id=test-client-id" in url
    assert "scope=read" in url
    assert "state=" in url
    assert url.startswith("https://github.com/login/oauth/authorize?")
    # Clean up added state
    _pending_states.clear()


def test_validate_state_valid():
    settings = _make_settings()
    url = get_authorize_url(settings)
    # Extract state from URL
    state = None
    for part in url.split("&"):
        if part.startswith("state="):
            state = part.split("=", 1)[1]
            break
    assert state is not None
    assert validate_state(state) is True
    # Second call should return False (state consumed)
    assert validate_state(state) is False


def test_validate_state_invalid():
    assert validate_state("random-invalid-string") is False
