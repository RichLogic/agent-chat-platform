"""LLM provider factory tests."""

from __future__ import annotations

from unittest.mock import patch

from agent_chat.config import Settings
from agent_chat.llm.factory import create_provider


def test_poe_provider():
    settings = Settings(
        _env_file=None,
        llm_provider="poe",
        poe_api_key="test-poe-key",
        poe_model="Gemini-3-Flash",
        poe_base_url="https://api.poe.com/v1",
    )
    with patch("agent_chat.llm.provider.AsyncOpenAI"):
        provider = create_provider(settings)
    assert provider.provider_name == "poe"
    assert provider.model == "Gemini-3-Flash"


def test_kimi_provider():
    settings = Settings(
        _env_file=None,
        llm_provider="kimi",
        kimi_api_key="test-kimi-key",
        kimi_model="kimi-k2.5",
        kimi_base_url="https://kimi-k2.ai/api/v1",
    )
    with patch("agent_chat.llm.provider.AsyncOpenAI"):
        provider = create_provider(settings)
    assert provider.provider_name == "kimi"
    assert provider.model == "kimi-k2.5"
